"""
Twilio SMS sender with deterministic 3-number rotation.

Number assignment: md5(lead_id) % len(numbers) → same lead always gets the
same number.  This matters for inbound reply routing: when they reply, the
reply arrives on the assigned number and we look up the lead by (phone, from_number).

Opt-out handling: STOP/UNSUBSCRIBE keywords are detected on inbound messages
and the lead is marked opted_out in the ledger.  We never send to opted-out leads.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_OPT_OUT_KEYWORDS = frozenset(
    {"STOP", "UNSUBSCRIBE", "QUIT", "CANCEL", "END", "STOPALL"}
)

_OPT_OUT_REPLY = (
    "You've been unsubscribed and won't receive further messages. "
    "Reply START to resubscribe."
)


def assign_number(lead_id: str, numbers: list[str]) -> str:
    """Deterministically assign one of the Twilio numbers to a lead."""
    if not numbers:
        raise ValueError("No Twilio numbers configured")
    idx = int(hashlib.md5(lead_id.encode()).hexdigest(), 16) % len(numbers)
    return numbers[idx]


def _build_twilio_client(settings: Any) -> Any:
    """Build Twilio REST client (sync — runs in thread pool)."""
    from twilio.rest import Client  # lazy import — not installed until needed
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _send_sync(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    body: str,
) -> tuple[str, float | None, str]:
    """Synchronous Twilio send — run via asyncio.to_thread.

    Returns (sid, price, price_unit).
    price is typically None at creation time; Twilio populates it once the
    message reaches a final status.  Callers should reconcile later via
    /api/sms/reconcile-costs or a Twilio status-callback webhook.
    """
    from twilio.rest import Client
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        from_=from_number,
        to=to_number,
        body=body,
    )
    # price is a string like "-0.00790" or None; normalise to float | None
    raw_price  = getattr(msg, "price", None)
    price      = abs(float(raw_price)) if raw_price is not None else None
    price_unit = getattr(msg, "price_unit", None) or "USD"
    return msg.sid, price, price_unit


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def send_sms(
    lead_id: str,
    to_number: str,
    body: str,
    settings: Any,
) -> tuple[str, float | None, str]:
    """Send an SMS and return (sid, price, price_unit).

    The from_number is deterministically chosen from settings.twilio_numbers
    based on lead_id so the same lead always receives from the same number.
    price is usually None at creation time — reconcile later via the
    /api/sms/reconcile-costs endpoint once messages reach final Twilio status.
    """
    numbers = settings.twilio_numbers
    from_number = assign_number(lead_id, numbers)

    sid, price, price_unit = await asyncio.to_thread(
        _send_sync,
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        from_number,
        to_number,
        body,
    )
    log.info(
        "SMS sent lead=%s from=%s to=%s sid=%s chars=%d price=%s%s",
        lead_id, from_number, to_number, sid, len(body),
        price if price is not None else "pending", price_unit,
    )
    return sid, price, price_unit


async def send_reply(
    to_number: str,
    from_number: str,
    body: str,
    settings: Any,
) -> str:
    """Send a manual reply from the dashboard.  Uses the explicit from_number."""
    sid, _price, _price_unit = await asyncio.to_thread(
        _send_sync,
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        from_number,
        to_number,
        body,
    )
    log.info("Manual reply from=%s to=%s sid=%s", from_number, to_number, sid)
    return sid


def is_opt_out(message_body: str) -> bool:
    """Return True if the message body is a standard opt-out keyword."""
    return message_body.strip().upper() in _OPT_OUT_KEYWORDS
