"""
Dashboard webapp — FastAPI backend + React/Blueprint SPA.

Run:
    python -m src.dashboard

Then open http://localhost:8000 in your browser.

Architecture:
  - /api/*          → REST endpoints consumed by the React SPA
  - /               → serves the React build (src/dashboard/static/app/index.html)
  - /static/        → legacy Jinja2 static files (kept for backward compat)
  - /partial/*      → legacy HTMX partials (kept for backward compat)

The React app is built with `npm run build` inside frontend/ and written
to src/dashboard/static/app/.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.analytics.insights_generator import generate_insights
from src.analytics.queries import (
    cost_summary,
    framework_motion_heatmap,
    framework_stats,
    significance_status,
    subject_line_stats,
    variant_stats,
    variant_vertical_heatmap,
)
from src.utils.settings import load_settings

log = logging.getLogger(__name__)

app = FastAPI(title="Ascentir Outreach OS")

ROOT = Path(__file__).parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
REACT_BUILD = STATIC_DIR / "app"
DB_PATH = Path("ledger.sqlite")          # same path pipeline.py + run_batch.py write to
UPLOAD_DIR = Path("data/input")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount /static for legacy Jinja2 assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Pipeline background task state ─────────────────────────────────────────

_pipeline_task: asyncio.Task | None = None
_pipeline_status: dict[str, Any] = {
    "running":          False,
    "total":            0,
    "processed":        0,
    "sent":             0,
    "skipped":          0,
    "failed":           0,
    "duplicate_count":  0,       # leads skipped because already sent
    "recent_activity":  [],      # last 50 per-lead events [{name,company,status,time}]
    "start_time":       None,
    "elapsed_seconds":  None,
    "cost_usd":         None,
}


def _get_db() -> Path:
    """Return path to ledger, creating it if missing."""
    if not DB_PATH.exists():
        # Initialize by importing Ledger (creates schema)
        try:
            from src.utils.ledger import Ledger
            from src.utils.cost_tracker import CostTracker
            Ledger(str(DB_PATH))
            CostTracker(path=str(DB_PATH), daily_budget_usd=100.0)
        except Exception:
            pass
    return DB_PATH


def heatmap_color(reply_rate_pct: float) -> str:
    if reply_rate_pct >= 4.0:
        return "#1D9E75"
    if reply_rate_pct >= 3.0:
        return "#5DCAA5"
    if reply_rate_pct >= 2.0:
        return "#9FE1CB"
    if reply_rate_pct > 0:
        return "#E1F5EE"
    return "#f5f5f4"


templates.env.globals["heatmap_color"] = heatmap_color


# ─── Analytics helpers ───────────────────────────────────────────────────────

def _build_dashboard_data() -> dict | None:
    settings = load_settings()
    test = settings.active_test_config()
    if not test:
        return None

    db_path = _get_db()
    primary = test.get("primary_metric", "reply_rate")
    min_per = test.get("minimum_sent_per_variant", 1500)

    variants = variant_stats(db_path, test["id"])
    frameworks = framework_stats(db_path, test["id"])
    heatmap = framework_motion_heatmap(db_path, test["id"])
    vertical = variant_vertical_heatmap(db_path, test["id"])
    sig = significance_status(variants, min_per, primary)
    cost = cost_summary(db_path, test["id"])

    total_sent = sum(v.sent for v in variants)
    total_replied = sum(v.replied for v in variants)
    total_booked = sum(v.booked for v in variants)

    leader_variant = (
        next((v for v in variants if v.variant_id == sig["leader_variant_id"]), None)
        if sig["leader_variant_id"]
        else None
    )

    framework_keys = sorted(set(c.row_key for c in heatmap))
    motion_keys = ["plg_self_serve", "hybrid_sales_assisted", "sales_led_outbound"]
    grid = {(c.row_key, c.col_key): c for c in heatmap}

    heatmap_grid = []
    for f in framework_keys:
        row = {"framework": f, "cells": []}
        for m in motion_keys:
            cell = grid.get((f, m))
            row["cells"].append(
                {
                    "motion": m,
                    "reply_rate": cell.reply_rate * 100 if cell else 0,
                    "sent": cell.sent if cell else 0,
                    "has_data": cell is not None and cell.sent >= 50,
                }
            )
        heatmap_grid.append(row)

    return {
        "test": test,
        "test_name": test["id"],
        "primary_metric": primary,
        "min_per_variant": min_per,
        "variants": sorted(variants, key=lambda v: getattr(v, primary), reverse=True),
        "frameworks": sorted(frameworks, key=lambda f: getattr(f, primary), reverse=True),
        "heatmap_grid": heatmap_grid,
        "motion_keys": motion_keys,
        "vertical_cells": sorted(vertical, key=lambda c: -c.reply_rate)[:20],
        "sig": sig,
        "leader_variant": leader_variant,
        "leader_framework": frameworks[0] if frameworks else None,
        "total_sent": total_sent,
        "total_replied": total_replied,
        "total_booked": total_booked,
        "blended_reply_rate": (total_replied / total_sent * 100) if total_sent else 0,
        "cost": cost,
        "cost_per_booked": cost.get("cost_per_booked"),
    }


# ─── REST API ────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
async def api_analytics() -> JSONResponse:
    """Full analytics payload for the React dashboard."""
    settings = load_settings()
    test = settings.active_test_config()
    if not test:
        return JSONResponse(
            {
                "test_id": "none",
                "primary_metric": "reply_rate",
                "min_per_variant": 1500,
                "variants": [],
                "frameworks": [],
                "heatmap": [],
                "significance": {
                    "ready": False,
                    "leader_variant_id": None,
                    "significant_winners": [],
                    "min_sent": 0,
                    "min_required": 1500,
                },
                "cost": {"total_cost_usd": 0, "booked": 0, "cost_per_booked": None},
                "total_sent": 0,
                "total_replied": 0,
                "total_booked": 0,
                "blended_reply_rate": 0,
            }
        )

    db_path = _get_db()
    primary = test.get("primary_metric", "reply_rate")
    min_per = test.get("minimum_sent_per_variant", 1500)

    variants = variant_stats(db_path, test["id"])
    frameworks = framework_stats(db_path, test["id"])
    heatmap_cells = framework_motion_heatmap(db_path, test["id"])
    sig = significance_status(variants, min_per, primary)
    cost = cost_summary(db_path, test["id"])

    total_sent = sum(v.sent for v in variants)
    total_replied = sum(v.replied for v in variants)
    total_booked = sum(v.booked for v in variants)

    def variant_to_dict(v: Any) -> dict:
        return {
            "variant_id": v.variant_id,
            "framework": v.framework,
            "sent": v.sent,
            "opened": v.opened,
            "clicked": v.clicked,
            "replied": v.replied,
            "bounced": v.bounced,
            "booked": v.booked,
            "open_rate": v.open_rate,
            "reply_rate": v.reply_rate,
            "click_rate": v.click_rate,
            "book_rate": v.book_rate,
            "bounce_rate": v.bounce_rate,
        }

    def framework_to_dict(f: Any) -> dict:
        return {
            "framework": f.framework,
            "sent": f.sent,
            "opened": f.opened,
            "replied": f.replied,
            "booked": f.booked,
            "variant_ids": f.variant_ids,
            "open_rate": f.open_rate,
            "reply_rate": f.reply_rate,
            "book_rate": f.book_rate,
        }

    def cell_to_dict(c: Any) -> dict:
        return {
            "row_key": c.row_key,
            "col_key": c.col_key,
            "sent": c.sent,
            "replied": c.replied,
            "booked": c.booked,
            "reply_rate": c.reply_rate,
            "book_rate": c.book_rate,
        }

    return JSONResponse(
        {
            "test_id": test["id"],
            "primary_metric": primary,
            "min_per_variant": min_per,
            "variants": [variant_to_dict(v) for v in sorted(variants, key=lambda v: getattr(v, primary), reverse=True)],
            "frameworks": [framework_to_dict(f) for f in sorted(frameworks, key=lambda f: getattr(f, primary), reverse=True)],
            "heatmap": [cell_to_dict(c) for c in heatmap_cells],
            "significance": sig,
            "cost": cost,
            "total_sent": total_sent,
            "total_replied": total_replied,
            "total_booked": total_booked,
            "blended_reply_rate": (total_replied / total_sent * 100) if total_sent else 0,
        }
    )


@app.get("/api/analytics/subject-lines")
async def api_subject_lines(min_sent: int = Query(10, ge=1)) -> JSONResponse:
    """Per-subject-line open/reply performance.

    Groups by the actual subject text sent to each lead (stored in leads.subject_line).
    Only returns rows with >= min_sent sends to filter out noise.
    Sorted by reply_rate desc so the best-performing subjects surface first.
    """
    db_path = _get_db()
    rows = subject_line_stats(db_path, min_sent=min_sent)
    return JSONResponse(
        {
            "min_sent": min_sent,
            "total_subject_lines": len(rows),
            "subject_lines": [
                {
                    "subject_line": r.subject_line,
                    "variant_id":   r.variant_id,
                    "sent":         r.sent,
                    "opened":       r.opened,
                    "replied":      r.replied,
                    "booked":       r.booked,
                    "open_rate":    round(r.open_rate * 100, 1),
                    "reply_rate":   round(r.reply_rate * 100, 1),
                    "book_rate":    round(r.book_rate * 100, 1),
                }
                for r in rows
            ],
        }
    )


@app.get("/api/leads")
async def api_leads(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
) -> JSONResponse:
    """Paginated leads list."""
    db = _get_db()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    where = "WHERE 1=1"
    params: list[Any] = []
    if status:
        where += " AND status = ?"
        params.append(status)

    total = conn.execute(f"SELECT COUNT(*) FROM leads {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT lead_id, email, first_name, last_name, company, website, role,
               vertical, motion, intent_confidence, variant_id, test_id,
               framework, recommended_angle, status, email_type, created_at, completed_at
        FROM leads {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    conn.close()

    leads = [dict(r) for r in rows]
    return JSONResponse({"leads": leads, "total": total})


@app.get("/api/leads/{lead_id}")
async def api_lead_detail(lead_id: str) -> JSONResponse:
    """Single lead with all stages."""
    db = _get_db()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = dict(row)

    # Load all stages
    stage_rows = conn.execute(
        "SELECT stage_name, data_json FROM stages WHERE lead_id = ?", (lead_id,)
    ).fetchall()
    conn.close()

    stages: dict[str, Any] = {}
    for sr in stage_rows:
        try:
            stages[sr["stage_name"]] = json.loads(sr["data_json"])
        except Exception:
            stages[sr["stage_name"]] = None

    lead["stages"] = stages
    return JSONResponse(lead)


# NOTE: Static routes MUST be defined before parameterised routes sharing the
# same prefix.  FastAPI matches in registration order — /api/leads/bulk-delete
# and /api/leads/email-only must come before /api/leads/{lead_id} or the path
# parameter swallows the literal path segments.

@app.post("/api/leads/bulk-delete")
async def api_bulk_delete_leads(request: Request) -> JSONResponse:
    """Delete multiple leads by ID in one request."""
    body = await request.json()
    lead_ids = body.get("lead_ids", [])
    if not lead_ids:
        return JSONResponse({"deleted": 0, "lead_ids": []})

    db = _get_db()
    conn = sqlite3.connect(str(db))
    placeholders = ",".join("?" * len(lead_ids))
    conn.execute(f"DELETE FROM stages WHERE lead_id IN ({placeholders})", lead_ids)
    conn.execute(f"DELETE FROM leads  WHERE lead_id IN ({placeholders})", lead_ids)
    conn.commit()
    deleted = len(lead_ids)
    conn.close()
    log.info("Bulk deleted %d leads", deleted)
    return JSONResponse({"deleted": deleted, "lead_ids": lead_ids})


@app.delete("/api/leads/email-only")
async def api_delete_email_only_leads() -> JSONResponse:
    """Delete all email-only leads (non-video) that haven't been pushed to Smartlead.

    Keeps all video leads (email_type = 'video') and already-sent leads intact.
    Targets: status IN ('dry_run', 'skipped', 'failed') AND email_type = 'email_only'
    """
    db = _get_db()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT lead_id FROM leads
        WHERE email_type = 'email_only'
          AND status IN ('dry_run', 'skipped', 'failed')
        """
    ).fetchall()
    ids = [r["lead_id"] for r in rows]

    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM stages WHERE lead_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM leads  WHERE lead_id IN ({placeholders})", ids)
        conn.commit()

    conn.close()
    log.info("Deleted %d email-only leads", len(ids))
    return JSONResponse({"deleted": len(ids), "lead_ids": ids})


