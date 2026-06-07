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

from contextlib import asynccontextmanager

# ─── Twilio sync worker ───────────────────────────────────────────────────────
_twilio_sync_stop  = asyncio.Event()
_twilio_sync_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app_: Any):
    """Start background workers on startup; stop them on shutdown."""
    global _twilio_sync_task, _twilio_sync_stop
    _twilio_sync_stop.clear()

    try:
        from src.sms.twilio_sync import run_sync_worker
        from src.sms.ledger import SMSLedger
        _settings = load_settings()
        if _settings.twilio_account_sid and _settings.twilio_auth_token and _settings.twilio_numbers:
            _sms_db   = _settings.sms.get("db_path", "data/sms_ledger.sqlite")
            _ledger   = SMSLedger(path=_sms_db)
            _twilio_sync_task = asyncio.create_task(
                run_sync_worker(_settings, _ledger, _twilio_sync_stop)
            )
            log.info("Twilio sync worker started (polling every 60 s)")
        else:
            log.info("Twilio credentials not configured — sync worker not started")
    except Exception as e:
        log.warning("Could not start Twilio sync worker: %s", e)

    yield   # server runs here

    # Shutdown
    _twilio_sync_stop.set()
    if _twilio_sync_task:
        try:
            await asyncio.wait_for(_twilio_sync_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _twilio_sync_task.cancel()


app = FastAPI(title="Ascentir Outreach OS", lifespan=lifespan)

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
    "sent":             0,       # leads actually pushed to SmartLead (status='sent')
    "dry_run_count":    0,       # leads personalised and awaiting push (status='dry_run')
    "db_sent":          0,       # alias for sent — kept for frontend compat
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
    icp_cells = variant_vertical_heatmap(db_path, test["id"])
    sig = significance_status(variants, min_per, primary)
    cost = cost_summary(db_path, test["id"])

    total_sent    = sum(v.sent for v in variants)     # emails delivered
    total_in_queue = sum(v.in_queue for v in variants) # leads added to SmartLead
    total_replied = sum(v.replied for v in variants)
    total_booked  = sum(v.booked for v in variants)

    def variant_to_dict(v: Any) -> dict:
        return {
            "variant_id": v.variant_id,
            "framework":  v.framework,
            "sent":       v.sent,       # emails delivered
            "in_queue":   v.in_queue,   # leads added to SmartLead campaign
            "opened":     v.opened,
            "clicked":    v.clicked,
            "replied":    v.replied,
            "bounced":    v.bounced,
            "booked":     v.booked,
            "open_rate":  v.open_rate,
            "reply_rate": v.reply_rate,
            "click_rate": v.click_rate,
            "book_rate":  v.book_rate,
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
            "row_key":    c.row_key,
            "col_key":    c.col_key,
            "sent":       c.sent,
            "opened":     getattr(c, "opened", 0),
            "replied":    c.replied,
            "booked":     c.booked,
            "open_rate":  getattr(c, "open_rate", 0.0),
            "reply_rate": c.reply_rate,
            "book_rate":  c.book_rate,
        }

    def _merge_variants(vs: list) -> list:
        """Collapse any remaining duplicate variant_id rows into one.
        campaign_stats fields (sent, in_queue, opened, replied, bounced, clicked)
        are per-campaign aggregates — identical across rows for the same variant,
        so take MAX. booked comes from per-lead events and should be summed."""
        from dataclasses import replace as _replace
        merged: dict[str, Any] = {}
        for v in vs:
            vid = v.variant_id
            if vid not in merged:
                merged[vid] = v
            else:
                m = merged[vid]
                merged[vid] = _replace(
                    m if m.in_queue >= v.in_queue else v,
                    sent=max(m.sent, v.sent),
                    in_queue=max(m.in_queue, v.in_queue),
                    opened=max(m.opened, v.opened),
                    clicked=max(m.clicked, v.clicked),
                    replied=max(m.replied, v.replied),
                    bounced=max(m.bounced, v.bounced),
                    booked=m.booked + v.booked,
                )
        return list(merged.values())

    # events_synced = True only when per-lead events exist.
    # campaign_stats (campaign-level totals) drives the Variant Performance table
    # correctly, but the ICP matrix needs per-lead events to show per-ICP rates.
    # Setting events_synced based solely on event_count makes the "Sync" banner
    # appear whenever the ICP matrix would show 0% rates.
    try:
        _econn = sqlite3.connect(str(db_path))
        event_count = _econn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        try:
            cs_count = _econn.execute(
                "SELECT COUNT(*) FROM campaign_stats"
            ).fetchone()[0]
        except Exception:
            cs_count = 0
        _econn.close()
    except Exception:
        event_count = 0
        cs_count = 0

    return JSONResponse(
        {
            "test_id": test["id"],
            "primary_metric": primary,
            "min_per_variant": min_per,
            "variants": [variant_to_dict(v) for v in sorted(_merge_variants(variants), key=lambda v: getattr(v, primary), reverse=True)],
            "frameworks": [framework_to_dict(f) for f in sorted(frameworks, key=lambda f: getattr(f, primary), reverse=True)],
            "heatmap": [cell_to_dict(c) for c in heatmap_cells],
            "icp_heatmap": [cell_to_dict(c) for c in icp_cells],
            "significance": sig,
            "cost": cost,
            "total_sent":     total_sent,      # emails delivered
            "total_in_queue": total_in_queue,  # leads added to SmartLead
            "total_replied":  total_replied,
            "total_booked":   total_booked,
            "blended_reply_rate": (total_replied / total_sent * 100) if total_sent else 0,
            # events_synced: True only when per-lead events exist (enables ICP rates).
            # campaign_stats alone is enough for the Variant table but NOT the ICP matrix.
            "events_synced": event_count > 0,
        }
    )


@app.post("/api/analytics/sync")
async def api_analytics_sync() -> JSONResponse:
    """Pull per-lead engagement stats from SmartLead API into the events table.

    Call this whenever the dashboard shows zero open/reply rates. SmartLead
    webhooks require a public URL; on localhost this endpoint is the fallback.
    """
    from src.ai_cold_email.smartlead.stats_sync import sync_all_campaigns
    from src.utils.ledger import Ledger
    settings = load_settings()
    ledger = Ledger("ledger.sqlite")
    result = await sync_all_campaigns(settings, ledger)
    return JSONResponse(result)


@app.get("/api/analytics/subject-lines")
async def api_subject_lines(min_sent: int = Query(3, ge=1)) -> JSONResponse:
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
                    "is_grouped":   r.is_grouped,
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


@app.get("/api/leads/export")
async def api_leads_export():
    """Download all leads as a CSV with their current status."""
    import csv, io
    from fastapi.responses import Response as _Response
    db = _get_db()
    if not db.exists():
        return _Response(content="", media_type="text/csv")

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT l.email, l.first_name, l.last_name, l.company, l.role,
               l.status, l.variant_id, l.completed_at, l.error
        FROM leads l
        ORDER BY l.completed_at DESC NULLS LAST
    """).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email","first_name","last_name","company","role","status","variant","completed_at","error"])
    for r in rows:
        writer.writerow([r["email"], r["first_name"] or "", r["last_name"] or "",
                         r["company"] or "", r["role"] or "", r["status"] or "",
                         r["variant_id"] or "", r["completed_at"] or "", r["error"] or ""])

    return _Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@app.get("/api/export/sms-leads")
async def api_export_sms_leads(csv_path: Optional[str] = Query(None)) -> Any:
    """
    Export a master SMS tracking sheet as a downloadable CSV.

    Columns per lead:
      first_name, last_name, company, role, email
      best_phone           — primary SMS number (highest-priority valid phone)
      total_valid_phones   — how many verified numbers this lead has
      all_valid_phones     — all verified numbers, pipe-separated
      market               — ICP (coach / agency / consultant / financial_advisor / msp)
      email_status         — from email ledger (sent / dry_run / skipped / failed / not_processed)
      sms_status           — from SMS ledger (not_started / ready / sent / replied / opted_out / failed)
      sms_variant          — which SMS-V1..V6 was assigned
      sms_sent_at          — timestamp the SMS was delivered (blank if not yet sent)
      can_contact          — YES/NO — has a valid phone AND not already sent/opted_out
      notes                — human-readable summary line

    Rows are sorted: replied first, then sent, then ready, then not_started, then ineligible.
    """
    import csv as _csv
    import io
    from datetime import datetime as _dt
    from fastapi.responses import Response as _Resp

    # ── 1. Resolve the CSV to read ─────────────────────────────────────────────
    if not csv_path:
        db_conn = sqlite3.connect(str(DB_PATH))
        row = db_conn.execute(
            "SELECT csv_path FROM csv_uploads ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
        db_conn.close()
        if not row:
            return _Resp(content="No CSV uploaded yet", media_type="text/plain", status_code=400)
        csv_path = row[0]

    if not Path(csv_path).exists():
        return _Resp(content=f"CSV not found: {csv_path}", media_type="text/plain", status_code=404)

    # ── 2. Read + extract phones ───────────────────────────────────────────────
    from src.ingestion.csv_reader import read_leads
    from src.sms.pipeline import extract_skiptrace_wireless_phone

    try:
        leads = read_leads(Path(csv_path))
    except Exception as e:
        return _Resp(content=f"Could not read CSV: {e}", media_type="text/plain", status_code=500)

    # ── 3. Build email-ledger lookup  { lead_id → {status, market, variant_id} } ──
    email_lookup: dict[str, dict] = {}
    try:
        ec = sqlite3.connect(str(DB_PATH))
        ec.row_factory = sqlite3.Row
        for r in ec.execute(
            "SELECT lead_id, status, vertical, motion, variant_id FROM leads"
        ).fetchall():
            email_lookup[r["lead_id"]] = {
                "email_status": r["status"] or "not_processed",
                "variant_id":   r["variant_id"] or "",
            }
        # Also pull market from analysis stage
        for r in ec.execute(
            "SELECT lead_id, data_json FROM stages WHERE stage_name='analysis'"
        ).fetchall():
            if r["lead_id"] in email_lookup:
                try:
                    import json as _json
                    ana = _json.loads(r["data_json"])
                    email_lookup[r["lead_id"]]["market"] = ana.get("market", "")
                except Exception:
                    pass
        ec.close()
    except Exception:
        pass

    # ── 4. Build SMS-ledger lookup  { phone → {status, variant_id, sent_at} } ──
    sms_phone_lookup: dict[str, dict] = {}
    try:
        settings = load_settings()
        sms_db = settings.sms.get("db_path", "data/sms_ledger.sqlite")
        if Path(sms_db).exists():
            sc = sqlite3.connect(sms_db)
            sc.row_factory = sqlite3.Row
            for r in sc.execute(
                "SELECT phone, status, variant_id, updated_at FROM sms_leads"
            ).fetchall():
                # Keep highest-priority status per phone
                existing = sms_phone_lookup.get(r["phone"])
                priority = {"replied": 0, "booked": 0, "sent": 1, "opted_out": 2, "ready": 3, "failed": 4}
                new_p = priority.get(r["status"] or "", 9)
                old_p = priority.get((existing or {}).get("sms_status", ""), 9) if existing else 9
                if not existing or new_p < old_p:
                    sms_phone_lookup[r["phone"]] = {
                        "sms_status":  r["status"] or "not_started",
                        "sms_variant": r["variant_id"] or "",
                        "sms_sent_at": (
                            _dt.fromtimestamp(r["updated_at"]).strftime("%Y-%m-%d %H:%M")
                            if r["updated_at"] and r["status"] in ("sent", "replied", "booked")
                            else ""
                        ),
                    }
            sc.close()
    except Exception:
        pass

    _SMS_SENT_STATUSES = {"sent", "replied", "booked", "opted_out"}

    # ── 5. Build rows ──────────────────────────────────────────────────────────
    rows: list[dict] = []
    for lead in leads:
        phones       = extract_skiptrace_wireless_phone(lead)
        lead_id      = lead["lead_id"]
        email_info   = email_lookup.get(lead_id, {})
        email_status = email_info.get("email_status", "not_processed")
        market       = email_info.get("market") or lead.get("market") or ""

        # Best SMS status across all phones for this lead
        best_sms: dict = {}
        for ph in phones:
            info = sms_phone_lookup.get(ph, {})
            if not best_sms:
                best_sms = info
            else:
                priority = {"replied": 0, "booked": 0, "sent": 1, "opted_out": 2, "ready": 3, "failed": 4}
                if priority.get(info.get("sms_status", ""), 9) < priority.get(best_sms.get("sms_status", ""), 9):
                    best_sms = info

        sms_status  = best_sms.get("sms_status", "not_started" if phones else "no_phone")
        sms_variant = best_sms.get("sms_variant", "")
        sms_sent_at = best_sms.get("sms_sent_at", "")

        already_sent = sms_status in _SMS_SENT_STATUSES
        can_contact  = "YES" if (phones and not already_sent) else "NO"

        if sms_status == "replied":
            notes = "Replied — follow up"
        elif sms_status == "booked":
            notes = "Booked — meeting scheduled"
        elif sms_status == "opted_out":
            notes = "Opted out — do not contact"
        elif sms_status == "sent":
            notes = "SMS sent — awaiting reply"
        elif sms_status == "ready":
            notes = "Generated — ready to send"
        elif sms_status == "no_phone":
            notes = "No valid phone number — email only"
        elif sms_status == "failed":
            notes = "Send failed — can retry"
        else:
            notes = "Not yet contacted via SMS"

        rows.append({
            "first_name":         lead.get("first_name", ""),
            "last_name":          lead.get("last_name", ""),
            "company":            lead.get("company", ""),
            "role":               lead.get("role", ""),
            "email":              lead.get("email", ""),
            "best_phone":         phones[0] if phones else "",
            "total_valid_phones": len(phones),
            "all_valid_phones":   " | ".join(phones),
            "market":             market,
            "email_status":       email_status,
            "sms_status":         sms_status,
            "sms_variant":        sms_variant,
            "sms_sent_at":        sms_sent_at,
            "can_contact_sms":    can_contact,
            "notes":              notes,
        })

    # ── 6. Sort: replied → sent → ready → not_started → no_phone / opted_out ──
    _sort_order = {
        "replied": 0, "booked": 0,
        "sent": 1,
        "ready": 2,
        "not_started": 3,
        "failed": 4,
        "opted_out": 5,
        "no_phone": 6,
    }
    rows.sort(key=lambda r: _sort_order.get(r["sms_status"], 9))

    # ── 7. Write CSV ───────────────────────────────────────────────────────────
    buf = io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else [])
    writer.writeheader()
    writer.writerows(rows)

    # Summary counts in a comment block at the top
    counts = {}
    for r in rows:
        counts[r["sms_status"]] = counts.get(r["sms_status"], 0) + 1
    can_sms  = sum(1 for r in rows if r["can_contact_sms"] == "YES")
    total    = len(rows)

    summary_lines = [
        f"# SMS Lead Tracking Export — generated {_dt.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Total leads: {total}",
        f"# Can contact via SMS: {can_sms}",
        f"# Already sent: {counts.get('sent', 0) + counts.get('replied', 0) + counts.get('booked', 0)}",
        f"# Replied: {counts.get('replied', 0) + counts.get('booked', 0)}",
        f"# Ready to send: {counts.get('ready', 0)}",
        f"# Not yet started: {counts.get('not_started', 0)}",
        f"# No valid phone: {counts.get('no_phone', 0)}",
        f"# Opted out: {counts.get('opted_out', 0)}",
        "#",
    ]
    final_content = "\n".join(summary_lines) + "\n" + buf.getvalue()

    fname = f"sms_leads_{_dt.now().strftime('%Y%m%d_%H%M')}.csv"
    return _Resp(
        content=final_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


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


def _backfill_csv_upload_ids(conn: sqlite3.Connection) -> None:
    """One-time backfill: for any lead whose csv_upload_id is NULL, assign it
    by reading the CSV file for each upload and matching on lead_id (sha256 hash
    of the email — same algorithm used by csv_reader._lead_id)."""
    import csv as _csv, hashlib, io as _io

    def _compute_lead_id(email: str) -> str:
        return hashlib.sha256(email.encode()).hexdigest()[:16]

    try:
        # Fast path: nothing to backfill
        unset = conn.execute(
            "SELECT 1 FROM leads WHERE csv_upload_id IS NULL LIMIT 1"
        ).fetchone()
        if not unset:
            return

        uploads = conn.execute(
            "SELECT id, csv_path FROM csv_uploads ORDER BY id"
        ).fetchall()
        for upload in uploads:
            upload_id = upload["id"]
            csv_path  = upload["csv_path"]
            if not Path(csv_path).exists():
                continue
            try:
                content = Path(csv_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            reader = _csv.DictReader(_io.StringIO(content))
            lead_ids: list[str] = []
            for row in reader:
                norm = {k.strip().upper(): (v or "").strip() for k, v in row.items()}
                # Prefer UUID (same priority as csv_reader.read_leads)
                identifier = norm.get("UUID", "").strip()
                if not identifier:
                    e = (
                        norm.get("BUSINESS_EMAIL")
                        or norm.get("BUSINESS_VERIFIED_EMAILS")
                        or norm.get("EMAIL", "")
                    )
                    identifier = e.split(",")[0].strip().lower()
                if identifier:
                    lead_ids.append(_compute_lead_id(identifier))
            if not lead_ids:
                continue
            # Update in batches of 500 to avoid hitting SQLite's variable limit
            batch = 500
            for i in range(0, len(lead_ids), batch):
                chunk = lead_ids[i : i + batch]
                placeholders = ",".join("?" * len(chunk))
                conn.execute(
                    f"""
                    UPDATE leads SET csv_upload_id = ?
                    WHERE csv_upload_id IS NULL
                      AND lead_id IN ({placeholders})
                    """,
                    (upload_id, *chunk),
                )
        conn.commit()
    except Exception as exc:
        log.warning("csv_upload_id backfill skipped: %s", exc)


@app.get("/api/pipeline/csv-history")
async def api_csv_history() -> JSONResponse:
    """Return all uploaded CSVs with live sent/pending counts, newest first."""
    db = _get_db()
    if not db.exists():
        return JSONResponse({"uploads": [], "total_new_leads": 0})
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        # Ensure csv_upload_id column exists (migration for older DBs)
        try:
            conn.execute("ALTER TABLE leads ADD COLUMN csv_upload_id INTEGER")
            conn.commit()
        except Exception:
            pass  # column already exists

        # Backfill csv_upload_id for existing leads (idempotent — skips already-set rows)
        _backfill_csv_upload_ids(conn)

        rows = conn.execute(
            """
            SELECT
                cu.id, cu.filename, cu.csv_path, cu.uploaded_at,
                cu.lead_count, cu.new_leads, cu.duplicate_leads,
                COUNT(CASE WHEN l.status IN ('sent','success') THEN 1 END) AS sent_count,
                COUNT(CASE WHEN l.status = 'dry_run' THEN 1 END)           AS pending_count,
                COUNT(CASE WHEN l.status = 'failed'  THEN 1 END)           AS failed_count
            FROM csv_uploads cu
            LEFT JOIN leads l ON l.csv_upload_id = cu.id
            GROUP BY cu.id
            ORDER BY cu.uploaded_at DESC
            LIMIT 50
            """
        ).fetchall()
        uploads = [dict(r) for r in rows]
        total_new = sum(u["new_leads"] for u in uploads)
    except Exception as exc:
        log.warning("csv-history query failed: %s", exc)
        uploads = []
        total_new = 0
    finally:
        conn.close()
    return JSONResponse({"uploads": uploads, "total_new_leads": total_new})


@app.get("/api/pipeline/master-stats")
async def api_pipeline_master_stats() -> JSONResponse:
    """Master lead database — aggregate cold-email stats across ALL uploaded CSVs.

    Sums lead_count from csv_uploads and live status counts from the leads table.
    Cross-CSV deduplication is automatic: the same email in two CSVs produces a
    single lead_id in the leads table and is only ever processed once.
    """
    db = _get_db()
    if not db.exists():
        return JSONResponse({
            "total_leads": 0, "total_sent": 0, "total_personalised": 0,
            "total_failed": 0, "total_skipped": 0, "total_remaining": 0,
            "uploads_count": 0,
        })
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        _backfill_csv_upload_ids(conn)
        rows = conn.execute(
            """
            SELECT
                cu.lead_count,
                COUNT(CASE WHEN l.status IN ('sent','success') THEN 1 END) AS sent_count,
                COUNT(CASE WHEN l.status = 'dry_run'  THEN 1 END)          AS personalised_count,
                COUNT(CASE WHEN l.status = 'failed'   THEN 1 END)          AS failed_count,
                COUNT(CASE WHEN l.status = 'skipped'  THEN 1 END)          AS skipped_count
            FROM csv_uploads cu
            LEFT JOIN leads l ON l.csv_upload_id = cu.id
            GROUP BY cu.id
            """
        ).fetchall()
        per_csv        = [dict(r) for r in rows]
        total_leads    = sum(r["lead_count"]         for r in per_csv)
        total_sent     = sum(r["sent_count"]         for r in per_csv)
        total_pers     = sum(r["personalised_count"] for r in per_csv)
        total_failed   = sum(r["failed_count"]       for r in per_csv)
        total_skipped  = sum(r["skipped_count"]      for r in per_csv)
        total_remaining = max(0, total_leads - total_sent - total_pers - total_failed - total_skipped)
    except Exception as exc:
        log.warning("api_pipeline_master_stats: %s", exc)
        return JSONResponse({"total_leads": 0, "error": str(exc)})
    finally:
        conn.close()

    return JSONResponse({
        "total_leads":        total_leads,
        "total_sent":         total_sent,
        "total_personalised": total_pers,
        "total_failed":       total_failed,
        "total_skipped":      total_skipped,
        "total_remaining":    total_remaining,
        "uploads_count":      len(per_csv),
    })


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

    # Only leads that Phase 2 will actually push: status='dry_run' + no smartlead stage yet.
    # Excluding failed/skipped/NULL so the count shown exactly matches what gets sent.
    rows = conn.execute(
        """
        SELECT l.lead_id, h.data_json AS hosting_json
        FROM   leads l
        LEFT  JOIN stages h  ON h.lead_id  = l.lead_id AND h.stage_name  = 'hosting'
        LEFT  JOIN stages sm ON sm.lead_id = l.lead_id AND sm.stage_name = 'smartlead'
        WHERE  l.status = 'dry_run'
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


@app.post("/api/campaigns/daily-limits")
async def api_set_daily_limits(body: dict[str, Any]) -> JSONResponse:
    """Apply per-day send limits across all 9 variant campaigns so they share
    at most `total_daily` sends per day (default 50).

    Distribution is ceil-rounded to the first N campaigns so the total is exact.
    """
    from src.ai_cold_email.smartlead.client import apply_daily_limits
    total_daily = int(body.get("total_daily", 900))
    if total_daily < 1 or total_daily > 100_000:
        raise HTTPException(status_code=400, detail="total_daily must be between 1 and 10000")
    settings = load_settings()
    result = await apply_daily_limits(settings, total_daily=total_daily)
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
            "dry_run_count":    0,
            "db_sent":          0,
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
                    SUM(CASE WHEN status IN ('sent','success') THEN 1 ELSE 0 END) AS sent,
                    SUM(CASE WHEN status = 'dry_run' THEN 1 ELSE 0 END)          AS dry_run_count,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END)          AS skipped,
                    SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END)          AS failed
                FROM leads
                """
            ).fetchone()
            cost_row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM costs"
            ).fetchone()
            conn.close()  # single close — no second conn.close() below

            if row:
                _pipeline_status["sent"]          = row[1] or 0   # actually pushed to SmartLead
                _pipeline_status["dry_run_count"]  = row[2] or 0   # personalised, awaiting push
                _pipeline_status["db_sent"]        = row[1] or 0   # alias — same value, kept for frontend compat
                _pipeline_status["skipped"]        = row[3] or 0
                _pipeline_status["failed"]         = row[4] or 0
                # processed = everything the pipeline has ever "touched"
                _pipeline_status["processed"] = (
                    (_pipeline_status["sent"]         or 0)
                    + (_pipeline_status["dry_run_count"] or 0)
                    + (_pipeline_status["skipped"]    or 0)
                    + (_pipeline_status["failed"]     or 0)
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


# ─── SMS Pipeline ────────────────────────────────────────────────────────────

_sms_pipeline_task: asyncio.Task | None = None
_sms_pipeline_status: dict[str, Any] = {
    "running":       False,
    "total":         0,
    "run_generated": 0,   # SMS bodies generated in this Phase 1 run
    "run_sent":      0,   # SMS messages sent in this Phase 2 run
    "run_failed":    0,
    "run_skipped":   0,
    "db_generated":  0,   # all-time ready-to-send leads
    "db_sent":       0,   # all-time sent leads
    "recent_activity": [],
    "start_time":    None,
    "elapsed_seconds": None,
    "cost_usd":      0.0,
    "last_error":    None,
}


@app.post("/api/sms/pipeline/run")
async def api_sms_pipeline_run(body: dict[str, Any]) -> JSONResponse:
    """Start the SMS pipeline.

    dry_run=True  → Phase 1: generate SMS bodies (nothing sent).
    dry_run=False → Phase 2: send all ready leads via Twilio.
    """
    global _sms_pipeline_task, _sms_pipeline_status

    if _sms_pipeline_task and not _sms_pipeline_task.done():
        raise HTTPException(status_code=409, detail="SMS pipeline already running")

    csv_path  = body.get("csv_path")
    dry_run   = bool(body.get("dry_run", True))
    batch_size = int(body.get("batch_size", 0))

    if dry_run:
        if not csv_path or not Path(csv_path).exists():
            raise HTTPException(status_code=400, detail="csv_path is required for Phase 1")

    # Reset status
    _sms_pipeline_status.update({
        "running":       True,
        "total":         0,
        "run_generated": 0,
        "run_sent":      0,
        "run_failed":    0,
        "run_skipped":   0,
        "recent_activity": [],
        "start_time":    datetime.utcnow().isoformat(),
        "elapsed_seconds": 0,
        "cost_usd":      0.0,
        "last_error":    None,
    })

    async def _run():
        global _sms_pipeline_status
        t0 = time.monotonic()
        try:
            from src.sms.pipeline import run_sms_pipeline
            settings = load_settings()
            await run_sms_pipeline(
                csv_path   = Path(csv_path) if csv_path else Path(""),
                dry_run    = dry_run,
                batch_size = batch_size,
                settings   = settings,
                email_db_path = DB_PATH,
                status_ref = _sms_pipeline_status,
            )
        except asyncio.CancelledError:
            log.info("SMS pipeline cancelled")
        except Exception as e:
            log.error("SMS pipeline error: %s", e, exc_info=True)
            _sms_pipeline_status["last_error"] = str(e)
        finally:
            _sms_pipeline_status["running"]          = False
            _sms_pipeline_status["elapsed_seconds"]  = round(time.monotonic() - t0)
            # Refresh all-time DB counts
            try:
                from src.sms.ledger import SMSLedger
                _settings = load_settings()
                _db = _settings.sms.get("db_path", "data/sms_ledger.sqlite")
                _l  = SMSLedger(path=_db)
                kpi = _l.kpi_summary()
                _sms_pipeline_status["db_generated"] = _l.count_leads(status="ready")
                _sms_pipeline_status["db_sent"]      = kpi.get("sent") or 0
            except Exception:
                pass

    _sms_pipeline_task = asyncio.create_task(_run())
    return JSONResponse({"started": True, "dry_run": dry_run})


@app.post("/api/sms/pipeline/stop")
async def api_sms_pipeline_stop() -> JSONResponse:
    global _sms_pipeline_task, _sms_pipeline_status
    if _sms_pipeline_task and not _sms_pipeline_task.done():
        _sms_pipeline_task.cancel()
    _sms_pipeline_status["running"] = False
    return JSONResponse({"stopped": True})


@app.get("/api/sms/pipeline/status")
async def api_sms_pipeline_status() -> JSONResponse:
    global _sms_pipeline_status
    # Refresh all-time DB counts on every poll
    try:
        from src.sms.ledger import SMSLedger
        settings = load_settings()
        db = settings.sms.get("db_path", "data/sms_ledger.sqlite")
        if Path(db).exists():
            ledger = SMSLedger(path=db)
            kpi    = ledger.kpi_summary()
            _sms_pipeline_status["db_generated"] = ledger.count_leads(status="ready")
            _sms_pipeline_status["db_sent"]      = kpi.get("sent") or 0
    except Exception:
        pass

    if _sms_pipeline_status.get("start_time") and _sms_pipeline_status["running"]:
        try:
            _sms_pipeline_status["elapsed_seconds"] = round(
                time.monotonic()
                - time.mktime(
                    datetime.fromisoformat(_sms_pipeline_status["start_time"]).timetuple()
                )
            )
        except Exception:
            pass

    return JSONResponse(_sms_pipeline_status)


@app.get("/api/sms/readiness")
async def api_sms_readiness() -> JSONResponse:
    """How many SMS leads are ready to send vs. already sent."""
    try:
        from src.sms.ledger import SMSLedger
        settings = load_settings()
        db = settings.sms.get("db_path", "data/sms_ledger.sqlite")
        if not Path(db).exists():
            return JSONResponse({"ready_to_send": 0, "already_sent": 0, "total": 0})
        ledger = SMSLedger(path=db)
        kpi    = ledger.kpi_summary()
        return JSONResponse({
            "ready_to_send": ledger.count_leads(status="ready"),
            "already_sent":  kpi.get("sent")    or 0,
            "replied":       kpi.get("replied") or 0,
            "total":         kpi.get("total")   or 0,
        })
    except Exception as e:
        return JSONResponse({"ready_to_send": 0, "already_sent": 0, "total": 0, "error": str(e)})


# ── SMS phone-scan cache (5-min TTL — avoids re-reading large CSV files) ──────
_sms_master_cache: dict[str, Any] | None = None
_sms_master_cache_ts: float = 0.0
_SMS_MASTER_TTL: float = 300.0


def _scan_csv_phones(csv_path: str) -> tuple[int, int]:
    """Return (leads_with_wireless_phone, dnc_excluded) for one CSV file.

    Mirrors the SMS pipeline exactly: only SKIPTRACE_WIRELESS_NUMBERS counts,
    and SKIPTRACE_DNC=Y excludes the lead.

    Returns:
        with_phone  — leads with a valid wireless number that can be contacted
        dnc_only    — leads that had a wireless number but SKIPTRACE_DNC=Y
    """
    import csv as _csv
    from src.sms.pipeline import extract_skiptrace_wireless_phone
    from src.ingestion.csv_reader import _detect_format

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader     = _csv.DictReader(f)
            headers    = reader.fieldnames or []
            fmt        = _detect_format(headers)
            with_phone = 0
            dnc_only   = 0
            for row in reader:
                if fmt == "skiptrace":
                    wireless = (row.get("SKIPTRACE_WIRELESS_NUMBERS") or "").strip()
                    dnc      = (row.get("SKIPTRACE_DNC") or "").strip().upper()
                    mapped   = {
                        "skiptrace_wireless_raw": wireless,
                        "skiptrace_dnc_raw":      dnc,
                    }
                else:
                    # Native format doesn't have skiptrace columns — 0 sendable
                    mapped = {k: (v or "") for k, v in row.items()}

                phones = extract_skiptrace_wireless_phone(mapped)
                if phones:
                    with_phone += 1

        return with_phone, dnc_only
    except Exception as exc:
        log.warning("_scan_csv_phones(%s): %s", csv_path, exc)
        return 0, 0


@app.get("/api/sms/master-stats")
async def api_sms_master_stats() -> JSONResponse:
    """Master SMS pool: total leads across all uploads, phone-validated and DNC-filtered.

    Scans every uploaded CSV with the same phone-extraction logic the SMS pipeline
    uses, so 'leads_with_phone' exactly matches what Twilio would receive.
    Result is cached for 5 minutes — subsequent loads are instant.
    The same lead in two CSVs is counted once in sms_leads (dedup by lead_id+phone).
    """
    global _sms_master_cache, _sms_master_cache_ts

    now = time.monotonic()
    if _sms_master_cache is not None and (now - _sms_master_cache_ts) < _SMS_MASTER_TTL:
        return JSONResponse(_sms_master_cache)

    db          = _get_db()
    settings    = load_settings()
    sms_db_path = settings.sms.get("db_path", "data/sms_ledger.sqlite")

    # ── 1. Total leads + CSV paths from upload history ─────────────────────────
    total_leads  = 0
    csv_paths: list[str] = []
    if db.exists():
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT lead_count, csv_path FROM csv_uploads ORDER BY uploaded_at DESC"
            ).fetchall()
            for r in rows:
                total_leads += r["lead_count"]
                if r["csv_path"] and Path(r["csv_path"]).exists():
                    csv_paths.append(r["csv_path"])
        except Exception as exc:
            log.warning("api_sms_master_stats DB: %s", exc)
        finally:
            conn.close()

    # ── 2. Phone-validation scan across all CSV files ──────────────────────────
    leads_with_phone = 0
    dnc_excluded     = 0
    for path in csv_paths:
        wp, dc = _scan_csv_phones(path)
        leads_with_phone += wp
        dnc_excluded     += dc

    # ── 3. SMS ledger stats ─────────────────────────────────────────────────────
    sms_sent = sms_ready = sms_opted_out = sms_failed = 0
    if Path(sms_db_path).exists():
        try:
            from src.sms.ledger import SMSLedger
            sms_ledger    = SMSLedger(path=sms_db_path)
            kpi           = sms_ledger.kpi_summary()
            sms_sent      = kpi.get("sent")      or 0
            sms_ready     = sms_ledger.count_leads(status="ready")
            sms_opted_out = kpi.get("opted_out") or 0
            sms_failed    = kpi.get("failed")    or 0
        except Exception as exc:
            log.warning("api_sms_master_stats ledger: %s", exc)

    result: dict[str, Any] = {
        "total_leads":      total_leads,
        "leads_with_phone": leads_with_phone,
        "dnc_excluded":     dnc_excluded,
        "sms_sent":         sms_sent,
        "sms_ready":        sms_ready,
        "sms_opted_out":    sms_opted_out,
        "sms_failed":       sms_failed,
        "net_sendable":     max(0, leads_with_phone - sms_sent - sms_opted_out),
        "uploads_count":    len(csv_paths),
        "scan_complete":    True,
    }
    _sms_master_cache    = result
    _sms_master_cache_ts = now
    return JSONResponse(result)


@app.get("/api/sms/icp-matrix")
async def api_sms_icp_matrix() -> JSONResponse:
    """ICP × SMS-Variant reply-rate matrix for the dashboard heatmap.

    The sms_leads table stores the 'vertical' (ICP) for every lead at generation
    time, so no cross-database join is needed.  Groups by (vertical, variant_id)
    and returns sent + replied counts with a calculated reply_rate.
    """
    settings    = load_settings()
    sms_db_path = settings.sms.get("db_path", "data/sms_ledger.sqlite")

    if not Path(sms_db_path).exists():
        return JSONResponse({"cells": []})
    try:
        conn = sqlite3.connect(sms_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(vertical), ''), 'Unknown')   AS col_key,
                COALESCE(NULLIF(TRIM(variant_id), ''), 'Unknown') AS row_key,
                COUNT(*)                                           AS sent,
                SUM(CASE WHEN status IN ('replied','booked') THEN 1 ELSE 0 END) AS replied
            FROM sms_leads
            WHERE status IN ('sent','replied','booked','opted_out')
            GROUP BY col_key, row_key
            HAVING sent >= 1
            ORDER BY col_key, row_key
            """
        ).fetchall()
        conn.close()
        cells = []
        for r in rows:
            sent    = r["sent"]    or 0
            replied = r["replied"] or 0
            cells.append({
                "col_key":    r["col_key"],
                "row_key":    r["row_key"],
                "sent":       sent,
                "replied":    replied,
                "reply_rate": replied / sent if sent > 0 else 0.0,
            })
        return JSONResponse({"cells": cells})
    except Exception as exc:
        log.warning("api_sms_icp_matrix: %s", exc)
        return JSONResponse({"cells": [], "error": str(exc)})


