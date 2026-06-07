"""
Twilio inbound message sync — polls Twilio's Messages API every 60 seconds
for new replies on all 3 Twilio numbers.

No public URL or webhook configuration needed.  Works 100% locally.

How it works:
  1. On first run, syncs the last 7 days of inbound messages so you don't miss
     anything that came in before the sync started.
  2. On every subsequent poll, fetches only messages newer than the last sync.
  3. Deduplication via Twilio SID — the UNIQUE constraint in sms_messages means
     the same message can never be recorded twice even if the poll overlaps.
  4. For each new inbound message, calls handle_inbound() exactly as the
     Twilio webhook would — opt-out detection, ledger update, status → 'replied'.

The worker is started as a background asyncio task on server startup.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60   # how often to check Twilio
_LOOKBACK_DAYS_FIRST_RUN = 7  # on first run, how far back to check


def _twilio_client(settings: Any):
    from twilio.rest import Client
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _fetch_inbound_for_number(
    client: Any,
    number: str,
    after: datetime,
) -> list[dict]:
    """
    Fetch all inbound messages sent TO `number` after `after`.
    Returns list of dicts with: sid, from_, to_, body, date_sent.
    """
    try:
        msgs = client.messages.list(
            to=number,
            date_sent_after=after,
        )
        results = []
        for m in msgs:
            # direction can be 'inbound' or 'inbound' depending on Twilio SDK version
            direction = getattr(m, "direction", "") or ""
            if "inbound" not in direction.lower():
                continue
            results.append({
                "sid":       m.sid,
                "from_":     m.from_,
                "to_":       m.to,
                "body":      m.body or "",
                "date_sent": m.date_sent,   # datetime object from Twilio SDK
            })
        return results
    except Exception as e:
        log.warning("Twilio fetch failed for %s: %s", number, e)
        return []


async def sync_once(settings: Any, ledger: Any) -> dict:
    """
    Pull new inbound messages from Twilio for all configured numbers.
    Returns a summary dict: { synced: N, new: N, errors: [...] }
    """
    from src.sms.conversation import handle_inbound

    numbers = settings.twilio_numbers
    if not numbers:
        return {"synced": 0, "new": 0, "errors": ["No Twilio numbers configured"]}

    # Determine the lookback window
    last_sync_str = ledger.get_sync_state("last_sync_at")
    if last_sync_str:
        try:
            after = datetime.fromisoformat(last_sync_str)
            # Add tz info if missing (Twilio returns tz-aware datetimes)
            if after.tzinfo is None:
                after = after.replace(tzinfo=timezone.utc)
        except ValueError:
            after = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS_FIRST_RUN)
    else:
        # First ever run — look back 7 days to catch any replies already waiting
        after = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS_FIRST_RUN)
        log.info("Twilio sync: first run, checking last %d days", _LOOKBACK_DAYS_FIRST_RUN)

    client = await asyncio.to_thread(_twilio_client, settings)
    total_new = 0
    errors = []

    for number in numbers:
        msgs = await asyncio.to_thread(_fetch_inbound_for_number, client, number, after)
        log.debug("Twilio sync: %d inbound messages on %s since %s", len(msgs), number, after)

        for msg in msgs:
            sid       = msg["sid"]
            from_num  = msg["from_"]
            to_num    = msg["to_"]
            body      = msg["body"]

            # Skip if already recorded (dedup by SID)
            if ledger.sid_exists(sid):
                continue

            # Process exactly as the webhook would
            try:
                result = await handle_inbound(
                    from_number=from_num,
                    to_number=to_num,
                    body=body,
                    twilio_sid=sid,
                    ledger=ledger,
                    settings=settings,
                )
                total_new += 1
                log.info(
                    "Twilio sync: new inbound from %s on %s — %s (sid=%s)",
                    from_num, to_num, result.get("status"), sid,
                )
            except Exception as e:
                log.error("Twilio sync: handle_inbound failed for sid=%s: %s", sid, e)
                errors.append(f"{sid}: {e}")

    # Record the sync timestamp so next poll only fetches newer messages
    now_iso = datetime.now(timezone.utc).isoformat()
    ledger.set_sync_state("last_sync_at", now_iso)
    ledger.set_sync_state("last_sync_result", f"{total_new} new messages")

    if total_new:
        log.info("Twilio sync complete: %d new inbound messages", total_new)

    return {
        "synced":   len(numbers),
        "new":      total_new,
        "errors":   errors,
        "synced_at": now_iso,
    }


async def run_sync_worker(settings: Any, ledger: Any, stop_event: asyncio.Event) -> None:
    """
    Background worker — calls sync_once() every POLL_INTERVAL_SECONDS.
    Stops gracefully when stop_event is set (on server shutdown).
    """
    log.info("Twilio sync worker started (interval=%ds)", _POLL_INTERVAL_SECONDS)

    while not stop_event.is_set():
        try:
            result = await sync_once(settings, ledger)
            if result["new"] > 0:
                log.info("Twilio sync: picked up %d new replies", result["new"])
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Twilio sync worker error: %s", e)

        # Wait POLL_INTERVAL_SECONDS, but break early if stop_event fires
        try:
            await asyncio.wait_for(
                asyncio.shield(stop_event.wait()),
                timeout=_POLL_INTERVAL_SECONDS,
            )
            break  # stop_event was set
        except asyncio.TimeoutError:
            pass   # normal — just continue polling

    log.info("Twilio sync worker stopped")