@app.delete("/api/leads/{lead_id}")
async def api_delete_lead(lead_id: str) -> JSONResponse:
    """Delete a single lead and all its stages from the ledger."""
    db = _get_db()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT lead_id, status FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead not found")

    conn.execute("DELETE FROM stages WHERE lead_id = ?", (lead_id,))
    conn.execute("DELETE FROM leads WHERE lead_id = ?", (lead_id,))
    conn.commit()
    conn.close()
    log.info("Deleted lead %s (was status=%s)", lead_id, row["status"])
    return JSONResponse({"deleted": True, "lead_id": lead_id})


@app.post("/api/pipeline/upload")
async def api_pipeline_upload(file: UploadFile = File(...)) -> JSONResponse:
    """Save uploaded CSV to data/input/ and return the path + row count."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files accepted")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Count data rows using the real CSV parser — NOT splitlines().
    # Many skiptrace CSVs have embedded newlines inside quoted fields
    # (e.g. COMPANY_DESCRIPTION).  splitlines() counts those as extra rows
    # and can report 2× the real lead count.  csv.reader handles quoting
    # correctly and gives the true row count.
    import csv as _csv, io as _io
    decoded = content.decode("utf-8", errors="replace")
    reader  = _csv.reader(_io.StringIO(decoded))
    lead_count = max(0, sum(1 for _ in reader) - 1)   # -1 for header

    # Count how many of these leads already exist in the DB (duplicates).
    # Use csv_reader._lead_id() so the hash algorithm stays in one place.
    from src.ingestion.csv_reader import _lead_id as _compute_lead_id
    import csv as _csv2, io as _io2
    _decoded2 = content.decode("utf-8", errors="replace")
    _reader2 = _csv2.DictReader(_io2.StringIO(_decoded2))
    _rows2 = [{k.strip().upper(): (v or "").strip() for k, v in row.items()} for row in _reader2]
    _emails = []
    for _row in _rows2:
        _e = _row.get("BUSINESS_EMAIL") or _row.get("BUSINESS_VERIFIED_EMAILS") or _row.get("EMAIL", "")
        _e = _e.split(",")[0].strip().lower()
        if _e and "@" in _e:
            _emails.append(_e)

    _lead_ids = [_compute_lead_id(e) for e in _emails]
    duplicate_count_upload = 0
    if _lead_ids:
        _db = _get_db()
        _conn2 = sqlite3.connect(str(_db))
        _placeholders = ",".join("?" * len(_lead_ids))
        _existing = _conn2.execute(
            f"SELECT COUNT(*) FROM leads WHERE lead_id IN ({_placeholders})"
            f" AND status IN ('sent','success')",
            _lead_ids,
        ).fetchone()[0]
        duplicate_count_upload = _existing
        _conn2.close()
    new_leads_count = max(0, lead_count - duplicate_count_upload)

    # Record this upload in the csv_uploads table
    try:
        from src.utils.ledger import Ledger
        _ledger = Ledger(str(_get_db()))
        _ledger.record_csv_upload(
            filename=file.filename,
            csv_path=str(dest),
            lead_count=lead_count,
            new_leads=new_leads_count,
            duplicate_leads=duplicate_count_upload,
        )
    except Exception as _e:
        log.warning("Could not record CSV upload: %s", _e)

    return JSONResponse(
        {
            "filename": file.filename,
            "lead_count": lead_count,
            "new_leads": new_leads_count,
            "duplicate_leads": duplicate_count_upload,
            "csv_path": str(dest),
        }
    )


@app.get("/api/pipeline/csv-history")
async def api_csv_history() -> JSONResponse:
    """Return all uploaded CSVs with their lead counts, newest first."""
    db = _get_db()
    if not db.exists():
        return JSONResponse({"uploads": [], "total_new_leads": 0})
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, filename, csv_path, uploaded_at,
                   lead_count, new_leads, duplicate_leads
            FROM csv_uploads
            ORDER BY uploaded_at DESC
            LIMIT 50
            """
        ).fetchall()
        uploads = [dict(r) for r in rows]
        total_new = sum(u["new_leads"] for u in uploads)
    except Exception:
        # Table may not exist yet on older DBs
        uploads = []
        total_new = 0
    finally:
        conn.close()
    return JSONResponse({"uploads": uploads, "total_new_leads": total_new})


