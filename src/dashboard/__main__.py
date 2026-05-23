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
DB_PATH = Path("data/ledger.sqlite")
UPLOAD_DIR = Path("data/input")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount /static for legacy Jinja2 assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Pipeline background task state ─────────────────────────────────────────

_pipeline_task: asyncio.Task | None = None
_pipeline_status: dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "start_time": None,
    "elapsed_seconds": None,
    "cost_usd": None,
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
               framework, recommended_angle, status, created_at, completed_at
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


@app.post("/api/pipeline/upload")
async def api_pipeline_upload(file: UploadFile = File(...)) -> JSONResponse:
    """Save uploaded CSV to data/input/ and return the path + row count."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files accepted")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Count data rows (header doesn't count)
    lines = content.decode("utf-8", errors="replace").splitlines()
    lead_count = max(0, len([l for l in lines if l.strip()]) - 1)

    return JSONResponse(
        {
            "filename": file.filename,
            "lead_count": lead_count,
            "csv_path": str(dest),
        }
    )


@app.post("/api/pipeline/run")
async def api_pipeline_run(body: dict[str, Any]) -> JSONResponse:
    """Start the pipeline as a background asyncio task."""
    global _pipeline_task, _pipeline_status

    if _pipeline_task and not _pipeline_task.done():
        raise HTTPException(status_code=409, detail="Pipeline already running")

    csv_path = body.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        raise HTTPException(status_code=400, detail="csv_path is required and must exist")

    dry_run: bool = body.get("dry_run", True)
    single_lead: Optional[int] = body.get("single_lead")

    # Reset status
    _pipeline_status.update(
        {
            "running": True,
            "total": 0,
            "processed": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "start_time": datetime.utcnow().isoformat(),
            "elapsed_seconds": 0,
            "cost_usd": 0.0,
        }
    )

    async def _run():
        global _pipeline_status
        t0 = time.monotonic()
        try:
            from src.ai_cold_email.orchestrator.pipeline import run_pipeline
            settings = load_settings()
            await run_pipeline(
                csv_path=Path(csv_path),
                single_lead_index=single_lead,
                resume=False,
                dry_run=dry_run,
                settings=settings,
            )
        except asyncio.CancelledError:
            log.info("Pipeline cancelled")
        except Exception as e:
            log.error(f"Pipeline error: {e}", exc_info=True)
        finally:
            _pipeline_status["running"] = False
            _pipeline_status["elapsed_seconds"] = round(time.monotonic() - t0)

    _pipeline_task = asyncio.create_task(_run())
    return JSONResponse({"started": True})


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

@app.get("/api/playbook")
async def api_playbook_get() -> JSONResponse:
    """Return all email and SMS templates for the Playbook editor.

    Combines config from settings.yaml (variant metadata) with editable
    template content from config/templates.yaml.
    """
    from src.utils.template_store import load_templates
    settings  = load_settings()
    overrides = load_templates()

    # ── Email variants ──────────────────────────────────────────────────────
    email_variants = []
    active_test = settings.variants.get("framework_tournament_v1", {})
    email_overrides = overrides.get("email", {})
    for arm in active_test.get("arms", []):
        vid  = arm["id"]
        tmpl = email_overrides.get(vid, {})
        email_variants.append({
            "variant_id":     vid,
            "framework":      arm.get("overrides", {}).get("variant_framework", ""),
            "description":    arm.get("description", ""),
            "subject_formula": tmpl.get("subject_formula", ""),
            "template":       tmpl.get("template", ""),
            "word_count":     tmpl.get("word_count", ""),
            "ai_fills":       tmpl.get("ai_fills", ""),
            "is_edited":      bool(tmpl.get("template")),
        })

    # ── SMS variants ────────────────────────────────────────────────────────
    sms_variants = []
    sms_test_id = settings.sms.get("variants", {}).get("active_test", "sms_framework_v1")
    sms_test    = settings.sms.get("variants", {}).get(sms_test_id, {})
    sms_overrides = overrides.get("sms", {})
    for arm in sms_test.get("arms", []):
        vid  = arm["id"]
        tmpl = sms_overrides.get(vid, {})
        sms_variants.append({
            "variant_id":  vid,
            "name":        arm.get("name", ""),
            "framework":   arm.get("framework", ""),
            "description": arm.get("description", ""),
            "template":    tmpl.get("template", ""),
            "char_limit":  tmpl.get("char_limit", 160),
            "ai_fills":    tmpl.get("ai_fills", ""),
            "is_edited":   bool(tmpl.get("template")),
        })

    return JSONResponse({"email": email_variants, "sms": sms_variants})


@app.put("/api/playbook/template")
async def api_playbook_save(payload: dict[str, Any]) -> JSONResponse:
    """Save an edited template from the Playbook editor.

    Body: { "channel": "email"|"sms", "variant_id": "...", "updates": {...} }
    Allowed update keys: template, subject_formula, word_count, char_limit, ai_fills
    """
    from src.utils.template_store import save_template
    channel    = payload.get("channel", "")
    variant_id = payload.get("variant_id", "")
    updates    = payload.get("updates", {})

    if not channel or not variant_id:
        raise HTTPException(status_code=400, detail="channel and variant_id are required")
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")
    if not updates:
        raise HTTPException(status_code=400, detail="updates cannot be empty")

    # Only allow safe keys
    allowed_keys = {"template", "subject_formula", "word_count", "char_limit", "ai_fills"}
    filtered = {k: v for k, v in updates.items() if k in allowed_keys}
    if not filtered:
        raise HTTPException(status_code=400, detail=f"No valid update keys. Allowed: {allowed_keys}")

    save_template(channel, variant_id, filtered)
    log.info("Playbook template updated: channel=%s variant=%s keys=%s", channel, variant_id, list(filtered))
    return JSONResponse({"ok": True, "channel": channel, "variant_id": variant_id, "updated_keys": list(filtered)})


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
