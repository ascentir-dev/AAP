"""
Video event tracker — SQLite-backed.

Tracks the full funnel per video script variant:
  sent    → video was generated + hosted for a lead
  viewed  → lead opened the video URL (tracked via /v/{lead_id} redirect)
  replied → lead replied to the email (logged by Smartlead webhook)
  booked  → lead booked a call (logged by Calendly webhook)

Schema lives in data/video_ledger.sqlite (separate from the main cost ledger).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DB_PATH = Path("data/video_ledger.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS video_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id             TEXT    NOT NULL,
    email               TEXT,
    company             TEXT,
    variant_id          TEXT    NOT NULL,   -- V1 / V2 / V3 / V4
    event_type          TEXT    NOT NULL,   -- sent / viewed / replied / booked
    email_type          TEXT    NOT NULL DEFAULT 'video',  -- video | email_only
    video_url           TEXT,
    cta_url             TEXT,               -- per-lead Calendly/booking link override
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ve_lead     ON video_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_ve_variant  ON video_events(variant_id);
CREATE INDEX IF NOT EXISTS idx_ve_event    ON video_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ve_created  ON video_events(created_at);
"""


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(_SCHEMA)
    # Migration: add email_type to existing databases that predate this column.
    try:
        con.execute("ALTER TABLE video_events ADD COLUMN email_type TEXT NOT NULL DEFAULT 'video'")
        con.commit()
    except Exception:
        pass
    return con


# ── Write ─────────────────────────────────────────────────────────────────────

def log_sent(
    lead_id: str,
    variant_id: str,
    video_url: str,
    email: str = "",
    company: str = "",
    cta_url: str = "",
) -> None:
    """Call when a video is generated + hosted for a lead."""
    with _conn() as con:
        con.execute(
            "INSERT INTO video_events "
            "(lead_id, email, company, variant_id, event_type, email_type, video_url, cta_url) "
            "VALUES (?, ?, ?, ?, 'sent', 'video', ?, ?)",
            (lead_id, email, company, variant_id, video_url, cta_url),
        )
    log.debug(f"video_tracker: sent  lead={lead_id} variant={variant_id} type=video")


def log_email_only_sent(
    lead_id: str,
    variant_id: str,
    email: str = "",
    company: str = "",
    cta_url: str = "",
) -> None:
    """Call when an email-only lead is sent (no video generated)."""
    with _conn() as con:
        con.execute(
            "INSERT INTO video_events "
            "(lead_id, email, company, variant_id, event_type, email_type, video_url, cta_url) "
            "VALUES (?, ?, ?, ?, 'sent', 'email_only', '', ?)",
            (lead_id, email, company, variant_id, cta_url),
        )
    log.debug(f"video_tracker: sent  lead={lead_id} variant={variant_id} type=email_only")