@app.get("/api/pipeline/readiness")
async def api_pipeline_readiness() -> JSONResponse:
    """How many leads are personalized (dry-run complete) and ready to push to Smartlead.

    Used by the two-phase Pipeline UI:
      Phase 1 → Personalize Leads  (dry_run=True)
      Phase 2 → Push to Smartlead  (dry_run=False, stages cached so it's fast)

    Queries the stages table so it works even before the email_type migration runs.
    """
    db = _get_db()
    if not db.exists():
        return JSONResponse({
            "personalized": 0, "video_count": 0,
            "email_only_count": 0, "ready_to_push": 0, "already_sent": 0,
        })

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # All leads that Phase 2 (Push to Smartlead) will actually process:
    # - Not yet sent/succeeded (any other status, including NULL)
    # - No smartlead stage yet
    # This matches the pipeline dedup logic exactly so the count shown = leads pushed.
    rows = conn.execute(
        """
        SELECT l.lead_id, h.data_json AS hosting_json
        FROM   leads l
        LEFT  JOIN stages h  ON h.lead_id  = l.lead_id AND h.stage_name  = 'hosting'
        LEFT  JOIN stages sm ON sm.lead_id = l.lead_id AND sm.stage_name = 'smartlead'
        WHERE  (l.status NOT IN ('sent', 'success') OR l.status IS NULL)
          AND  sm.lead_id IS NULL
        """
    ).fetchall()

    personalized    = len(rows)
    video_count     = 0
    email_only_count = 0
    for r in rows:
        j = r["hosting_json"] or ""
        if '"email_only": true' in j or '"email_only":true' in j:
            email_only_count += 1
        elif j:                        # has a hosting record but not email_only → video
            video_count += 1
        # no hosting record yet (e.g. failed before hosting stage) → neither bucket

    sent_row = conn.execute(
        "SELECT COUNT(*) AS n FROM leads WHERE status IN ('sent','success')"
    ).fetchone()
    already_sent = (sent_row["n"] or 0) if sent_row else 0

    # ── All-time cumulative totals ─────────────────────────────────────────
    # These show total progress against the full CSV, not just the last batch.
    totals = conn.execute(
        """
        SELECT
            COUNT(*)                                                          AS all_total,
            SUM(CASE WHEN status IN ('dry_run','sent','success') THEN 1 ELSE 0 END) AS all_personalised,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END)              AS all_skipped,
            SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END)              AS all_failed
        FROM leads
        """
    ).fetchone()

    conn.close()

    return JSONResponse({
        "personalized":       personalized,
        "video_count":        video_count,
        "email_only_count":   email_only_count,
        "ready_to_push":      personalized,
        "already_sent":       already_sent,
        # All-time cumulative progress (shown in the UI progress tracker)
        "all_personalised":   (totals["all_personalised"] or 0) if totals else 0,
        "all_skipped":        (totals["all_skipped"]      or 0) if totals else 0,
        "all_failed":         (totals["all_failed"]       or 0) if totals else 0,
        "all_total":          (totals["all_total"]        or 0) if totals else 0,
    })