@app.post("/api/sms/reset-failed")
async def api_sms_reset_failed() -> JSONResponse:
    """Reset all sms_leads with status='failed' back to 'pending' so they are
    picked up on the next pipeline run.  Returns the count of rows reset."""
    try:
        db_path = Path("data/sms_ledger.sqlite")
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute(
            "UPDATE sms_leads SET status='pending', error=NULL, updated_at=? WHERE status='failed'",
            (time.time(),),
        )
        reset_count = cur.rowcount
        conn.commit()
        conn.close()
        log.info("Reset %d failed SMS leads to pending", reset_count)
        return JSONResponse({"ok": True, "reset": reset_count})
    except Exception as exc:
        log.warning("api_sms_reset_failed: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/sms/reconcile-costs")
async def api_sms_reconcile_costs() -> JSONResponse:
    """Fetch actual Twilio prices for recently-sent messages whose price is still null.

    Twilio often returns price=null at message-creation time; the price is
    populated only once the message reaches a final delivery status (delivered,
    failed, undelivered).  Call this endpoint 5-10 minutes after a send run to
    pull accurate billing data for up to 100 recent messages.

    The endpoint is idempotent — already-priced messages are skipped.
    """
    try:
        settings = load_settings()
        ledger   = _get_sms_ledger()
        sids     = ledger.fetch_unsettled_sids(limit=100)

        if not sids:
            return JSONResponse({"ok": True, "checked": 0, "updated": 0,
                                 "message": "No unsettled messages to reconcile"})

        from twilio.rest import Client
        client  = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        updated = 0
        errors: list[str] = []

        for sid in sids:
            try:
                msg        = await asyncio.to_thread(lambda s=sid: client.messages(s).fetch())
                raw_price  = getattr(msg, "price", None)
                price_unit = getattr(msg, "price_unit", None) or "USD"
                if raw_price is not None:
                    ledger.set_message_price(sid, raw_price, price_unit)
                    updated += 1
            except Exception as exc:
                errors.append(f"{sid}: {exc}")

        log.info("SMS cost reconciliation: checked=%d updated=%d errors=%d",
                 len(sids), updated, len(errors))
        return JSONResponse({
            "ok":      True,
            "checked": len(sids),
            "updated": updated,
            "errors":  errors[:10],   # cap error list to avoid huge responses
        })

    except Exception as exc:
        log.error("api_sms_reconcile_costs: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/sms/sync")
