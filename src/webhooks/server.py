"""
Smartlead webhook receiver.

Smartlead POSTs events here on every email send/open/click/reply/bounce.
This handler validates the payload, looks up the lead, and records the event
in the ledger.

Run:
    python -m src.webhooks.server

Then in Smartlead, configure webhooks:
    https://your-public-url.com/webhooks/smartlead

For booked calls, also point Calendly's invitee.created webhook here:
    https://your-public-url.com/webhooks/calendly

Deploy options:
    - VPS with nginx + uvicorn (simplest)
    - Cloudflare Worker as a thin proxy → forwards to your home server
    - Replit / Fly.io / Railway free tiers (fine for receiver-only volume)

Security:
    - Smartlead can sign webhooks with HMAC; validate signature in production
    - Bind to 0.0.0.0 only behind a reverse proxy / TLS terminator
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

# NOTE: imports below assume the ledger module is built. Claude Code will
# implement src.utils.ledger as part of the master prompt.
from src.utils.ledger import Ledger
from src.utils.settings import load_settings

log = logging.getLogger(__name__)

app = FastAPI(title="Smartlead Webhook Receiver")
settings = load_settings()
ledger = Ledger("ledger.sqlite")

# Smartlead event types we care about → our internal event_type
SMARTLEAD_EVENT_MAP = {
    "EMAIL_SENT": "sent",
    "EMAIL_OPEN": "opened",
    "EMAIL_LINK_CLICK": "clicked",
    "EMAIL_REPLY": "replied",
    "EMAIL_BOUNCE": "bounced",
    "LEAD_UNSUBSCRIBE": "unsubscribed",
}


def verify_smartlead_signature(body: bytes, signature_header: str) -> bool:
    """Validate HMAC signature from Smartlead."""
    secret = os.environ.get("SMARTLEAD_WEBHOOK_SECRET", "")
    if not secret:
        log.warning("SMARTLEAD_WEBHOOK_SECRET not set — accepting unverified webhooks")
        return True
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


@app.post("/webhooks/smartlead")
async def smartlead_webhook(request: Request) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Smartlead-Signature", "")

    if not verify_smartlead_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    event_type_raw = payload.get("event_type")
    event_type = SMARTLEAD_EVENT_MAP.get(event_type_raw)
    if not event_type:
        log.info(f"Ignoring unmapped Smartlead event: {event_type_raw}")
        return {"status": "ignored"}

    # Smartlead identifies leads by email or by their internal lead_id
    # Both should be in the payload — match by email since that's what we sent
    lead_email = payload.get("lead", {}).get("email", "").lower().strip()
    if not lead_email:
        log.warning(f"Webhook missing lead email: {payload}")
        return {"status": "missing_email"}

    # Find our lead_id from email (lead_id was hash of email at ingestion)
    lead_id = ledger.lead_id_for_email(lead_email)
    if not lead_id:
        log.warning(f"No matching lead for email {lead_email}")
        return {"status": "lead_not_found"}

    ledger.record_event(
        lead_id=lead_id,
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
        smartlead_payload=payload,
    )
    log.info(f"Recorded {event_type} for {lead_email}")
    return {"status": "ok"}


@app.post("/webhooks/calendly")
async def calendly_webhook(request: Request) -> dict[str, str]:
    """
    Calendly invitee.created → records a booked_call event for the lead.
    Match by invitee email.
    """
    payload = await request.json()
    event_type = payload.get("event")
    if event_type != "invitee.created":
        return {"status": "ignored"}

    invitee_email = (
        payload.get("payload", {}).get("invitee", {}).get("email", "").lower().strip()
    )
    if not invitee_email:
        return {"status": "missing_email"}

    lead_id = ledger.lead_id_for_email(invitee_email)
    if not lead_id:
        # Booked call from someone not in our pipeline (e.g., referral) — ignore
        log.info(f"Calendly booking from non-pipeline email {invitee_email}")
        return {"status": "not_in_pipeline"}

    ledger.record_event(
        lead_id=lead_id,
        event_type="booked_call",
        occurred_at=datetime.now(timezone.utc),
        smartlead_payload=payload,
    )
    log.info(f"Recorded booked_call for {invitee_email}")
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("WEBHOOK_PORT", 8001)))