@app.get("/api/pipeline/campaign-check")
async def api_campaign_check() -> JSONResponse:
    """Validate the configured Smartlead campaign is ready to receive leads.

    Called by the frontend before showing the Phase 2 push button.
    Returns ok=True only if campaign is ACTIVE and Step 1 has the right variables.
    """
    from src.ai_cold_email.smartlead.client import validate_campaign
    settings = load_settings()
    result = await validate_campaign(settings)
    return JSONResponse(result)


@app.post("/api/pipeline/preview")
async def api_pipeline_preview(body: dict[str, Any]) -> JSONResponse:
    """Parse an uploaded CSV and classify each lead as new vs already-sent duplicate.

    Returns counts + lead lists so the UI can show "248 new · 12 duplicates (skipped)"
    before the user hits Launch.
    """
    csv_path = body.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        raise HTTPException(status_code=400, detail="csv_path is required and must exist")

    from src.ingestion.csv_reader import read_leads
    try:
        leads = read_leads(Path(csv_path))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}") from exc

    db = _get_db()
    conn: sqlite3.Connection | None = None
    if db.exists():
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row

    new_leads: list[dict] = []
    duplicate_leads: list[dict] = []

    for lead in leads:
        existing_status: str | None = None
        if conn:
            row = conn.execute(
                "SELECT status FROM leads WHERE lead_id=?", (lead["lead_id"],)
            ).fetchone()
            existing_status = row["status"] if row else None

        entry = {
            "lead_id":         lead["lead_id"],
            "email":           lead.get("email", ""),
            "first_name":      lead.get("first_name", ""),
            "last_name":       lead.get("last_name", ""),
            "company":         lead.get("company", ""),
            "existing_status": existing_status,
        }

        if existing_status in ("sent", "success"):
            duplicate_leads.append(entry)
        else:
            new_leads.append(entry)

    if conn:
        conn.close()

    return JSONResponse({
        "total":           len(leads),
        "new_count":       len(new_leads),
        "duplicate_count": len(duplicate_leads),
        "new_leads":       new_leads[:200],       # cap for response size
        "duplicate_leads": duplicate_leads[:200],
    })


@app.post("/api/pipeline/run")
async def api_pipeline_run(body: dict[str, Any]) -> JSONResponse:
    """Start the pipeline as a background asyncio task."""
    global _pipeline_task, _pipeline_status

    if _pipeline_task and not _pipeline_task.done():
        raise HTTPException(status_code=409, detail="Pipeline already running")

    csv_path = body.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        raise HTTPException(status_code=400, detail="csv_path is required and must exist")

    dry_run: bool     = body.get("dry_run", True)
    single_lead: Optional[int] = body.get("single_lead")
    # Phase 1 (Personalize): batch 100 at a time — video gen is slow.
    # Phase 2 (Push to Smartlead): process ALL ready leads at once so the
    # count shown equals the count pushed. batch_size=0 means unlimited.
    if dry_run:
        batch_size: int = int(body.get("batch_size", 100))
    else:
        batch_size = 0

    # Count total leads in CSV so the UI can show "X of N total" progress
    try:
        import csv as _csv, io as _io
        _raw     = Path(csv_path).read_bytes()
        _decoded = _raw.decode("utf-8", errors="replace")
        _reader  = _csv.reader(_io.StringIO(_decoded))
        csv_total = max(0, sum(1 for _ in _reader) - 1)
    except Exception:
        csv_total = 0

    # Reset status
    _pipeline_status.update(
        {
            "running":          True,
            "csv_total":        csv_total,   # full file size — stays constant across batches
            "total":            0,
            "processed":        0,
            "sent":             0,
            "skipped":          0,
            "failed":           0,
            "duplicate_count":  0,
            "recent_activity":  [],
            "start_time":       datetime.utcnow().isoformat(),
            "elapsed_seconds":  0,
            "cost_usd":         0.0,
        }
    )

    async def _run():
        global _pipeline_status
        t0 = time.monotonic()

        from src.ai_cold_email.orchestrator.pipeline import run_pipeline
        from src.enrichment.website import init_shared_browser, close_shared_browser

        # Start ONE shared Chromium instance for the whole batch
        try:
            await init_shared_browser()
        except Exception as e:
            log.warning("Could not start shared browser: %s", e)

        try:
            settings = load_settings()
            safe_settings = settings.model_copy(
                update={"max_concurrent_leads": min(settings.max_concurrent_leads, 3)}
            )
            await run_pipeline(
                csv_path=Path(csv_path),
                single_lead_index=single_lead,
                resume=False,
                dry_run=dry_run,
                settings=safe_settings,
                status_ref=_pipeline_status,
                batch_size=batch_size,
            )
        except asyncio.CancelledError:
            log.info("Pipeline cancelled")
        except Exception as e:
            log.error(f"Pipeline error: {e}", exc_info=True)
            _pipeline_status["last_error"] = str(e)
        finally:
            _pipeline_status["running"] = False
            _pipeline_status["elapsed_seconds"] = round(time.monotonic() - t0)
            try:
                await close_shared_browser()
            except Exception:
                pass

    _pipeline_task = asyncio.create_task(_run())
    return JSONResponse({"started": True, "batch_size": batch_size})