def log_viewed(lead_id: str) -> dict | None:
    """
    Call when the /v/{lead_id} tracking URL is hit.
    Logs the view event and returns a dict with video metadata, or None if not found.

    Returned dict keys: video_url, cta_url, variant_id, company, email
    """
    with _conn() as con:
        row = con.execute(
            "SELECT video_url, cta_url, variant_id, company, email FROM video_events "
            "WHERE lead_id=? AND event_type='sent' ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        if not row:
            return None
        con.execute(
            "INSERT INTO video_events (lead_id, variant_id, event_type) VALUES (?, ?, 'viewed')",
            (lead_id, row["variant_id"]),
        )
    log.debug(f"video_tracker: viewed lead={lead_id}")
    return dict(row)


def log_replied(lead_id: str) -> None:
    """Call from the Smartlead reply webhook."""
    with _conn() as con:
        row = con.execute(
            "SELECT variant_id FROM video_events WHERE lead_id=? AND event_type='sent' "
            "ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        if row:
            con.execute(
                "INSERT INTO video_events (lead_id, variant_id, event_type) VALUES (?, ?, 'replied')",
                (lead_id, row["variant_id"]),
            )
    log.debug(f"video_tracker: replied lead={lead_id}")


def log_booked(lead_id: str) -> None:
    """Call from the Calendly booking webhook."""
    with _conn() as con:
        row = con.execute(
            "SELECT variant_id FROM video_events WHERE lead_id=? AND event_type='sent' "
            "ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        if row:
            con.execute(
                "INSERT INTO video_events (lead_id, variant_id, event_type) VALUES (?, ?, 'booked')",
                (lead_id, row["variant_id"]),
            )
    log.debug(f"video_tracker: booked lead={lead_id}")


# ── Read ──────────────────────────────────────────────────────────────────────

# ── KPI targets (from Morgan's Loom Alchemic Equation) ───────────────────────
KPI_LVR          = 0.15   # 15%  — loom sent → viewed
KPI_PRR_OVERALL  = 0.03   # 3%   — loom sent → positive reply
KPI_PRR_VIEW     = 0.20   # 20%  — loom viewed → positive reply
KPI_ABR_OVERALL  = 0.015  # 1.5% — loom sent → appointment booked
KPI_ABR_REPLY    = 0.50   # 50%  — positive reply → appointment booked

# Minimum sample sizes before a KPI reading is statistically meaningful
SAMPLE_LVR   = 300   # looms sent   → unlocks LVR
SAMPLE_PRR   = 45    # loom views   → unlocks PRR
SAMPLE_ABR   = 9     # pos. replies → unlocks ABR


def _kpi_status(value: float, target: float, sample: int, have: int) -> str:
    """Return 'pass' | 'fail' | 'pending' (not enough data yet)."""
    if have < sample:
        return "pending"
    return "pass" if value >= target else "fail"


def get_analytics() -> list[dict[str, Any]]:
    """
    Return per-variant funnel stats for the dashboard.

    Each dict includes:
      variant_id, name, hook_style, description,
      sent, views, replies, bookings,
      lvr, prr_overall, prr_view, abr_overall, abr_reply,
      lvr_status, prr_status, abr_status,  ('pass'|'fail'|'pending')
      leading  (bool — highest reply_rate among variants with >= 5 sent)
    """
    from src.ai_cold_email.video.script.video_scripts import list_variants

    with _conn() as con:
        rows = con.execute(
            """
            SELECT variant_id, event_type, email_type, COUNT(*) as cnt
            FROM video_events
            GROUP BY variant_id, event_type, email_type
            """
        ).fetchall()

    # counts[variant_id][event_type] = total
    # type_counts[variant_id][email_type] = sent count
    counts: dict[str, dict[str, int]] = {}
    type_counts: dict[str, dict[str, int]] = {}
    for r in rows:
        counts.setdefault(r["variant_id"], {})[r["event_type"]] = (
            counts.get(r["variant_id"], {}).get(r["event_type"], 0) + r["cnt"]
        )
        if r["event_type"] == "sent":
            type_counts.setdefault(r["variant_id"], {})[r["email_type"]] = r["cnt"]

    variants_meta = {v["id"]: v for v in list_variants()}
    result = []

    for vid in ["V1", "V2", "V3", "V4"]:
        meta    = variants_meta.get(vid, {"name": vid, "hook_style": "", "description": ""})
        ev      = counts.get(vid, {})
        tc      = type_counts.get(vid, {})
        sent    = ev.get("sent",    0)
        views   = ev.get("viewed",  0)
        replies = ev.get("replied", 0)
        booked  = ev.get("booked",  0)
        sent_video      = tc.get("video",      0)
        sent_email_only = tc.get("email_only", 0)

        lvr         = round(views   / sent,    4) if sent    else 0.0
        prr_overall = round(replies / sent,    4) if sent    else 0.0
        prr_view    = round(replies / views,   4) if views   else 0.0
        abr_overall = round(booked  / sent,    4) if sent    else 0.0
        abr_reply   = round(booked  / replies, 4) if replies else 0.0

        result.append({
            "variant_id":   vid,
            "name":         meta["name"],
            "hook_style":   meta["hook_style"],
            "description":  meta.get("description", ""),

            # Raw counts
            "sent":           sent,
            "sent_video":     sent_video,
            "sent_email_only": sent_email_only,
            "views":          views,
            "replies":        replies,
            "bookings":       booked,

            # Rates (kept for backward-compat)
            "view_rate":   lvr,
            "reply_rate":  prr_overall,
            "book_rate":   abr_overall,

            # Named KPI rates
            "lvr":          lvr,
            "prr_overall":  prr_overall,
            "prr_view":     prr_view,
            "abr_overall":  abr_overall,
            "abr_reply":    abr_reply,

            # KPI pass/fail/pending
            "lvr_status":  _kpi_status(lvr,         KPI_LVR,         SAMPLE_LVR,  sent),
            "prr_status":  _kpi_status(prr_view,     KPI_PRR_VIEW,    SAMPLE_PRR,  views),
            "abr_status":  _kpi_status(abr_reply,    KPI_ABR_REPLY,   SAMPLE_ABR,  replies),

            # Sample size progress (0.0 – 1.0)
            "lvr_sample_pct":  min(sent    / SAMPLE_LVR,  1.0),
            "prr_sample_pct":  min(views   / SAMPLE_PRR,  1.0),
            "abr_sample_pct":  min(replies / SAMPLE_ABR,  1.0),
        })

    # Mark the leading variant (highest prr_overall, min 5 sent)
    eligible = [r for r in result if r["sent"] >= 5]
    if eligible:
        winner = max(eligible, key=lambda x: x["prr_overall"])
        winner["leading"] = True
    for r in result:
        r.setdefault("leading", False)

    return result


def get_testing_summary() -> dict[str, Any]:
    """
    Aggregate testing summary across all variants.
    Returns overall LVR / PRR / ABR plus which phase the campaign is in.
    """
    variants = get_analytics()

    total_sent    = sum(v["sent"]     for v in variants)
    total_views   = sum(v["views"]    for v in variants)
    total_replies = sum(v["replies"]  for v in variants)
    total_booked  = sum(v["bookings"] for v in variants)

    lvr         = round(total_views   / total_sent,    4) if total_sent    else 0.0
    prr_overall = round(total_replies / total_sent,    4) if total_sent    else 0.0
    prr_view    = round(total_replies / total_views,   4) if total_views   else 0.0
    abr_overall = round(total_booked  / total_sent,    4) if total_sent    else 0.0
    abr_reply   = round(total_booked  / total_replies, 4) if total_replies else 0.0

    lvr_status = _kpi_status(lvr,      KPI_LVR,       SAMPLE_LVR,  total_sent)
    prr_status = _kpi_status(prr_view, KPI_PRR_VIEW,  SAMPLE_PRR,  total_views)
    abr_status = _kpi_status(abr_reply,KPI_ABR_REPLY, SAMPLE_ABR,  total_replies)

    # Current phase: LVR first, then PRR, then ABR
    if lvr_status != "pass":
        phase = "LVR"
        phase_label = "Nail your view rate — focus on offer, copy & lead quality"
    elif prr_status != "pass":
        phase = "PRR"
        phase_label = "LVR in KPI ✓ — now nail script content & delivery"
    elif abr_status != "pass":
        phase = "ABR"
        phase_label = "LVR + PRR in KPI ✓ — now nail reply style & warm follow-ups"
    else:
        phase = "SCALE"
        phase_label = "All KPIs in target — change NOTHING, just add volume"

    return {
        # Totals
        "total_sent":    total_sent,
        "total_views":   total_views,
        "total_replies": total_replies,
        "total_booked":  total_booked,

        # Overall rates
        "lvr":          lvr,
        "prr_overall":  prr_overall,
        "prr_view":     prr_view,
        "abr_overall":  abr_overall,
        "abr_reply":    abr_reply,

        # KPI targets
        "kpi": {
            "lvr":         KPI_LVR,
            "prr_overall": KPI_PRR_OVERALL,
            "prr_view":    KPI_PRR_VIEW,
            "abr_overall": KPI_ABR_OVERALL,
            "abr_reply":   KPI_ABR_REPLY,
        },

        # Sample size gates
        "sample": {
            "lvr":  {"required": SAMPLE_LVR,  "have": total_sent,    "pct": min(total_sent    / SAMPLE_LVR,  1.0)},
            "prr":  {"required": SAMPLE_PRR,  "have": total_views,   "pct": min(total_views   / SAMPLE_PRR,  1.0)},
            "abr":  {"required": SAMPLE_ABR,  "have": total_replies, "pct": min(total_replies / SAMPLE_ABR,  1.0)},
        },

        # Status
        "lvr_status":  lvr_status,
        "prr_status":  prr_status,
        "abr_status":  abr_status,

        # Current testing phase
        "phase":       phase,
        "phase_label": phase_label,

        # Per-variant detail
        "variants": variants,
    }


async def sync_from_cloudflare_kv(worker_url: str = "", since: str = "") -> int:
    """
    Pull view events from the Cloudflare Worker KV and write them to local SQLite.
    Returns the number of new views written.

    Called automatically by the dashboard every few minutes, or manually:
      python3 -c "import asyncio; from src.utils.video_tracker import sync_from_cloudflare_kv; asyncio.run(sync_from_cloudflare_kv())"
    """
    import httpx

    if not worker_url:
        try:
            from src.utils.settings import Settings
            worker_url = Settings().cloudflare_worker_url
        except Exception:
            pass

    if not worker_url:
        log.warning("sync_from_cloudflare_kv: CLOUDFLARE_WORKER_URL not set — skipping sync")
        return 0

    url = f"{worker_url.rstrip('/')}/api/views"
    if since:
        url += f"?since={since}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            events = r.json()
    except Exception as e:
        log.warning(f"sync_from_cloudflare_kv: fetch failed — {e}")
        return 0

    new_count = 0
    with _conn() as con:
        for ev in events:
            lead_id = ev.get("leadId", "")
            ts      = ev.get("ts", "")
            if not lead_id or not ts:
                continue

            # Check if this view is already in SQLite (avoid duplicates)
            exists = con.execute(
                "SELECT 1 FROM video_events WHERE lead_id=? AND event_type='viewed' AND created_at=?",
                (lead_id, ts),
            ).fetchone()
            if exists:
                continue

            # Look up variant_id from the sent event
            row = con.execute(
                "SELECT variant_id FROM video_events WHERE lead_id=? AND event_type='sent' "
                "ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ).fetchone()
            variant_id = row["variant_id"] if row else "unknown"

            con.execute(
                "INSERT INTO video_events (lead_id, variant_id, event_type, created_at) "
                "VALUES (?, ?, 'viewed', ?)",
                (lead_id, variant_id, ts),
            )
            new_count += 1

    if new_count:
        log.info(f"sync_from_cloudflare_kv: wrote {new_count} new view(s)")
    return new_count


def get_recent_views(limit: int = 50) -> list[dict[str, Any]]:
    """Recent video view events for the live feed."""
    with _conn() as con:
        rows = con.execute(
            "SELECT lead_id, company, variant_id, event_type, created_at "
            "FROM video_events WHERE event_type IN ('viewed','replied','booked') "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
