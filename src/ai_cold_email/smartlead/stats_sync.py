"""
SmartLead analytics sync.

Pulls per-lead engagement data from the SmartLead API for every variant campaign
and upserts events into the ledger so the analytics dashboard reflects reality
without requiring SmartLead webhooks to be reachable (which they can't be on
localhost).

Call /api/analytics/sync from the dashboard to trigger a sync.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from src.utils.settings import Settings
from src.utils.ledger import Ledger

log = logging.getLogger(__name__)

BASE_URL = "https://server.smartlead.ai/api/v1"

# SmartLead lead-level stat field → our event_type
_STAT_TO_EVENT: dict[str, str] = {
    "is_email_open":    "opened",
    "is_replied":       "replied",
    "is_unsubscribed":  "unsubscribed",
    "is_bounced":       "bounced",
    "is_clicked":       "clicked",
}


async def sync_campaign(
    campaign_id: str,
    variant_label: str,
    api_key: str,
    ledger: Ledger,
    client: httpx.AsyncClient,
) -> dict[str, int]:
    """Sync one campaign's lead engagement data into the events table.

    Returns counts of new events upserted by type.
    """
    counts: dict[str, int] = {}
    offset = 0
    limit = 100

    while True:
        url = (
            f"{BASE_URL}/campaigns/{campaign_id}/leads"
            f"?api_key={api_key}&offset={offset}&limit={limit}"
        )
        try:
            r = await client.get(url)
        except Exception as exc:
            log.warning("[sync] campaign %s: network error — %s", campaign_id, exc)
            break

        if r.status_code == 404:
            log.warning("[sync] campaign %s not found", campaign_id)
            break
        if not r.is_success:
            log.warning("[sync] campaign %s HTTP %d: %s", campaign_id, r.status_code, r.text[:120])
            break

        payload: Any = r.json()

        # SmartLead returns either a list directly or {"data": [...]}
        if isinstance(payload, list):
            leads_page = payload
        elif isinstance(payload, dict):
            leads_page = (
                payload.get("data")
                or payload.get("leads")
                or payload.get("lead_list")
                or []
            )
        else:
            leads_page = []

        if not leads_page:
            break

        for sl_lead in leads_page:
            email = (
                sl_lead.get("email")
                or sl_lead.get("lead_email")
                or (sl_lead.get("lead") or {}).get("email")
                or ""
            ).lower().strip()
            if not email:
                continue

            lead_id = ledger.lead_id_for_email(email)
            if not lead_id:
                continue

            # Per-lead stats may be nested under "statistics", "stats", or at top level
            stats: dict = (
                sl_lead.get("statistics")
                or sl_lead.get("stats")
                or sl_lead.get("email_lead_statistic")
                or sl_lead
            )

            now = datetime.now(timezone.utc)
            for sl_field, event_type in _STAT_TO_EVENT.items():
                if stats.get(sl_field):
                    # Upsert: skip if this event already recorded for this lead
                    existing = ledger._execute(
                        "SELECT 1 FROM events WHERE lead_id=? AND event_type=? LIMIT 1",
                        (lead_id, event_type),
                    ).fetchone()
                    if not existing:
                        ledger.record_event(lead_id, event_type, now, sl_lead)
                        counts[event_type] = counts.get(event_type, 0) + 1

        if len(leads_page) < limit:
            break
        offset += limit

    log.info("[sync] campaign %s (%s): upserted %s", campaign_id, variant_label, counts)
    return counts


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

    totals: dict[str, int] = {}
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for variant_label, campaign_id in campaign_pairs:
            try:
                counts = await sync_campaign(campaign_id, variant_label, api_key, ledger, client)
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
            except Exception as exc:
                msg = f"{variant_label}: {exc}"
                errors.append(msg)
                log.error("[sync] %s", msg, exc_info=True)

    return {
        "ok": len(errors) == 0,
        "campaigns_synced": len(campaign_pairs),
        "totals": totals,
        "errors": errors,
    }