@app.post("/api/pipeline/diagnose")
async def api_pipeline_diagnose(body: dict[str, Any]) -> JSONResponse:
    """Run a single lead end-to-end and return the FULL error (if any).

    Use this to debug failures without guessing — the response includes:
      - every stage that was reached
      - the exact exception class + message
      - the full Python traceback as a string

    Body: { "csv_path": "...", "lead_index": 0 }
    """
    import traceback as _tb
    csv_path = body.get("csv_path")
    lead_index = int(body.get("lead_index", body.get("index", 0)))

    if not csv_path or not Path(csv_path).exists():
        raise HTTPException(status_code=400, detail="csv_path required and must exist")

    from src.ingestion.csv_reader import read_leads
    from src.utils.ledger import Ledger
    from src.utils.cost_tracker import CostTracker
    from src.enrichment.website import init_shared_browser, close_shared_browser
    from src.ai_cold_email.orchestrator.pipeline import process_lead

    leads = read_leads(Path(csv_path))
    if lead_index >= len(leads):
        raise HTTPException(status_code=400, detail=f"lead_index {lead_index} out of range (CSV has {len(leads)} leads)")

    lead = leads[lead_index]
    settings = load_settings()
    safe_settings = settings.model_copy(update={"max_concurrent_leads": 1})
    ledger = Ledger("ledger.sqlite")
    cost_tracker = CostTracker(path="ledger.sqlite", daily_budget_usd=100.0)

    result: dict = {
        "lead": {
            "index":      lead_index,
            "name":       f"{lead.get('first_name','')} {lead.get('last_name','')}".strip(),
            "company":    lead.get("company", ""),
            "email":      lead.get("email", ""),
            "website":    lead.get("website", ""),
            "lead_id":    lead.get("lead_id", "")[:12],
        },
        "status":     "unknown",
        "error":      None,
        "error_type": None,
        "traceback":  None,
        "stages_completed": [],
    }

    try:
        await init_shared_browser()
    except Exception as e:
        result["browser_warning"] = str(e)

    try:
        out = await process_lead(lead, safe_settings, ledger, cost_tracker, dry_run=True)
        result["status"] = out.get("status", "ok")
        result["output"] = out
    except Exception as e:
        result["status"]     = "failed"
        result["error_type"] = type(e).__name__
        result["error"]      = str(e)
        result["traceback"]  = _tb.format_exc()
    finally:
        # Record which stages made it to the ledger
        import sqlite3
        try:
            conn = sqlite3.connect("ledger.sqlite")
            rows = conn.execute(
                "SELECT stage_name FROM stages WHERE lead_id=?", (lead.get("lead_id", ""),)
            ).fetchall()
            result["stages_completed"] = [r[0] for r in rows]
            conn.close()
        except Exception:
            pass
        try:
            await close_shared_browser()
        except Exception:
            pass

    return JSONResponse(result)


@app.post("/api/pipeline/stop")
async def api_pipeline_stop() -> JSONResponse:
    """Cancel the running pipeline task."""
    global _pipeline_task, _pipeline_status

    if _pipeline_task and not _pipeline_task.done():
        _pipeline_task.cancel()
        try:
            await _pipeline_task
        except (asyncio.CancelledError, Exception):
            pass
    _pipeline_status["running"] = False
    return JSONResponse({"stopped": True})


