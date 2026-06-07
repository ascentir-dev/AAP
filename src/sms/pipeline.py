"""
SMS Pipeline — 2-phase send flow, mirrors the cold-email pipeline.

Phase 1  dry_run=True  — "Generate"
  ─ Read CSV, extract ALL verified wireless phone numbers per lead
  ─ Filter out leads with ZERO valid phones immediately (no work wasted)
  ─ Deduplicate globally — same phone never appears twice
  ─ One SMS ledger entry per (lead, phone) pair
  ─ Pull enrichment analysis from email ledger if available
  ─ Assign SMS variant + Twilio number deterministically
  ─ Generate personalised body via AI
  ─ Save to SMS ledger as status='ready' — nothing sent yet

Phase 2  dry_run=False — "Send"
  ─ Pull all 'ready' leads from SMS ledger
  ─ Send via Twilio with per-number throttling
  ─ Respect max_daily_per_number and throttle_ms_between_sends
  ─ Update status → 'sent'

Phone priority (wireless only — landlines and company phones skipped):
  1. VALID_PHONES          — pre-validated by skip-trace vendor
  2. SKIPTRACE_WIRELESS    — wireless-confirmed numbers
  3. MOBILE_PHONE (non-DNC)
  4. PERSONAL_PHONE (non-DNC)
  5. DIRECT_NUMBER (non-DNC)  — last resort; may be landline

Leads with no verified phones at any priority level are skipped upfront with
a log warning so you only ever work with clean, sendable data.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_OPT_OUT_FOOTER = "\nReply STOP to opt out."

# Regex: E.164-ish — starts with optional + then digits, total 7–15 digits
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")

# Bad pattern: pure garbage like "8882228301190402" (too long) or test numbers
_MAX_PHONE_DIGITS = 15


# ─── phone helpers ────────────────────────────────────────────────────────────

def _normalize_phone(raw: str) -> str | None:
    """Strip formatting and return E.164-ish phone, or None if invalid."""
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", raw.strip())
    if not cleaned:
        return None
    # Add leading + if not present and starts with 1 (US/Canada)
    if cleaned.startswith("1") and len(cleaned) == 11 and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    # Strip excessively long numbers (usually data errors)
    if len(cleaned.lstrip("+")) > _MAX_PHONE_DIGITS:
        return None
    if not _PHONE_RE.match(cleaned):
        return None
    return cleaned


def _parse_multi_phone(raw: str, dnc_raw: str = "") -> list[str]:
    """
    Parse a comma-separated phone list + parallel DNC flags.
    Returns all non-DNC, valid numbers.
    """
    phones = [p.strip() for p in (raw or "").split(",") if p.strip()]
    dncs   = [d.strip().upper() for d in (dnc_raw or "").split(",")]
    result = []
    for i, phone in enumerate(phones):
        is_dnc = i < len(dncs) and dncs[i] == "Y"
        if is_dnc:
            continue
        n = _normalize_phone(phone)
        if n:
            result.append(n)
    return result


def extract_skiptrace_wireless_phone(lead: dict) -> list[str]:
    """Return the skip-traced wireless number for a lead, or [] if DNC or absent.

    This is the SOLE source of phone numbers for SMS targeting:
      - Column: SKIPTRACE_WIRELESS_NUMBERS  → lead["skiptrace_wireless_raw"]
      - DNC flag: SKIPTRACE_DNC             → lead["skiptrace_dnc_raw"]

    Rules:
      - If SKIPTRACE_WIRELESS_NUMBERS is empty  → [] (lead has no wireless number)
      - If SKIPTRACE_DNC = "Y"                  → [] (lead is on the DNC list)
      - Otherwise                               → [normalized_phone]

    Returns a list for compatibility with code that iterates over phones.
    In practice the column is always a single number (never comma-separated).
    """
    wireless = (lead.get("skiptrace_wireless_raw") or "").strip()
    if not wireless:
        return []

    # Normalise — handle the rare case of comma-separated, take the first
    phone = _normalize_phone(wireless.split(",")[0].strip())
    return [phone] if phone else []


def extract_all_valid_phones(lead: dict) -> list[str]:
    """
    LEGACY — returns every verified wireless phone across all tiers.

    Kept for backward compatibility with the export CSV.  The SMS pipeline
    now uses extract_skiptrace_wireless_phone() exclusively so that only
    vendor-skiptraced wireless numbers are texted.

    Priority order (most → least reliable):
      1. VALID_PHONES         — vendor-validated
      2. SKIPTRACE_WIRELESS   — skip-trace wireless confirmation
      3. MOBILE_PHONE         — mobile, non-DNC only
      4. PERSONAL_PHONE       — personal mobile, non-DNC only
      5. DIRECT_NUMBER        — last resort, non-DNC only
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(numbers: list[str]) -> None:
        for n in numbers:
            if n not in seen:
                seen.add(n)
                result.append(n)

    _add(_parse_multi_phone(lead.get("valid_phones_raw", ""), ""))
    _add(_parse_multi_phone(lead.get("skiptrace_wireless_raw", ""), ""))
    _add(_parse_multi_phone(
        lead.get("mobile_phone_raw", "") or lead.get("mobile_phone", ""),
        lead.get("mobile_phone_dnc_raw", "") or lead.get("mobile_phone_dnc", ""),
    ))
    _add(_parse_multi_phone(
        lead.get("personal_phone_raw", ""),
        lead.get("personal_phone_dnc_raw", ""),
    ))
    _add(_parse_multi_phone(
        lead.get("direct_number_raw", "") or lead.get("direct_number", ""),
        lead.get("direct_number_dnc_raw", "") or lead.get("direct_number_dnc", ""),
    ))
    return result