async def api_sms_sync_now() -> JSONResponse:
    """Manually trigger a Twilio inbound sync right now.

    Normally the background worker does this every 60 s automatically.
    This lets the user force an immediate check from the dashboard.
    """
    try:
        from src.sms.twilio_sync import sync_once
        from src.sms.ledger import SMSLedger
        settings = load_settings()
        db = settings.sms.get("db_path", "data/sms_ledger.sqlite")
        ledger = SMSLedger(path=db)
        result = await sync_once(settings, ledger)
        return JSONResponse({"ok": True, **result})
    except Exception as e:
        log.error("Manual Twilio sync failed: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/sms/sync/status")
async def api_sms_sync_status() -> JSONResponse:
    """Return the last sync timestamp and result."""
    try:
        from src.sms.ledger import SMSLedger
        settings = load_settings()
        db = settings.sms.get("db_path", "data/sms_ledger.sqlite")
        if not Path(db).exists():
            return JSONResponse({"last_sync_at": None, "last_result": None, "worker_running": False})
        ledger = SMSLedger(path=db)
        return JSONResponse({
            "last_sync_at":     ledger.get_sync_state("last_sync_at"),
            "last_result":      ledger.get_sync_state("last_sync_result"),
            "worker_running":   _twilio_sync_task is not None and not _twilio_sync_task.done(),
            "poll_interval_s":  60,
        })
    except Exception as e:
        return JSONResponse({"last_sync_at": None, "error": str(e)})


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
        sent      = raw_kpis.get("sent")       or 0
        generated = raw_kpis.get("generated")  or 0
        replied   = raw_kpis.get("replied")    or 0
        opted     = raw_kpis.get("opted_out")  or 0
        booked    = raw_kpis.get("booked")     or 0
        ai_cost   = raw_kpis.get("total_ai_cost_usd",     0.0)
        tw_cost   = raw_kpis.get("total_twilio_cost_usd", 0.0)
        kpis = {
            "total_sent":             sent,       # actually delivered via Twilio
            "total_generated":        generated,  # bodies written (includes ready)
            "total_delivered":        sent,
            "total_replied":          replied,
            "total_opted_out":        opted,
            "total_booked":           booked,
            "blended_reply_rate":     round(replied / sent, 4) if sent else 0.0,
            "blended_opt_out_rate":   round(opted   / sent, 4) if sent else 0.0,
            # cost fields
            "total_ai_cost_usd":      round(ai_cost,          6),
            "total_twilio_cost_usd":  round(tw_cost,          6),
            "total_cost_usd":         round(ai_cost + tw_cost, 6),
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
    limit: int  = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),   # search: name / company / phone
) -> JSONResponse:
    """Paginated SMS leads list with per-status counts and last-message preview."""
    ledger = _get_sms_ledger()

    # Per-status badge counts (always across all statuses, ignoring current filter)
    all_statuses = ["ready", "sent", "replied", "booked", "opted_out", "failed"]
    status_counts = {s: ledger.count_leads(status=s) for s in all_statuses}
    status_counts["all"] = ledger.count_leads(status=None)

    leads = ledger.list_leads(status=status, limit=limit, offset=offset)
    total = ledger.count_leads(status=status)

    # Client-side search filter (simple contains match on name / company / phone)
    if q:
        q_lower = q.lower()
        leads = [
            l for l in leads
            if q_lower in (l.get("first_name") or "").lower()
            or q_lower in (l.get("last_name") or "").lower()
            or q_lower in (l.get("company") or "").lower()
            or q_lower in (l.get("phone") or "").lower()
        ]
        total = len(leads)

    # Enrich with last-message preview (outbound_pending excluded)
    for lead in leads:
        msgs = ledger.get_conversation(lead["lead_id"])
        inbound = [m for m in msgs if m["direction"] == "inbound"]
        lead["has_reply"]     = len(inbound) > 0
        lead["inbound_count"] = len(inbound)
        if msgs:
            last = msgs[-1]
            lead["last_message"]    = last["body"][:100]
            lead["last_message_at"] = last["sent_at"]
            lead["last_direction"]  = last["direction"]
        else:
            lead["last_message"]    = None
            lead["last_message_at"] = None
            lead["last_direction"]  = None

    return JSONResponse({"leads": leads, "total": total, "status_counts": status_counts})


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