@app.get("/api/pipeline/status")
async def api_pipeline_status() -> JSONResponse:
    """Return live pipeline counters, also pulling from ledger for accuracy."""
    global _pipeline_status

    # Augment with live ledger counts if a run is in progress or just finished
    try:
        db = _get_db()
        if db.exists():
            conn = sqlite3.connect(str(db))
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status IN ('sent','dry_run') THEN 1 ELSE 0 END) AS sent,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                    SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) AS failed
                FROM leads
                """
            ).fetchone()
            cost_row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM costs"
            ).fetchone()
            conn.close()

            if row:
                _pipeline_status["total"] = row[0] or 0
                _pipeline_status["sent"] = row[1] or 0
                _pipeline_status["skipped"] = row[2] or 0
                _pipeline_status["failed"] = row[3] or 0
                _pipeline_status["processed"] = (
                    (_pipeline_status["sent"] or 0)
                    + (_pipeline_status["skipped"] or 0)
                    + (_pipeline_status["failed"] or 0)
                )
            if cost_row:
                _pipeline_status["cost_usd"] = round(cost_row[0] or 0, 4)
    except Exception:
        pass

    if _pipeline_status.get("start_time") and _pipeline_status["running"]:
        _pipeline_status["elapsed_seconds"] = round(
            time.monotonic()
            - time.mktime(
                datetime.fromisoformat(_pipeline_status["start_time"]).timetuple()
            )
        )

    return JSONResponse(_pipeline_status)


# ─── Playbook API ────────────────────────────────────────────────────────────

_VALID_MARKETS = ("coach", "agency", "consultant", "financial_advisor", "msp")


@app.get("/api/playbook/markets")
async def api_playbook_markets() -> JSONResponse:
    """Return the list of valid market keys and their display names."""
    return JSONResponse({
        "markets": [
            {"key": "coach",            "label": "Coaches & Training Firms"},
            {"key": "agency",           "label": "Marketing & Advertising Agencies"},
            {"key": "consultant",       "label": "Consulting / Advisory Firms"},
            {"key": "financial_advisor","label": "Financial Advisory / Fractional CFO"},
            {"key": "msp",              "label": "MSPs & B2B Cybersecurity"},
        ]
    })


@app.get("/api/playbook")
async def api_playbook_get(market: Optional[str] = Query(None)) -> JSONResponse:
    """Return email and SMS templates for the Playbook editor.

    When `market` is provided (one of coach/agency/consultant/financial_advisor/msp),
    returns the market-specific scaffolds from config/templates.yaml.
    When omitted, returns all markets grouped together.

    Combines config from settings.yaml (variant metadata) with editable
    template content from config/templates.yaml.
    """
    from src.utils.template_store import load_templates
    settings  = load_settings()
    overrides = load_templates()

    if market and market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"Invalid market. Valid: {_VALID_MARKETS}")

    def _get_tmpl(channel: str, vid: str, mkt: str | None) -> dict:
        """Look up market-keyed first, fall back to flat."""
        ch_data = overrides.get(channel, {})
        if mkt and mkt in ch_data:
            return ch_data[mkt].get(vid, {})
        return ch_data.get(vid, {})

    # ── Email variants ──────────────────────────────────────────────────────
    email_variants = []
    active_test = settings.variants.get("framework_tournament_v1", {})

    if market:
        # Single market — return that market's 9 variants
        for arm in active_test.get("arms", []):
            vid  = arm["id"]
            tmpl = _get_tmpl("email", vid, market)
            email_variants.append({
                "variant_id":      vid,
                "market":          market,
                "framework":       arm.get("overrides", {}).get("variant_framework", ""),
                "description":     arm.get("description", ""),
                "subject_formula": tmpl.get("subject_formula", ""),
                "template":        tmpl.get("template", ""),
                "word_count":      tmpl.get("word_count", ""),
                "ai_fills":        tmpl.get("ai_fills", ""),
                "is_edited":       bool(tmpl.get("template")),
            })
    else:
        # All markets — return grouped
        for mkt in _VALID_MARKETS:
            for arm in active_test.get("arms", []):
                vid  = arm["id"]
                tmpl = _get_tmpl("email", vid, mkt)
                email_variants.append({
                    "variant_id":      vid,
                    "market":          mkt,
                    "framework":       arm.get("overrides", {}).get("variant_framework", ""),
                    "description":     arm.get("description", ""),
                    "subject_formula": tmpl.get("subject_formula", ""),
                    "template":        tmpl.get("template", ""),
                    "word_count":      tmpl.get("word_count", ""),
                    "ai_fills":        tmpl.get("ai_fills", ""),
                    "is_edited":       bool(tmpl.get("template")),
                })

    # ── SMS variants ────────────────────────────────────────────────────────
    sms_variants = []
    sms_test_id   = settings.sms.get("variants", {}).get("active_test", "sms_framework_v1")
    sms_test      = settings.sms.get("variants", {}).get(sms_test_id, {})

    target_markets = [market] if market else list(_VALID_MARKETS)
    for mkt in target_markets:
        for arm in sms_test.get("arms", []):
            vid  = arm["id"]
            tmpl = _get_tmpl("sms", vid, mkt)
            sms_variants.append({
                "variant_id":  vid,
                "market":      mkt,
                "name":        arm.get("name", ""),
                "framework":   arm.get("framework", ""),
                "description": arm.get("description", ""),
                "template":    tmpl.get("template", ""),
                "char_limit":  tmpl.get("char_limit", 160),
                "ai_fills":    tmpl.get("ai_fills", ""),
                "is_edited":   bool(tmpl.get("template")),
            })

    return JSONResponse({
        "email":   email_variants,
        "sms":     sms_variants,
        "market":  market or "all",
        "markets": list(_VALID_MARKETS),
    })


@app.put("/api/playbook/template")
async def api_playbook_save(payload: dict[str, Any]) -> JSONResponse:
    """Save an edited template from the Playbook editor.

    Body: {
      "channel": "email"|"sms",
      "variant_id": "...",
      "updates": {...},
      "market": "coach"|"agency"|"consultant"|"financial_advisor"|"msp"  (optional)
    }
    Allowed update keys: template, subject_formula, word_count, char_limit, ai_fills
    """
    from src.utils.template_store import save_template
    channel    = payload.get("channel", "")
    variant_id = payload.get("variant_id", "")
    updates    = payload.get("updates", {})
    market     = payload.get("market") or None

    if not channel or not variant_id:
        raise HTTPException(status_code=400, detail="channel and variant_id are required")
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")
    if market and market not in _VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"Invalid market. Valid: {_VALID_MARKETS}")
    if not updates:
        raise HTTPException(status_code=400, detail="updates cannot be empty")

    # Only allow safe keys
    allowed_keys = {"template", "subject_formula", "word_count", "char_limit", "ai_fills"}
    filtered = {k: v for k, v in updates.items() if k in allowed_keys}
    if not filtered:
        raise HTTPException(status_code=400, detail=f"No valid update keys. Allowed: {allowed_keys}")

    save_template(channel, variant_id, filtered, market=market)
    log.info(
        "Playbook template updated: channel=%s market=%s variant=%s keys=%s",
        channel, market or "flat", variant_id, list(filtered),
    )
    return JSONResponse({
        "ok": True,
        "channel": channel,
        "market": market or "flat",
        "variant_id": variant_id,
        "updated_keys": list(filtered),
    })


# ─── SMS API ─────────────────────────────────────────────────────────────────

def _get_sms_ledger():
    """Lazy-init SMS ledger (creates file + schema on first call)."""
    from src.sms.ledger import SMSLedger
    settings = load_settings()
    db_path = settings.sms.get("db_path", "data/sms_ledger.sqlite")
    return SMSLedger(path=db_path)


@app.get("/api/sms/analytics")
async def api_sms_analytics() -> JSONResponse:
    """SMS KPIs, variant stats, and per-number stats — fully separate from email.

    All rate fields are returned as fractions (0.0–1.0) so the frontend can
    multiply by 100 for display.  Variant names come from settings.yaml.
    """
    try:
        settings = load_settings()
        ledger   = _get_sms_ledger()
        raw_kpis = ledger.kpi_summary()
        raw_vars = ledger.variant_stats()
        raw_nums = ledger.number_stats()

        # Active test config from settings.yaml
        sms_cfg     = settings.sms
        test_id     = sms_cfg.get("variants", {}).get("active_test", "sms_framework_v1")
        active_test = sms_cfg.get("variants", {}).get(test_id, {})
        arms_by_id  = {a["id"]: a for a in active_test.get("arms", [])}

        # KPIs — fractions for rates
        sent     = raw_kpis.get("sent") or 0
        replied  = raw_kpis.get("replied") or 0
        opted    = raw_kpis.get("opted_out") or 0
        booked   = raw_kpis.get("booked") or 0
        kpis = {
            "total_sent":          sent,
            "total_delivered":     sent,   # Twilio delivery receipts not tracked yet
            "total_replied":       replied,
            "total_opted_out":     opted,
            "total_booked":        booked,
            "blended_reply_rate":  round(replied / sent, 4) if sent else 0.0,
            "blended_opt_out_rate": round(opted  / sent, 4) if sent else 0.0,
        }

        # Variant stats — enrich with name from settings, rates as fractions
        variants = []
        for v in raw_vars:
            vid  = v.get("variant_id", "")
            arm  = arms_by_id.get(vid, {})
            vsnt = v.get("sent") or 0
            variants.append({
                "variant_id":   vid,
                "name":         arm.get("name", vid),
                "framework":    v.get("framework", arm.get("framework", "")),
                "sent":         vsnt,
                "delivered":    vsnt,
                "replied":      v.get("replied") or 0,
                "opted_out":    v.get("opted_out") or 0,
                "reply_rate":   round((v.get("replied") or 0) / vsnt, 4) if vsnt else 0.0,
                "opt_out_rate": round((v.get("opted_out") or 0) / vsnt, 4) if vsnt else 0.0,
            })

        # Number stats — rename assigned_number → number, rates as fractions
        numbers = []
        for n in raw_nums:
            nsnt = n.get("sent") or 0
            numbers.append({
                "number":    n.get("assigned_number", ""),
                "sent":      nsnt,
                "delivered": nsnt,
                "replied":   n.get("replied") or 0,
                "opted_out": n.get("opted_out") or 0,
                "reply_rate": round((n.get("replied") or 0) / nsnt, 4) if nsnt else 0.0,
            })

        return JSONResponse({
            "kpis":     kpis,
            "variants": variants,
            "numbers":  numbers,
            "test_id":  test_id,
        })

    except Exception as e:
        log.error("SMS analytics error: %s", e)
        return JSONResponse({
            "kpis": {
                "total_sent": 0, "total_delivered": 0, "total_replied": 0,
                "total_opted_out": 0, "total_booked": 0,
                "blended_reply_rate": 0.0, "blended_opt_out_rate": 0.0,
            },
            "variants": [],
            "numbers":  [],
            "test_id":  "sms_framework_v1",
        })


@app.get("/api/sms/leads")
async def api_sms_leads(
    offset: int = Query(0, ge=0),
    limit: int  = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
) -> JSONResponse:
    """Paginated SMS leads list with last-message preview."""
    ledger = _get_sms_ledger()
    leads  = ledger.list_leads(status=status, limit=limit, offset=offset)
    total  = ledger.count_leads(status=status)

    # Enrich each lead with last message preview
    for lead in leads:
        msgs = ledger.get_conversation(lead["lead_id"])
        if msgs:
            last = msgs[-1]
            lead["last_message"]    = last["body"][:80]
            lead["last_message_at"] = last["sent_at"]
        else:
            lead["last_message"]    = None
            lead["last_message_at"] = None

    return JSONResponse({"leads": leads, "total": total})


@app.get("/api/sms/conversations/{lead_id}")
async def api_sms_conversation(lead_id: str) -> JSONResponse:
    """Full message thread for a single SMS lead."""
    from src.sms.conversation import get_conversation
    ledger = _get_sms_ledger()
    data   = get_conversation(lead_id, ledger)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return JSONResponse(data)


@app.post("/api/sms/reply")
async def api_sms_reply(payload: dict[str, Any]) -> JSONResponse:
    """Send a manual reply to a lead from the dashboard.

    Body: { "lead_id": "...", "body": "..." }
    """
    from src.sms.conversation import reply_from_dashboard
    lead_id = payload.get("lead_id")
    message = payload.get("body", "").strip()
    if not lead_id or not message:
        raise HTTPException(status_code=400, detail="lead_id and body are required")

    ledger   = _get_sms_ledger()
    settings = load_settings()
    result   = await reply_from_dashboard(lead_id, message, ledger, settings)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "send failed"))
    return JSONResponse(result)


@app.post("/api/sms/webhook/inbound")
async def api_sms_inbound(request: Request) -> Any:
    """Twilio inbound SMS webhook.

    Configure in Twilio console:
    Each number → 'A message comes in' → Webhook → POST → https://your-domain/api/sms/webhook/inbound

    Twilio sends form-encoded data; we return an empty TwiML response so Twilio
    doesn't auto-reply.  Manual replies are sent from the dashboard.
    """
    from src.sms.conversation import handle_inbound
    from fastapi.responses import Response

    form = await request.form()
    from_number = str(form.get("From", ""))
    to_number   = str(form.get("To", ""))
    body        = str(form.get("Body", ""))
    twilio_sid  = str(form.get("MessageSid", ""))

    ledger   = _get_sms_ledger()
    settings = load_settings()

    await handle_inbound(
        from_number=from_number,
        to_number=to_number,
        body=body,
        twilio_sid=twilio_sid,
        ledger=ledger,
        settings=settings,
    )

    # Return empty TwiML — we don't auto-respond
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


# ─── Video script A/B tracking ───────────────────────────────────────────────

@app.get("/v/{lead_id}", response_class=HTMLResponse)
async def video_view_page(lead_id: str) -> HTMLResponse:
    """
    Personalised video landing page.

    The link embedded in every cold email is:
        https://your-domain.com/v/{lead_id}

    When a prospect clicks it:
      1. View event is logged to the SQLite tracker
      2. An HTML page is returned with:
           - The video autoplaying (hosted video URL)
           - A large clickable "GET A.I DEMO" button → Calendly
           - Clean branding, mobile-friendly

    Scalable: calendly_url comes from settings.yaml (default) and can be
    overridden per-lead when log_sent() is called with a custom cta_url.
    """
    from src.utils.video_tracker import log_viewed
    from src.utils.settings import Settings

    row = log_viewed(lead_id)          # returns dict with video_url + metadata
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    video_url    = row.get("video_url", "")
    company      = row.get("company", "")
    # Per-lead CTA URL takes priority; fall back to settings.yaml
    settings     = Settings()
    identity_cfg = settings.your_identity if isinstance(settings.your_identity, dict) else {}
    calendly_url = row.get("cta_url") or identity_cfg.get("calendly_url", "#")
    sender_name  = identity_cfg.get("your_first_name", "Frank")

    # Determine if the video can be served directly (local file) or needs an R2 URL
    # For local files we expose them via /api/video/file/{lead_id}
    if video_url and not video_url.startswith("http"):
        video_src = f"/api/video/file/{lead_id}"
    else:
        video_src = video_url

    headline = f"A personal message for {company}" if company else "A personal message for you"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{headline}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0f0f13;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .container {{ max-width: 800px; width: 100%; }}
    .headline {{
      font-size: clamp(16px, 2.5vw, 20px);
      color: #aaa;
      margin-bottom: 16px;
      text-align: center;
      letter-spacing: 0.3px;
    }}
    .video-wrap {{
      position: relative;
      width: 100%;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0,0,0,0.6);
      background: #000;
    }}
    video {{
      width: 100%;
      display: block;
      border-radius: 12px;
    }}
    .cta-wrap {{
      margin-top: 28px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
    }}
    .cta-btn {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background: #E63946;
      color: #fff;
      text-decoration: none;
      font-size: 18px;
      font-weight: 700;
      padding: 16px 40px;
      border-radius: 50px;
      letter-spacing: 0.3px;
      box-shadow: 0 8px 32px rgba(230,57,70,0.4);
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .cta-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 12px 40px rgba(230,57,70,0.55);
    }}
    .cta-sub {{
      font-size: 13px;
      color: #666;
    }}
    .sender {{
      margin-top: 32px;
      font-size: 13px;
      color: #444;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <p class="headline">{headline}</p>

    <div class="video-wrap">
      <video
        src="{video_src}"
        controls
        autoplay
        playsinline
        preload="auto"
      ></video>
    </div>

    <div class="cta-wrap">
      <a href="{calendly_url}" target="_blank" class="cta-btn">
        🤖 &nbsp;GET A.I DEMO with {sender_name}
      </a>
      <span class="cta-sub">20 minutes · No obligation · Leave your card at home</span>
    </div>

    <p class="sender">Sent personally by {sender_name} · <a href="https://ascentir.io" style="color:#555;text-decoration:none;">Ascentir</a></p>
  </div>
</body>
</html>"""

    return HTMLResponse(html)