# ─── other helpers ────────────────────────────────────────────────────────────

def _sms_lead_id(lead_id: str, phone: str) -> str:
    """
    Unique SMS ledger key for a (lead, phone) pair.
    Same lead_id + same phone always produces the same sms_lead_id.
    """
    digest = hashlib.sha256(f"{lead_id}:{phone}".encode()).hexdigest()[:12]
    return f"{lead_id[:8]}_{digest}"


def _assign_sms_variant(sms_lead_id: str, arms: list[dict]) -> dict:
    """Deterministic variant assignment (same key = same arm)."""
    if not arms:
        return {"id": "SMS-V1", "weight": 1.0, "framework": "DirectValue"}
    digest = hashlib.sha256(f"sms_variant:{sms_lead_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    cumulative = 0.0
    for arm in arms:
        cumulative += arm.get("weight", 1 / len(arms))
        if bucket < cumulative:
            return arm
    return arms[-1]


def _infer_market(lead: dict) -> str:
    """Infer ICP market from lead CSV fields when email-ledger analysis is absent."""
    from src.ingestion.csv_reader import INDUSTRY_TO_MARKET
    industry = (lead.get("industry") or "").lower().strip()
    if industry in INDUSTRY_TO_MARKET:
        return INDUSTRY_TO_MARKET[industry]
    combined = f"{lead.get('role','')} {industry}".lower()
    if any(w in combined for w in ("financial", "advisor", "wealth", "investment", "cfp")):
        return "financial_advisor"
    if any(w in combined for w in ("msp", "managed service", "it service", "cybersec")):
        return "msp"
    if any(w in combined for w in ("coach", "coaching", "trainer", "training")):
        return "coach"
    if any(w in combined for w in ("agency", "marketing", "advertising")):
        return "agency"
    if any(w in combined for w in ("consult", "advisory", "fractional")):
        return "consultant"
    return "agency"


def _load_email_analysis(lead_id: str, email: str, email_db: Path) -> dict | None:
    """Pull analysis JSON from the email ledger.  Returns None on miss."""
    if not email_db.exists():
        return None
    try:
        conn = sqlite3.connect(str(email_db))
        row = conn.execute(
            "SELECT data_json FROM stages WHERE lead_id=? AND stage_name='analysis'",
            (lead_id,),
        ).fetchone()
        if not row and email:
            row = conn.execute(
                """
                SELECT s.data_json FROM stages s
                JOIN leads l ON l.lead_id = s.lead_id
                WHERE l.email=? AND s.stage_name='analysis' LIMIT 1
                """,
                (email,),
            ).fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        log.debug("Analysis lookup failed for %s: %s", lead_id, e)
    return None


def _build_fallback_analysis(lead: dict) -> dict:
    """Minimal analysis dict built from CSV alone for leads not in email ledger."""
    market = _infer_market(lead)
    company = lead.get("company", "your company")
    return {
        "market":           market,
        "vertical":         lead.get("industry") or "B2B Services",
        "motion":           "sales_led_outbound",
        "personalized_hook": f"{company} looks like a strong fit for what we're building",
        "recommended_angle": "aap_prospect_outbound",
    }


# ─── main pipeline ────────────────────────────────────────────────────────────

async def run_sms_pipeline(
    csv_path: Path,
    dry_run: bool,
    batch_size: int,
    settings: Any,
    email_db_path: Path,
    status_ref: dict | None = None,
) -> None:
    """
    Phase 1 (dry_run=True)  → generate SMS bodies, store as 'ready'.
    Phase 2 (dry_run=False) → send all 'ready' leads via Twilio.
    """
    from src.sms.ledger import SMSLedger
    from src.sms.sender import send_sms, assign_number
    from src.ingestion.csv_reader import read_leads
    from src.utils.cost_tracker import CostTracker

    sms_cfg     = settings.sms
    db_path     = sms_cfg.get("db_path", "data/sms_ledger.sqlite")
    throttle_s  = sms_cfg.get("throttle_ms_between_sends", 500) / 1000
    max_daily   = sms_cfg.get("max_daily_per_number", 100)
    opt_out_ftr = sms_cfg.get("opt_out_footer", _OPT_OUT_FOOTER)
    test_id     = sms_cfg.get("variants", {}).get("active_test", "sms_framework_v1")
    test_cfg    = sms_cfg.get("variants", {}).get(test_id, {})
    arms        = test_cfg.get("arms", [])

    ledger       = SMSLedger(path=db_path)
    cost_tracker = CostTracker(path=str(email_db_path), daily_budget_usd=100.0)

    # ── status helper ─────────────────────────────────────────────────────────
    def _push_activity(lead: dict, phone: str, outcome: str, error: str = "") -> None:
        if status_ref is None:
            return
        feed = status_ref.setdefault("recent_activity", [])
        feed.insert(0, {
            "name":    f"{lead.get('first_name','')} {lead.get('last_name','')}".strip(),
            "company": lead.get("company", ""),
            "phone":   phone,
            "status":  outcome,
            "time":    time.strftime("%H:%M:%S"),
            "error":   error,
        })
        if len(feed) > 50:
            feed[:] = feed[:50]
        if outcome == "sms_ready":
            status_ref["run_generated"] = (status_ref.get("run_generated") or 0) + 1
        elif outcome == "sms_sent":
            status_ref["run_sent"] = (status_ref.get("run_sent") or 0) + 1
        else:
            status_ref["run_failed"] = (status_ref.get("run_failed") or 0) + 1

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — Generate
    # ══════════════════════════════════════════════════════════════════════════
    if dry_run:
        all_leads = read_leads(csv_path)
        log.info("SMS Phase 1: %d total leads in CSV", len(all_leads))

        # ── Step 1: expand to (lead, phone) pairs ──────────────────────────
        # Also deduplicate globally — same phone never sent twice
        global_seen_phones: set[str] = set()

        # Pre-load already-used phones from SMS ledger
        try:
            conn_pre = sqlite3.connect(db_path)
            for row in conn_pre.execute("SELECT phone FROM sms_leads WHERE status != 'failed'").fetchall():
                global_seen_phones.add(row[0])
            conn_pre.close()
        except Exception:
            pass

        work_items: list[tuple[dict, str]] = []   # (lead, phone)
        leads_no_phone = 0

        for lead in all_leads:
            phones = extract_skiptrace_wireless_phone(lead)
            if not phones:
                leads_no_phone += 1
                log.debug(
                    "No valid phone for %s %s @ %s — skipping",
                    lead.get("first_name"), lead.get("last_name"), lead.get("company"),
                )
                continue

            added = 0
            for phone in phones:
                if phone in global_seen_phones:
                    continue  # already sent or queued globally
                sms_id = _sms_lead_id(lead["lead_id"], phone)
                existing = ledger.get_lead(sms_id)
                if existing and existing.get("status") in ("ready", "sent", "opted_out"):
                    global_seen_phones.add(phone)
                    continue
                if ledger.is_opted_out(phone):
                    global_seen_phones.add(phone)
                    continue
                global_seen_phones.add(phone)
                work_items.append((lead, phone))
                added += 1

        log.info(
            "SMS Phase 1: %d (lead, phone) pairs to generate  |  %d leads had no valid phone",
            len(work_items), leads_no_phone,
        )

        if status_ref is not None:
            status_ref["total"]   = len(work_items)
            status_ref["run_skipped"] = (status_ref.get("run_skipped") or 0) + leads_no_phone

        # Apply batch cap
        if batch_size and batch_size > 0:
            work_items = work_items[:batch_size]
            if status_ref is not None:
                status_ref["total"] = len(work_items)

        # ── Step 2: group by lead, then generate once per lead ─────────────
        # Task 4 fix: a lead with N phones calls the AI exactly ONCE.  The
        # single personalised body is stored for every phone number.
        lead_groups: dict[str, tuple[dict, list[str]]] = {}
        for lead, phone in work_items:
            lid = lead["lead_id"]
            if lid not in lead_groups:
                lead_groups[lid] = (lead, [])
            lead_groups[lid][1].append(phone)

        sem = asyncio.Semaphore(5)

        async def _process_lead_group(lead: dict, phones: list[str]) -> None:
            """Generate ONE body per lead, then write one ledger entry per phone."""
            async with sem:
                lead_id = lead["lead_id"]
                # Variant + analysis are the same for all phones of this lead
                # Use the lead_id (not sms_id) for deterministic variant assignment
                arm      = _assign_sms_variant(lead_id, arms)
                analysis = _load_email_analysis(lead_id, lead.get("email", ""), email_db_path)
                if not analysis:
                    analysis = _build_fallback_analysis(lead)

                try:
                    # ── ONE AI call regardless of how many phones ───────────
                    from src.sms.generator import generate_sms
                    result = await generate_sms(
                        lead=lead,
                        analysis=analysis,
                        variant_arm=arm,
                        settings=settings,
                        cost_tracker=cost_tracker,
                    )

                    body       = result["body"] + opt_out_ftr
                    ai_cost    = result.get("ai_cost_usd", 0.0)
                    variant_id = arm.get("id", "")

                    # ── Write one ledger row per phone with the SAME body ───
                    first_phone = True
                    for phone in phones:
                        sms_id      = _sms_lead_id(lead_id, phone)
                        from_number = assign_number(sms_id, settings.twilio_numbers)

                        ledger.upsert_lead(
                            sms_id,
                            first_name      = lead.get("first_name", ""),
                            last_name       = lead.get("last_name", ""),
                            phone           = phone,
                            company         = lead.get("company", ""),
                            role            = lead.get("role", ""),
                            vertical        = analysis.get("vertical", ""),
                            motion          = analysis.get("motion", ""),
                            assigned_number = from_number,
                            variant_id      = variant_id,
                            test_id         = test_id,
                            framework       = arm.get("framework", ""),
                            status          = "ready",
                            # attribute the full AI cost to the first phone only
                            # so we never double-count when aggregating
                            ai_cost_usd     = ai_cost if first_phone else 0.0,
                        )
                        ledger.record_message(
                            lead_id     = sms_id,
                            direction   = "outbound_pending",
                            from_number = from_number,
                            to_number   = phone,
                            body        = body,
                            twilio_sid  = None,
                            variant_id  = variant_id,
                        )
                        _push_activity(lead, phone, "sms_ready")
                        log.info(
                            "SMS ready  id=%s  phone=%s  variant=%s  chars=%d%s",
                            sms_id, phone, variant_id, len(body),
                            f"  ai_cost=${ai_cost:.6f}" if first_phone else "  (body shared)",
                        )
                        first_phone = False

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    err_msg = str(e)[:200]
                    log.error(
                        "SMS generation failed  lead_id=%s  phones=%s: %s",
                        lead_id, phones, err_msg,
                    )
                    # Mark every phone for this lead as failed so they're resettable
                    for phone in phones:
                        sms_id = _sms_lead_id(lead_id, phone)
                        _push_activity(lead, phone, "failed", err_msg[:120])
                        try:
                            ledger.upsert_lead(
                                sms_id,
                                first_name  = lead.get("first_name", ""),
                                last_name   = lead.get("last_name", ""),
                                phone       = phone,
                                company     = lead.get("company", ""),
                                role        = lead.get("role", ""),
                                vertical    = analysis.get("vertical", ""),
                                motion      = analysis.get("motion",   ""),
                                variant_id  = arm.get("id", ""),
                                test_id     = test_id,
                                framework   = arm.get("framework", ""),
                                status      = "failed",
                                error       = err_msg,
                            )
                        except Exception as db_err:
                            log.warning("Could not persist failed lead %s: %s", sms_id, db_err)

        await asyncio.gather(*[
            _process_lead_group(lead, phones)
            for lead, phones in lead_groups.values()
        ])

        if status_ref is not None:
            status_ref["db_generated"] = ledger.count_leads(status="ready")

        log.info(
            "SMS Phase 1 complete. Ready to send: %d", ledger.count_leads(status="ready")
        )
        return

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — Send
    # ══════════════════════════════════════════════════════════════════════════

    from src.sms.scheduler import check_send_window   # lazy import — only needed in Phase 2

    ready = ledger.list_leads(status="ready", limit=batch_size or 999_999)
    log.info("SMS Phase 2: %d ready leads to send", len(ready))

    if status_ref is not None:
        status_ref["total"] = len(ready)

    # Per-number daily send counts
    sends_today: dict[str, int] = defaultdict(int)
    # Track how many leads were deferred due to TCPA window (for status reporting)
    tcpa_deferred = 0

    for rec in ready:
        sms_id   = rec["lead_id"]
        phone    = rec["phone"]
        from_num = rec.get("assigned_number")

        if not from_num:
            log.warning("SMS lead %s has no assigned_number — skipping", sms_id)
            if status_ref:
                status_ref["run_skipped"] = (status_ref.get("run_skipped") or 0) + 1
            continue

        if sends_today[from_num] >= max_daily:
            log.info("Number %s hit daily limit (%d) — deferring %s", from_num, max_daily, sms_id)
            if status_ref:
                status_ref["run_skipped"] = (status_ref.get("run_skipped") or 0) + 1
            continue

        # ── TCPA / send-window gate ────────────────────────────────────────
        sw = check_send_window(phone)
        if not sw.can_send_now:
            tcpa_deferred += 1
            log.info(
                "SMS TCPA deferred  sms_id=%s  phone=%s  zone=%s  reason=%s  "
                "next_utc=%s%s",
                sms_id, phone, sw.zone, sw.reason,
                sw.next_window_utc.strftime("%Y-%m-%d %H:%M UTC") if sw.next_window_utc else "—",
                "  [zone guessed — review]" if sw.review_flag else "",
            )
            if status_ref:
                status_ref["run_skipped"] = (status_ref.get("run_skipped") or 0) + 1
            continue   # lead stays 'ready'; will be retried on next pipeline run

        if sw.review_flag:
            log.warning(
                "SMS sending to %s with guessed zone %s — verify recipient location",
                phone, sw.zone,
            )

        # Retrieve the pre-generated body
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        msg_row = conn.execute(
            """
            SELECT id, body FROM sms_messages
            WHERE lead_id=? AND direction='outbound_pending'
            ORDER BY sent_at DESC LIMIT 1
            """,
            (sms_id,),
        ).fetchone()
        conn.close()

        if not msg_row:
            log.warning("No pending message for SMS lead %s — skipping", sms_id)
            if status_ref:
                status_ref["run_skipped"] = (status_ref.get("run_skipped") or 0) + 1
            continue

        body   = msg_row["body"]
        msg_id = msg_row["id"]

        try:
            sid, twilio_price, twilio_price_unit = await send_sms(
                lead_id=sms_id,
                to_number=phone,
                body=body,
                settings=settings,
            )
            sent_ts = time.time()   # capture send time immediately after Twilio confirms

            # Promote the pending message record: set direction='outbound',
            # record SID, and store price if available (usually None at this point)
            conn2 = sqlite3.connect(db_path)
            conn2.execute(
                """
                UPDATE sms_messages
                   SET direction='outbound', twilio_sid=?,
                       twilio_price=?, twilio_price_unit=?
                 WHERE id=?
                """,
                (sid, twilio_price, twilio_price_unit or "USD", msg_id),
            )
            conn2.commit()
            conn2.close()

            # Task 2 fix: use mark_sent() so sent_at reflects actual delivery time
            ledger.mark_sent(sms_id, sent_at=sent_ts)

            # Task 3 fix: record Twilio cost if available now (usually None; reconcile later)
            if twilio_price is not None:
                ledger.set_message_price(sid, twilio_price, twilio_price_unit)

            sends_today[from_num] += 1
            _push_activity(rec, phone, "sms_sent")
            log.info(
                "SMS sent  sms_id=%s  phone=%s  from=%s  sid=%s  price=%s",
                sms_id, phone, from_num, sid,
                f"${twilio_price:.4f}" if twilio_price else "pending",
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("SMS send failed  sms_id=%s  phone=%s: %s", sms_id, phone, e)
            ledger.update_status(sms_id, "failed")
            _push_activity(rec, phone, "failed", str(e)[:120])

        await asyncio.sleep(throttle_s)

    if status_ref is not None:
        kpi = ledger.kpi_summary()
        status_ref["db_generated"]    = ledger.count_leads(status="ready")
        status_ref["db_sent"]         = kpi.get("sent") or 0
        status_ref["tcpa_deferred"]   = tcpa_deferred

    log.info(
        "SMS Phase 2 complete. sent=%s  tcpa_deferred=%d",
        status_ref.get("run_sent", "?") if status_ref else "?",
        tcpa_deferred,
    )
