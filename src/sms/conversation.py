"""
SMS conversation helpers — load thread and send replies from the dashboard.

Used by the dashboard API (/api/sms/conversations/{lead_id} and /api/sms/reply).
"""
from __future__ import annotations

import logging
from typing import Any

from src.sms.ledger import SMSLedger
from src.sms.sender import is_opt_out, send_reply, _OPT_OUT_REPLY

log = logging.getLogger(__name__)


def get_conversation(lead_id: str, ledger: SMSLedger) -> dict[str, Any]:
    """Return the lead record + full message thread."""
    lead = ledger.get_lead(lead_id)
    if not lead:
        return {"error": "lead_not_found", "messages": []}
    messages = ledger.get_conversation(lead_id)
    return {
        "lead": lead,
        "messages": messages,
        "message_count": len(messages),
        "inbound_count": sum(1 for m in messages if m["direction"] == "inbound"),
    }


async def handle_inbound(
    from_number: str,
    to_number: str,
    body: str,
    twilio_sid: str,
    ledger: SMSLedger,
    settings: Any,
) -> dict[str, str]:
    """Process an inbound SMS from Twilio webhook.

    Steps:
    1. Match sender phone to a lead
    2. Check for opt-out keyword → mark opted_out, send confirmation
    3. Record inbound message
    4. Update lead status to 'replied'
    5. Return TwiML response (empty — we reply manually from dashboard)
    """
    lead_id = ledger.lead_id_for_phone(from_number)
    if not lead_id:
        log.warning("Inbound SMS from unknown number %s — not in pipeline", from_number)
        return {"status": "unknown_sender"}

    # Check opt-out
    if is_opt_out(body):
        ledger.update_status(lead_id, "opted_out")
        ledger.record_message(
            lead_id=lead_id,
            direction="inbound",
            from_number=from_number,
            to_number=to_number,
            body=body,
            twilio_sid=twilio_sid,
        )
        # Send opt-out confirmation
        try:
            from src.sms.sender import send_reply as _send
            sid = await _send(
                to_number=from_number,
                from_number=to_number,
                body=_OPT_OUT_REPLY,
                settings=settings,
            )
            ledger.record_message(
                lead_id=lead_id,
                direction="outbound",
                from_number=to_number,
                to_number=from_number,
                body=_OPT_OUT_REPLY,
                twilio_sid=sid,
            )
        except Exception as e:
            log.warning("Failed sending opt-out confirmation to %s: %s", from_number, e)
        log.info("Lead %s opted out via SMS", lead_id)
        return {"status": "opted_out"}

    # Normal reply
    ledger.record_message(
        lead_id=lead_id,
        direction="inbound",
        from_number=from_number,
        to_number=to_number,
        body=body,
        twilio_sid=twilio_sid,
    )
    ledger.update_status(lead_id, "replied")
    log.info("Inbound SMS recorded for lead %s", lead_id)
    return {"status": "ok", "lead_id": lead_id}


async def reply_from_dashboard(
    lead_id: str,
    body: str,
    ledger: SMSLedger,
    settings: Any,
) -> dict[str, Any]:
    """Send a manual reply to a lead from the dashboard UI.

    Uses the lead's assigned_number as the from number so the reply comes
    from the same number the original outbound message was sent from.
    """
    lead = ledger.get_lead(lead_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found"}

    if lead.get("status") == "opted_out":
        return {"ok": False, "error": "lead_opted_out"}

    to_number = lead.get("phone")
    from_number = lead.get("assigned_number")
    if not to_number or not from_number:
        return {"ok": False, "error": "missing_phone_or_number"}

    try:
        sid = await send_reply(
            to_number=to_number,
            from_number=from_number,
            body=body,
            settings=settings,
        )
        ledger.record_message(
            lead_id=lead_id,
            direction="outbound",
            from_number=from_number,
            to_number=to_number,
            body=body,
            twilio_sid=sid,
        )
        return {"ok": True, "sid": sid}
    except Exception as e:
        log.error("Failed sending reply to lead %s: %s", lead_id, e)
        return {"ok": False, "error": str(e)}