# ─── Audience API ─────────────────────────────────────────────────────────────
# Stores AudienceLab.io CSV exports in a local SQLite database.
# Deduplication is global (by business_email), so appending multiple CSVs
# never inflates the lead count with the same contact twice.

def _audience_db() -> "AudienceLedger":
    from src.audience.ledger import AudienceLedger
    return AudienceLedger(path=str(Path("data/audience.sqlite")))


@app.post("/api/audience/upload")
async def api_audience_upload(file: UploadFile) -> JSONResponse:
    """
    Accept a CSV file, ingest into audience.sqlite for display, AND write new
    leads into the pipeline ledger (ledger.sqlite) so they are immediately
    available for the email-personalisation and SMS pipelines.

    Flow:
      1. Save raw file to data/input/  → pipelines can reference csv_path
      2. Ingest into audience.sqlite   → Audience tab display / search
      3. INSERT OR IGNORE into ledger.sqlite → pipeline dedup & lead pool
      4. Record in csv_uploads         → pipeline history + csv_path linkage

    Returns pipeline_new / pipeline_duplicates so the UI can tell the user
    how many leads are ready to personalise vs already in the system.
    """
    import csv, io
    from src.audience.ledger import AudienceLedger, map_csv_row

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    try:
        raw_bytes = await file.read()
        text = raw_bytes.decode("utf-8-sig")   # strip BOM if present
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    try:
        reader = csv.DictReader(io.StringIO(text))
        raw_rows = list(reader)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {exc}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # ── 1. Save raw file to data/input/ ─────────────────────────────────────
    # Both pipelines (email + SMS Phase 1) need a csv_path on disk.
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    dest.write_bytes(raw_bytes)
    csv_path_str = str(dest)

    # ── 2. Ingest into audience.sqlite (display / filtering / search) ────────
    db          = _audience_db()
    import_name = Path(file.filename).stem.replace("_", " ").replace("-", " ").title()
    import_id   = db.create_import(import_name, file.filename)
    mapped_rows = [m for m in (map_csv_row(r) for r in raw_rows) if m is not None]
    inserted, updated = db.ingest(import_id, mapped_rows)

    # ── 3. Write new leads into pipeline ledger (ledger.sqlite) ─────────────
    # INSERT OR IGNORE preserves any lead already in the pipeline at any status.
    # Leads with status=NULL are picked up by Phase 1 (Personalise) and the
    # SMS pipeline as "new unprocessed leads".
    pipeline_new = 0
    pipeline_dup = 0
    try:
        from src.ingestion.csv_reader import _lead_id as _compute_lead_id
        from src.utils.ledger import Ledger as _Ledger

        _pipeline = _Ledger(str(DB_PATH))

        # Register this upload in csv_uploads so pipeline history is accurate
        _upload_id = _pipeline.record_csv_upload(
            filename=file.filename,
            csv_path=csv_path_str,
            lead_count=len(raw_rows),
            new_leads=0,       # updated below once we know exact count
            duplicate_leads=0,
        )

        for _row in mapped_rows:
            # Prefer business_email; fall back to personal_email
            _email = (
                (_row.get("business_email") or "")
                or (_row.get("personal_email") or "")
            ).strip().lower()
            if not _email or "@" not in _email:
                continue

            _lead_id = _compute_lead_id(_email)

            # INSERT OR IGNORE: never touch a lead that is already in the pipeline
            _cur = _pipeline._execute(
                """
                INSERT OR IGNORE INTO leads
                    (lead_id, email, first_name, last_name,
                     company, website, role, vertical, csv_upload_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _lead_id,
                    _email,
                    (_row.get("first_name")     or ""),
                    (_row.get("last_name")      or ""),
                    (_row.get("company")        or ""),
                    (_row.get("company_domain") or ""),
                    (_row.get("job_title")      or ""),
                    (_row.get("industry")       or ""),
                    _upload_id,
                ),
            )
            if _cur.rowcount == 1:
                pipeline_new += 1
            else:
                pipeline_dup += 1

        _pipeline._conn.commit()

        # Patch csv_uploads with the real counts
        _pipeline._execute(
            "UPDATE csv_uploads SET new_leads=?, duplicate_leads=? WHERE id=?",
            (pipeline_new, pipeline_dup, _upload_id),
        )
        _pipeline._conn.commit()

    except Exception as _ex:
        log.warning("[audience upload] pipeline ledger sync failed: %s", _ex, exc_info=True)

    return JSONResponse({
        "import_id":           import_id,
        "filename":            file.filename,
        "total_rows":          len(raw_rows),
        "inserted":            inserted,
        "duplicates":          updated,
        "pipeline_new":        pipeline_new,
        "pipeline_duplicates": pipeline_dup,
        "csv_path":            csv_path_str,
    })


@app.get("/api/audience/imports")
async def api_audience_imports() -> JSONResponse:
    """List all uploaded audience CSVs."""
    db = _audience_db()
    imports = db.list_imports()
    return JSONResponse({"imports": imports})


@app.delete("/api/audience/imports/{import_id}")
async def api_audience_delete_import(import_id: int) -> JSONResponse:
    """Delete an import and its orphaned leads."""
    db = _audience_db()
    if not db.get_import(import_id):
        raise HTTPException(status_code=404, detail="Import not found.")
    db.delete_import(import_id)
    return JSONResponse({"deleted": True})


@app.patch("/api/audience/imports/{import_id}")
async def api_audience_rename_import(import_id: int, request: Request) -> JSONResponse:
    """Rename an audience import."""
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")
    db = _audience_db()
    db.rename_import(import_id, name)
    return JSONResponse({"ok": True})


@app.get("/api/audience/leads")
async def api_audience_leads(
    offset: int = 0,
    limit:  int = 100,
    search: str = "",
    has_phone:          bool = False,
    has_email:          bool = False,
    has_wireless:       bool = False,
    has_personal_email: bool = False,
    import_id: Optional[int] = None,
    # Business filters — comma-separated lists
    job_titles:     str = "",
    seniority:      str = "",
    departments:    str = "",
    company_names:  str = "",
    company_domains: str = "",
    industries:     str = "",
) -> JSONResponse:
    """Return paginated, filtered audience leads."""
    def _split(s: str) -> list[str]:
        return [v.strip() for v in s.split(",") if v.strip()] if s else []

    db = _audience_db()
    leads, total = db.list_leads(
        offset=offset, limit=min(limit, 500),
        search=search,
        has_phone=has_phone,
        has_email=has_email,
        has_wireless=has_wireless,
        has_personal_email=has_personal_email,
        import_id=import_id,
        job_titles=_split(job_titles),
        seniority=_split(seniority),
        departments=_split(departments),
        company_names=_split(company_names),
        company_domains=_split(company_domains),
        industries=_split(industries),
    )
    return JSONResponse({"leads": leads, "total": total, "offset": offset, "limit": limit})


@app.post("/api/audience/imports/{import_id}/webhook")
async def api_audience_set_webhook(import_id: int, request: Request) -> JSONResponse:
    """Save a webhook URL for a specific audience import."""
    body = await request.json()
    url  = (body.get("url") or "").strip()
    db   = _audience_db()
    if not db.get_import(import_id):
        raise HTTPException(status_code=404, detail="Import not found.")
    db.update_webhook(import_id, url)
    return JSONResponse({"ok": True})


@app.get("/api/audience/stats")
async def api_audience_stats() -> JSONResponse:
    """Return aggregate stats about the audience database."""
    db = _audience_db()
    return JSONResponse(db.stats())


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
