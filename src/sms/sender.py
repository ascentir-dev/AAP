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
) -> str:
    """Synchronous Twilio send — run via asyncio.to_thread."""
    from twilio.rest import Client
    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        from_=from_number,
        to=to_number,
        body=body,
    )
    return msg.sid


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def send_sms(
    lead_id: str,
    to_number: str,
    body: str,
    settings: Any,
) -> str:
    """Send an SMS and return the Twilio message SID.

    The from_number is deterministically chosen from settings.twilio_numbers
    based on lead_id so the same lead always receives from the same number.
    """
    numbers = settings.twilio_numbers
    from_number = assign_number(lead_id, numbers)

    sid = await asyncio.to_thread(
        _send_sync,
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        from_number,
        to_number,
        body,
    )
    log.info(
        "SMS sent lead=%s from=%s to=%s sid=%s chars=%d",
        lead_id, from_number, to_number, sid, len(body),
    )
    return sid


async def send_reply(
    to_number: str,
    from_number: str,
    body: str,
    settings: Any,
) -> str:
    """Send a manual reply from the dashboard.  Uses the explicit from_number."""
    sid = await asyncio.to_thread(
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