@app.get("/api/video/file/{lead_id}")
async def video_file_serve(lead_id: str):
    """
    Serve the local video file for a lead (used when video_url is a local path).
    In production, videos are hosted on R2/S3 and this endpoint is not used.
    """
    import sqlite3
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse as _FR

    try:
        con = sqlite3.connect("data/video_ledger.sqlite")
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT video_url FROM video_events WHERE lead_id=? AND event_type='sent' "
            "ORDER BY id DESC LIMIT 1", (lead_id,)
        ).fetchone()
        con.close()
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    if not row:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = _Path(row["video_url"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {video_path}")

    return _FR(str(video_path), media_type="video/mp4")


@app.get("/api/video/analytics")
async def api_video_analytics() -> JSONResponse:
    """Per-variant video funnel: sent / views / replies / bookings."""
    from src.utils.video_tracker import get_analytics, get_recent_views
    return JSONResponse({
        "variants": get_analytics(),
        "recent":   get_recent_views(20),
    })


@app.get("/api/video/testing")
async def api_video_testing() -> JSONResponse:
    """
    Testing Framework dashboard — LVR / PRR / ABR KPIs per Morgan's Loom Alchemic Equation.
    Returns overall summary + per-variant breakdown with KPI pass/fail/pending status.
    """
    from src.utils.video_tracker import get_testing_summary
    return JSONResponse(get_testing_summary())


@app.post("/api/video/sync")
async def api_video_sync() -> JSONResponse:
    """
    Pull new view events from Cloudflare Worker KV into local SQLite.
    Called by the dashboard every 2 minutes, or triggered manually.
    """
    from src.utils.video_tracker import sync_from_cloudflare_kv
    new_views = await sync_from_cloudflare_kv()
    return JSONResponse({"synced": new_views})


@app.get("/api/video/variants")
async def api_video_variants(market: Optional[str] = Query(None)) -> JSONResponse:
    """Return video script variant metadata + their scripts.

    When `market` is provided, returns the market-specific scripts.
    When omitted, returns the flat/generic scripts (backward compat).
    """
    from src.ai_cold_email.video.script.video_scripts import list_variants, _load_variants_raw
    raw = _load_variants_raw()

    if market and market in _VALID_MARKETS and market in raw:
        variants_dict = raw[market]
    else:
        # Flat fallback — top-level V1..V4 keys
        variants_dict = {k: v for k, v in raw.items() if k in ("V1", "V2", "V3", "V4")}

    meta = [
        {
            "id":          vid,
            "name":        v["name"],
            "hook_style":  v["hook_style"],
            "description": v["description"].strip(),
            "script":      v["script"].strip(),
            "market":      market or "generic",
        }
        for vid, v in variants_dict.items()
    ]
    return JSONResponse({"variants": meta, "market": market or "generic"})


@app.post("/api/video/webhook/reply")
async def api_video_reply_webhook(payload: dict[str, Any]) -> JSONResponse:
    """
    Called by the Smartlead reply webhook to log email replies.
    Payload: { "lead_id": "...", "email": "..." }
    """
    from src.utils.video_tracker import log_replied
    lead_id = payload.get("lead_id", "")
    if lead_id:
        log_replied(lead_id)
    return JSONResponse({"ok": True})


@app.post("/api/video/webhook/booking")
async def api_video_booking_webhook(payload: dict[str, Any]) -> JSONResponse:
    """
    Called by the Calendly webhook to log bookings.
    Payload: { "lead_id": "...", "email": "..." }
    """
    from src.utils.video_tracker import log_booked
    lead_id = payload.get("lead_id", "")
    if not lead_id:
        # Try to look up by email
        lead_id = payload.get("email", "")
    if lead_id:
        log_booked(lead_id)
    return JSONResponse({"ok": True})


# ─── Legacy Jinja2 routes (kept for backward compat) ────────────────────────

@app.get("/legacy", response_class=HTMLResponse)
async def index_legacy(request: Request) -> HTMLResponse:
    data = _build_dashboard_data()
    if not data:
        return HTMLResponse(
            "<h1>No active test</h1>"
            "<p>Configure variants.active_test in settings.yaml.</p>"
        )
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})


