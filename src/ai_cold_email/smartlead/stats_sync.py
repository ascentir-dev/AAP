"""
SmartLead analytics sync.

Pulls per-lead engagement data from the SmartLead API for every variant campaign
and upserts events into the ledger so the analytics dashboard reflects reality
without requiring SmartLead webhooks to be reachable (which they can't be on
localhost).

Call /api/analytics/sync from the dashboard to trigger a sync.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.utils.settings import Settings
from src.utils.ledger import Ledger

log = logging.getLogger(__name__)

BASE_URL = "https://server.smartlead.ai/api/v1"


def _build_email_to_lead_id(ledger: Ledger) -> dict[str, str]:
    """Build an email → lead_id reverse map.

    Strategy 1: read leads.email from the DB (fast, works when emails are stored).
    Strategy 2: read CSV files from csv_uploads and compute lead_id from UUID
                (backfill path — also patches leads.email while it runs).
    """
    email_map: dict[str, str] = {}

    # Strategy 1 — emails already in DB
    rows = ledger._execute("SELECT lead_id, email FROM leads WHERE email != ''").fetchall()
    for r in rows:
        email_map[r["email"].lower().strip()] = r["lead_id"]

    if email_map:
        log.info("[sync] email map: %d entries from DB", len(email_map))
        return email_map

    # Strategy 2 — read CSV files to build the map and backfill emails
    log.info("[sync] DB emails blank — building email map from CSV files")
    try:
        uploads = ledger._execute(
            "SELECT id, csv_path FROM csv_uploads ORDER BY id"
        ).fetchall()
    except Exception:
        return email_map

    for upload in uploads:
        csv_path = Path(upload["csv_path"])
        if not csv_path.exists():
            continue
        try:
            content = csv_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        reader = csv.DictReader(io.StringIO(content))
        batch_updates: list[tuple[str, str]] = []
        for row in reader:
            norm = {k.strip().upper(): (v or "").strip() for k, v in row.items()}
            uuid  = norm.get("UUID", "").strip()
            email = (
                norm.get("BUSINESS_EMAIL")
                or norm.get("BUSINESS_VERIFIED_EMAILS")
                or norm.get("EMAIL", "")
            )
            email = email.split(",")[0].strip().lower()
            if not email or "@" not in email:
                continue
            identifier = uuid if uuid else email
            lead_id = hashlib.sha256(identifier.encode()).hexdigest()[:16]
            email_map[email] = lead_id
            batch_updates.append((email, lead_id))

        # Backfill emails in the DB in batches
        if batch_updates:
            for i in range(0, len(batch_updates), 500):
                chunk = batch_updates[i : i + 500]
                for email_val, lid in chunk:
                    ledger._execute(
                        "UPDATE leads SET email = ? WHERE lead_id = ? AND email = ''",
                        (email_val, lid),
                    )
            ledger._conn.commit()
            log.info("[sync] backfilled %d emails from %s", len(batch_updates), csv_path.name)

    log.info("[sync] email map: %d entries after CSV backfill", len(email_map))
    return email_map

# SmartLead boolean flag → our event_type
_FLAG_TO_EVENT: dict[str, str] = {
    "is_email_open":    "opened",
    "is_replied":       "replied",
    "is_unsubscribed":  "unsubscribed",
    "is_bounced":       "bounced",
    "is_clicked":       "clicked",
}

# SmartLead count field → our event_type (used when boolean flag not present)
_COUNT_TO_EVENT: dict[str, str] = {
    "open_count":   "opened",
    "reply_count":  "replied",
    "click_count":  "clicked",
}


async def sync_campaign(
    campaign_id: str,
    variant_label: str,
    api_key: str,
    ledger: Ledger,
    client: httpx.AsyncClient,
    email_map: dict[str, str] | None = None,
) -> dict[str, int]:
    """Sync per-lead engagement from SmartLead's /statistics endpoint.

    SmartLead's /campaigns/{id}/leads endpoint does NOT carry engagement data —
    it only has lead status (STARTED/COMPLETED).  The /statistics endpoint is the
    correct source: it returns one row per sent email with open_time, reply_time,
    and click_time timestamps for every lead that was actually delivered.

    Returns counts of new events upserted by type.
    """
    counts: dict[str, int] = {}
    offset = 0
    limit = 100

    # Timestamp → event_type mapping
    _TIME_TO_EVENT = {
        "open_time":  "opened",
        "reply_time": "replied",
        "click_time": "clicked",
    }
    _BOOL_TO_EVENT = {
        "is_unsubscribed": "unsubscribed",
        "is_bounced":       "bounced",
    }

    while True:
        url = (
            f"{BASE_URL}/campaigns/{campaign_id}/statistics"
            f"?api_key={api_key}&offset={offset}&limit={limit}"
        )
        try:
            r = await client.get(url)
        except Exception as exc:
            log.warning("[sync] campaign %s: network error — %s", campaign_id, exc)
            break

        if r.status_code == 404:
            log.warning("[sync] campaign %s not found (statistics endpoint)", campaign_id)
            break
        if not r.is_success:
            log.warning("[sync] campaign %s HTTP %d: %s", campaign_id, r.status_code, r.text[:120])
            break

        payload: Any = r.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not rows:
            break

        for row in rows:
            email = (row.get("lead_email") or "").lower().strip()
            if not email:
                continue

            lead_id = email_map.get(email) if email_map is not None else ledger.lead_id_for_email(email)
            if not lead_id:
                continue

            # Timestamp-based events (open_time, reply_time, click_time)
            for time_field, event_type in _TIME_TO_EVENT.items():
                if not row.get(time_field):
                    continue
                existing = ledger._execute(
                    "SELECT 1 FROM events WHERE lead_id=? AND event_type=? LIMIT 1",
                    (lead_id, event_type),
                ).fetchone()
                if not existing:
                    # Parse the ISO timestamp for the accurate occurred_at
                    try:
                        occurred_at = datetime.fromisoformat(row[time_field].replace("Z", "+00:00"))
                    except Exception:
                        occurred_at = datetime.now(timezone.utc)
                    ledger.record_event(lead_id, event_type, occurred_at, row)
                    counts[event_type] = counts.get(event_type, 0) + 1

            # Boolean flags (is_unsubscribed, is_bounced)
            for bool_field, event_type in _BOOL_TO_EVENT.items():
                if not row.get(bool_field):
                    continue
                existing = ledger._execute(
                    "SELECT 1 FROM events WHERE lead_id=? AND event_type=? LIMIT 1",
                    (lead_id, event_type),
                ).fetchone()
                if not existing:
                    ledger.record_event(lead_id, event_type, datetime.now(timezone.utc), row)
                    counts[event_type] = counts.get(event_type, 0) + 1

        if len(rows) < limit:
            break
        offset += limit

    log.info("[sync] campaign %s (%s): upserted %s", campaign_id, variant_label, counts)
    return counts


async def sync_campaign_analytics(
    campaign_id: str,
    variant_label: str,
    api_key: str,
    ledger: Ledger,
    client: httpx.AsyncClient,
) -> None:
    """Pull campaign-level aggregate analytics from SmartLead and save to campaign_stats."""
    url = f"{BASE_URL}/campaigns/{campaign_id}/analytics?api_key={api_key}"
    try:
        r = await client.get(url)
        if not r.is_success:
            log.warning("[sync-analytics] campaign %s HTTP %d", campaign_id, r.status_code)
            return
        d = r.json()
        ledger.save_campaign_stats(
            campaign_id=campaign_id,
            variant_id=variant_label,
            in_queue=int(d.get("total_count") or 0),
            delivered=int(d.get("sent_count") or 0),
            opened=int(d.get("open_count") or 0),
            replied=int(d.get("reply_count") or 0),
            bounced=int(d.get("bounce_count") or 0),
            clicked=int(d.get("click_count") or 0),
            drafted=int(d.get("drafted_count") or 0),
        )
        log.info(
            "[sync-analytics] campaign %s (%s): in_queue=%s delivered=%s",
            campaign_id, variant_label,
            d.get("total_count"), d.get("sent_count"),
        )
    except Exception as exc:
        log.warning("[sync-analytics] campaign %s: %s", campaign_id, exc)


async def sync_all_campaigns(settings: Settings, ledger: Ledger) -> dict[str, Any]:
    """Sync all variant campaigns. Returns a summary dict suitable for the API response."""
    api_key = settings.smartlead_api_key
    if not api_key:
        return {"ok": False, "error": "SMARTLEAD_API_KEY not set", "totals": {}}

    test_config = settings.active_test_config()
    if not test_config:
        return {"ok": False, "error": "No active test config", "totals": {}}

    arms = test_config.get("arms", [])
    campaign_pairs = [
        (arm.get("id", f"arm_{i}"), str(arm["smartlead_campaign_id"]))
        for i, arm in enumerate(arms)
        if arm.get("smartlead_campaign_id")
    ]

    # Build email→lead_id map once (backfills DB emails if blank)
    email_map = _build_email_to_lead_id(ledger)

    totals: dict[str, int] = {}
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for variant_label, campaign_id in campaign_pairs:
            try:
                # Per-lead engagement events
                counts = await sync_campaign(campaign_id, variant_label, api_key, ledger, client, email_map=email_map)
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
                # Campaign-level analytics (delivered/open/reply counts)
                await sync_campaign_analytics(campaign_id, variant_label, api_key, ledger, client)
            except Exception as exc:
                msg = f"{variant_label}: {exc}"
                errors.append(msg)
                log.error("[sync] %s", msg, exc_info=True)

    # Totals from campaign_stats for the API response
    try:
        row = ledger._execute(
            "SELECT SUM(in_queue) q, SUM(delivered) d FROM campaign_stats"
        ).fetchone()
        if row:
            totals["in_queue"]   = row[0] or 0
            totals["delivered"]  = row[1] or 0
    except Exception:
        pass

    return {
        "ok": len(errors) == 0,
        "campaigns_synced": len(campaign_pairs),
        "totals": totals,
        "errors": errors,
    }