@app.get("/partial/metrics", response_class=HTMLResponse)
async def metrics_partial(request: Request) -> HTMLResponse:
    data = _build_dashboard_data()
    if not data:
        return HTMLResponse("")
    return templates.TemplateResponse("_metrics_row.html", {"request": request, **data})


@app.get("/partial/insights", response_class=HTMLResponse)
async def insights_partial(request: Request) -> HTMLResponse:
    text = generate_insights(_get_db())
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return templates.TemplateResponse(
        "_insights_panel.html",
        {"request": request, "paragraphs": paragraphs},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ─── Serve React SPA ─────────────────────────────────────────────────────────
# Mount the React build's assets (JS/CSS chunks) at /app so they load correctly.
# The catch-all route below serves index.html for all other /app/* paths so
# that the React Router (or our manual state routing) works on hard refresh.

_REACT_INDEX = REACT_BUILD / "index.html"


@app.get("/", response_class=HTMLResponse)
async def spa_root() -> FileResponse:
    """Serve the React SPA."""
    if _REACT_INDEX.exists():
        return FileResponse(str(_REACT_INDEX))
    return HTMLResponse(
        """
        <html>
        <body style="font-family:sans-serif;background:#1c2127;color:#abb3bf;padding:40px">
          <h2 style="color:#f6f7f9">Dashboard not built yet</h2>
          <p>Run <code style="background:#252a31;padding:4px 8px;border-radius:4px">
            cd frontend && npm run build
          </code> to compile the React UI.</p>
          <p>Then restart the dashboard server.</p>
          <p style="margin-top:24px">
            <a href="/legacy" style="color:#4c90f0">→ Open legacy Jinja2 dashboard</a>
          </p>
        </body>
        </html>
        """,
        status_code=200,
    )


# Mount built React assets AFTER the catch-all so specific asset paths win.
# We use a conditional mount so the server starts even if not yet built.
if REACT_BUILD.exists():
    app.mount("/", StaticFiles(directory=str(REACT_BUILD), html=True), name="spa")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
