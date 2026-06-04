"""
Core pipeline. For each lead, runs all stages in order with retries + cost tracking.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.ingestion.csv_reader import read_leads
from src.enrichment.website import get_website_data
from src.enrichment.linkedin import get_linkedin_data
from src.analysis.fit_analyzer import analyze_fit
from src.analytics.variant_assigner import assign_variant
from src.ai_cold_email.email.generator import generate_email
from src.ai_cold_email.video.script.video_scripts import render_script, assign_variant as assign_video_variant
from src.ai_cold_email.video.tts.tts_client import synthesize
from src.ai_cold_email.video.scroll.recorder import record_scroll
from src.ai_cold_email.video.composite.compositor import composite_video
from src.ai_cold_email.video.composite.browser_frame import make_browser_frame, CHROME_HEADER_HEIGHT
from src.hosting.uploader import upload_video, upload_thumbnail, generate_landing_page
from src.hosting.thumbnail import make_email_thumbnail
from src.ai_cold_email.smartlead.client import push_to_smartlead
from src.utils.ledger import Ledger
from src.utils.cost_tracker import CostTracker
from src.utils.settings import Settings
from src.utils.validator import pre_upload_gate, post_upload_gate, ValidationError
import re
import src.utils.video_tracker as video_tracker

log = logging.getLogger(__name__)

# ── System-error classification ───────────────────────────────────────────────
_SYSTEM_ERROR_PATTERNS = (
    # Network / TLS
    "err_cert", "err_ssl", "err_connection", "err_name_not_resolved",
    "err_timed_out", "net::", "ssl", "certificate",
    # Playwright
    "page.goto", "target closed", "browser has disconnected",
    "execution context was destroyed",
    # HTTP transport
    "timeout", "connecttimeout", "readtimeout",
    # API 5xx
    "502", "503", "504", "overloaded", "service unavailable",
)


def _is_system_error(exc: BaseException) -> bool:
    """Return True if the exception is a transient infrastructure error."""
    msg = str(exc).lower()
    return any(pat in msg for pat in _SYSTEM_ERROR_PATTERNS)


def _get_ledger_db(ledger: "Ledger"):
    """Return the raw sqlite3 connection from the ledger for emergency stage cleanup."""
    try:
        return ledger._conn
    except Exception:
        return None


# ── Company-name cleaner ──────────────────────────────────────────────────────
# Note: trailing \b intentionally omitted after the suffix group — a trailing
# period (e.g. "Ltd." or "Inc.") is consumed by \.? so there is no word
# character at the match boundary and \b would fail. Leading \b prevents
# false matches inside compound words (e.g. "Costco" won't lose "co").
_LEGAL_SUFFIX_RE = re.compile(
    r'\s*,?\s*\b(?:Inc\.?|LLC\.?|Ltd\.?|Corp\.?|Co\.?|Limited|Incorporated|Corporation|'
    r'L\.L\.C\.?|L\.P\.?|LLP|L\.L\.P\.?|P\.C\.?|P\.A\.?|PLLC|LLLP|'
    r'GmbH|S\.A\.?|AG|NV|BV|Pty\.?|Pvt\.?)\s*$',
    re.IGNORECASE,
)


def _clean_company(name: str) -> str:
    """Strip legal suffixes (Inc., LLC, Ltd., Corp., etc.) from a company name.

    Examples:
        "Acme Corp."         → "Acme"
        "Smith & Jones, LLC" → "Smith & Jones"
        "Bright Future Inc"  → "Bright Future"
        "Ascentir"           → "Ascentir"  (unchanged)
    """
    if not name:
        return name
    cleaned = _LEGAL_SUFFIX_RE.sub('', name).strip().rstrip(',').strip()
    return cleaned or name  # fall back to original if result is somehow empty


# ── Email-only bridge-line replacements ───────────────────────────────────────
# When a lead doesn't get a video, these swap out the "I recorded a quick video"
# lines so the email doesn't promise something that isn't there.
# Each tuple is (regex_pattern, replacement_text).
_VIDEO_BRIDGE_SUBS: list[tuple[str, str]] = [
    # V1 — channels the guarantee momentum straight into the demo
    (
        r"I recorded a quick video,?\s+your site right here on screen:",
        "See the exact system we'd run for {company}:",
    ),
    # V2 — strips it bare: one action, zero fluff
    (
        r"By the way,?\s+I'?m not a robot!?\s+Recorded a quick video to say hello and explain how it works,?\s+so you know I'?m not sending this from a big list\.\.\.",
        "By the way, I write these personally, not from bulk software. One 20-minute call. That's all this is:",
    ),
    # V3 — specificity before the decision (Kennedy: exact numbers kill hesitation)
    (
        r"Your site is right here on screen:",
        "See the exact numbers before deciding anything:",
    ),
    # V4 / V7 — offer relief from the pain just agitated
    (
        r"so I recorded a quick video to explain my offer(?:[^:]*)?:",
        "see the exact system that handles this done-for-you:",
    ),
    # V5 — proof bullets create FOMO; "am I next?" closes the loop
    (
        r"Recorded a personalized video,?\s+your site is literally on screen:",
        "See if {company} qualifies to be next on this list:",
    ),
    # V6 — question was already asked; one step, no repetition
    (
        r"Under 60 seconds,?\s+your site on screen:",
        "20 minutes to find out if the numbers work:",
    ),
    # V8 — scarcity was already planted; reinforce it, don't dilute it
    (
        r"60-second video,?\s+your site on screen:",
        "See if you're still a fit before we go wider:",
    ),
    # V9 — diagnosis was sharp; make the fix feel inevitable
    (
        r"Recorded a video showing exactly what (?:we'?d|we would) do about it:",
        "See the exact 120-day fix. No commitment needed:",
    ),
    # ── Broader catch-alls for any remaining video-reference patterns ──────────
    # "I recorded/I've recorded/recorded a ... video...:"
    (
        r"(?:so )?(?:I(?:'ve)? )?[Rr]ecorded a (?:\w+ )?video[^:]*:",
        "See the exact system that handles this done-for-you:",
    ),
    # "I made/created/put together a (quick/short/personalized) video...:"
    (
        r"I(?:'ve)? (?:made|created|put together|prepared) a (?:\w+ )?video[^:]*:",
        "See the exact system that handles this done-for-you:",
    ),
    # "Here's/Here is a video / Here's a quick video...:"
    (
        r"[Hh]ere(?:'s| is| are) a? ?(?:\w+ )?video[^:]*:",
        "Here's what the first 30 days looks like for {company}:",
    ),
    # "Check out this video / Watch this video:"
    (
        r"(?:[Cc]heck out|[Ww]atch) (?:this|the) (?:\w+ )?video[^:]*:",
        "See the exact numbers before deciding anything:",
    ),
    # "I wanted to share/send a quick video:"
    (
        r"I wanted to (?:share|send) a (?:\w+ )?video[^:]*:",
        "See the exact system that handles this done-for-you:",
    ),
    # "quick/short/personalized video for you:"  (bare noun phrase lead-in)
    (
        r"(?:quick|short|personalized|personal|custom) video for you[^:]*:",
        "See the exact system that handles this done-for-you:",
    ),
    # "your site is on screen:" / "your site right here on screen:"
    (
        r"your site (?:is )?(?:right )?(?:here )?on screen:",
        "See the exact numbers before deciding anything:",
    ),
    # Generic "video:" line that leads directly into {VIDEO_LINK}
    # Only strip if the word "video" appears at end of a sentence/clause before a colon
    (
        r"\bvideo\b[^:.\n]*:",
        "See the exact system we'd run for {company}:",
    ),
]


def _strip_video_references(body: str, company: str = "") -> str:
    """Replace video-bridge lines with Kennedy-style alternatives for email-only sends."""
    for pattern, replacement in _VIDEO_BRIDGE_SUBS:
        repl = replacement.replace("{company}", company) if company else replacement
        body = re.sub(pattern, repl, body, flags=re.IGNORECASE)

    # Final sweep: remove any remaining full sentences that reference "video",
    # "recorded", "watch", or "on screen" — handles patterns not caught above.
    # Targets complete sentences (ends with . or :) containing these words.
    _RESIDUAL_VIDEO_PATTERNS = [
        # Sentence containing "video" that ends with a period or is standalone
        r"[A-Z][^.!?\n]*\b(?:video|recording)\b[^.!?\n]*[.!?]",
        # "I recorded / I've recorded" standalone phrases
        r"I(?:'ve)? recorded[^.!?\n]*[.!?]",
        # "watch the video" or "watch this" references
        r"[Ww]atch (?:the|this|my) (?:video|recording)[^.!?\n]*[.!?]",
        # "personalized video" standalone
        r"personalized video[^.!?\n]*[.!?]",
    ]
    _replacement = f"See the exact system we'd run for {company}." if company else "See the exact system we'd run for you."
    for pattern in _RESIDUAL_VIDEO_PATTERNS:
        body = re.sub(pattern, _replacement, body, flags=re.IGNORECASE)

    return body


# Market → native vocabulary for the email-only CTA (Kennedy: market vocabulary is non-negotiable)
_MARKET_CTA_TERM: dict[str, str] = {
    "coach":             "qualified discovery calls",
    "agency":            "qualified new-biz calls",
    "consultant":        "qualified intro calls",
    "financial_advisor": "qualified prospect meetings",
    "msp":               "qualified prospect calls",
}


def _market_cta_term(market: str) -> str:
    """Return the market-appropriate appointment vocabulary for the email-only CTA."""
    return _MARKET_CTA_TERM.get((market or "").lower().strip(), "qualified appointments")


async def process_lead(
    lead: dict[str, Any],
    settings: Settings,
    ledger: Ledger,
    cost_tracker: CostTracker,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run all pipeline stages for a single lead. Returns final state."""
    lead_id = lead["lead_id"]
    # Strip legal suffixes (Inc., LLC, Ltd. etc.) from company name so emails read naturally.
    if lead.get("company"):
        lead["company"] = _clean_company(lead["company"])
    log.info(f"[{lead_id}] Processing {lead['first_name']} @ {lead['company']}")

    # Save basic identity fields immediately so the lead row always shows name/company
    # even if it gets skipped or fails early (before save_lead_metadata is reached).
    ledger.save_lead_metadata(
        lead_id,
        email=lead.get("email", ""),
        first_name=lead.get("first_name", ""),
        last_name=lead.get("last_name", ""),
        company=lead.get("company", ""),
        website=lead.get("website", ""),
        role=lead.get("role", ""),
    )

    # 1. Enrichment — fast-path skips Playwright/Apify for pre-enriched leads
    if not ledger.has_stage(lead_id, "enrichment"):
        website_data  = await get_website_data(lead, settings)
        linkedin_data = await get_linkedin_data(lead, settings, cost_tracker)
        ledger.save_stage(lead_id, "enrichment", {
            "website":  website_data,
            "linkedin": linkedin_data,
        })

    enrichment = ledger.get_stage(lead_id, "enrichment") or {}

    # 2. Fit analysis (Claude Haiku)
    if not ledger.has_stage(lead_id, "analysis"):
        analysis = await analyze_fit(lead, enrichment, settings, cost_tracker)
        ledger.save_stage(lead_id, "analysis", analysis)

    analysis = ledger.get_stage(lead_id, "analysis")
    if not analysis:
        # Corrupt or missing analysis stage — clear it so it regenerates on retry
        log.warning("[%s] analysis stage missing or corrupt — clearing for retry", lead_id)
        raise ValueError("analysis stage is None after save — ledger may be corrupt, retrying")

    # Skip logic disabled — every lead is processed regardless of AI analysis output.
    # If Claude returned skip=true, log it for visibility but continue processing.
    if analysis.get("skip"):
        log.info(
            "[%s] Analysis suggested skip (%s) — skip disabled, continuing.",
            lead_id, analysis.get("skip_reason", "no reason given"),
        )

    # Save vertical, motion, market, intent_confidence to ledger
    ledger.save_lead_metadata(
        lead_id,
        email=lead.get("email", ""),
        vertical=analysis.get("vertical", ""),
        motion=analysis.get("motion", ""),
        intent_confidence=analysis.get("intent_confidence"),
        recommended_angle=analysis.get("recommended_angle", ""),
    )
    # Propagate confirmed market back into lead dict for downstream market-aware steps
    if analysis.get("market"):
        lead["market"] = analysis["market"]

    # ── Video gating — skip video for low-intent leads ────────────────────────
    intent_score     = float(analysis.get("intent_confidence") or 0)
    video_threshold  = float(settings.video.get("intent_threshold", 0.0))
    skip_video       = video_threshold > 0 and intent_score < video_threshold
    if skip_video:
        log.info(
            f"[{lead_id}] intent_confidence={intent_score:.2f} < threshold={video_threshold:.2f}"
            " — email-only mode (no video generation)"
        )

    # 3. Variant assignment (deterministic, hash-based)
    test_config = settings.active_test_config()
    if test_config:
        variant_arm = assign_variant(lead_id, test_config)
    else:
        # No active test — use a minimal passthrough arm
        variant_arm = {
            "id": "default",
            "test_id": None,
            "smartlead_campaign_id": settings.smartlead_campaign_id,
            "overrides": {},
        }

    # Save variant_id, test_id, and email_type to ledger
    ledger.save_lead_metadata(
        lead_id,
        variant_id=variant_arm.get("id", ""),
        test_id=variant_arm.get("test_id", ""),
        email_type="email_only" if skip_video else "video",
    )

    # 4. Email generation (Claude Sonnet, variant-aware)
    # Pass has_video so Claude writes video-free copy for email-only leads —
    # no "recorded a video" language anywhere, just a direct CTA email.
    if not ledger.has_stage(lead_id, "email"):
        email = await generate_email(
            lead, analysis, variant_arm, settings, cost_tracker,
            has_video=not skip_video,
        )
        ledger.save_stage(lead_id, "email", email)

    email = ledger.get_stage(lead_id, "email")
    if not email or not email.get("body"):
        # Corrupt or empty email stage — clear it so it regenerates
        log.warning("[%s] email stage missing/corrupt body — clearing for retry", lead_id)
        ledger._execute("DELETE FROM stages WHERE lead_id=? AND stage_name='email'", (lead_id,))
        ledger._conn.commit()
        raise ValueError("email stage body is None or empty — cleared, will regenerate on retry")
    # Normalise cached emails that may have been stored before dash-replacement was added
    email = dict(email)
    email["body"] = email["body"].replace("—", " - ").replace("–", "-")

    # Save framework_used + subject_line to ledger for analytics
    ledger.save_lead_metadata(
        lead_id,
        framework=email.get("framework_used", ""),
        subject_line=email.get("subject", ""),
    )

    if not skip_video:
        # ── Paths ─────────────────────────────────────────────────────────────
        Path("data/videos").mkdir(parents=True, exist_ok=True)
        audio_path       = Path(f"data/videos/{lead_id}_audio.mp3")
        scroll_path      = Path(f"data/videos/{lead_id}_scroll.mp4")
        frame_path       = Path(f"data/videos/{lead_id}_frame.png")
        final_video_path = Path(f"data/videos/{lead_id}_final.mp4")
        email_thumb_path = Path(f"data/videos/{lead_id}_email_thumb.jpg")
        face_path        = next(
            (p for p in [Path("assets/frank.jpg"), Path("assets/frank.png")] if p.exists()),
            Path("assets/frank.jpg"),
        )

        # 5. Video script — deterministic variant, market-aware if market is set
        video_variant_id = assign_video_variant(lead_id)   # hash on lead_id (stable)
        script_text = render_script(
            video_variant_id,
            {"first_name": lead["first_name"], "company": lead["company"]},
            market=lead.get("market") or None,
        )
        ledger.save_stage(lead_id, "video_script", {
            "variant_id": video_variant_id,
            "script": script_text,
        })

        # 6. TTS — cloned voice for high-intent leads, free Edge TTS otherwise
        if not audio_path.exists():
            await synthesize(
                script_text, audio_path, settings, cost_tracker,
                lead_id=lead_id,
                intent_score=intent_score,
            )

        # 7. Scroll capture — records their actual website, captures thumbnail
        _res = settings.video.get("resolution") or {}
        W = _res.get("width", 1280)
        H = _res.get("height", 720)
        content_h = H - CHROME_HEADER_HEIGHT   # 624px — content area below Chrome header
        scroll_result = None
        if not scroll_path.exists():
            scroll_result = await record_scroll(
                url=lead["website"],
                duration_seconds=settings.video.get("duration_seconds", 55),
                output_path=scroll_path,
                settings=settings,
                viewport_height=content_h,
            )
        else:
            # Already recorded — reconstruct minimal result for downstream use.
            # Thumbnail is per-lead (same stem, _thumb suffix) — check for it so
            # resumed runs can still generate the email thumbnail + cover art.
            from src.ai_cold_email.video.scroll.recorder import ScrollResult
            thumb_path = Path(f"data/videos/{lead_id}_thumb.jpg")
            scroll_result = ScrollResult(
                path=scroll_path,
                page_title=lead["company"],
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )

        # ── Scroll fallback: if recording is empty/corrupt, switch to email-only ──
        # Some websites block Playwright or fail to load — the result is a tiny
        # video file (< 500 KB for a 30-second recording).  Rather than failing
        # the lead entirely, degrade gracefully to email-only mode.
        _MIN_SCROLL_BYTES = 500_000
        if scroll_path.exists() and scroll_path.stat().st_size < _MIN_SCROLL_BYTES:
            log.warning(
                "[%s] Scroll recording too small (%s bytes) for %s — "
                "website likely blocked Playwright. Falling back to email-only.",
                lead_id, scroll_path.stat().st_size, lead.get("website", ""),
            )
            # Clean up partial video artefacts so a future retry starts fresh
            for _p in [scroll_path, audio_path, frame_path, final_video_path, email_thumb_path]:
                if _p.exists():
                    try:
                        _p.unlink()
                    except OSError:
                        pass
            skip_video = True   # re-route through email-only path below

        # ── Steps 8-11 only run if scroll succeeded (skip_video may have been
        # set True by the scroll fallback check above) ────────────────────────
        if not skip_video:
            # 8. Browser frame — Chrome dark-mode overlay with real URL + page title
            if not frame_path.exists():
                make_browser_frame(
                    url=lead["website"],
                    width=W,
                    height=H,
                    out_path=frame_path,
                    page_title=(scroll_result.page_title if scroll_result else None) or lead.get("company", ""),
                )

            # 9. Composite — scroll + Chrome frame + face circle + CTA + audio
            if not final_video_path.exists():
                await composite_video(
                    scroll_video=scroll_path,
                    audio=audio_path,
                    corner_image=face_path,
                    output_path=final_video_path,
                    settings=settings,
                    browser_frame=frame_path,
                    content_y=CHROME_HEADER_HEIGHT,
                    thumbnail_path=scroll_result.thumbnail_path if scroll_result else None,
                )

            # 10. Generate email thumbnail BEFORE the gate
            if scroll_result and scroll_result.thumbnail_path and scroll_result.thumbnail_path.exists():
                if not email_thumb_path.exists():
                    make_email_thumbnail(scroll_result.thumbnail_path, email_thumb_path)

            # ── Gate 1: validate all local files before touching R2 ──────────
            pre_upload_gate(
                lead_id=lead_id,
                paths={
                    "audio":       audio_path,
                    "scroll":      scroll_path,
                    "final_video": final_video_path,
                    "thumb":       Path(f"data/videos/{lead_id}_thumb.jpg"),
                    "email_thumb": email_thumb_path,
                },
                email=email,
                face_path=face_path,
            )

            # 11. Upload to R2 — video + thumbnail + static landing page
            if not ledger.has_stage(lead_id, "hosting"):
                identity = settings.your_identity if isinstance(settings.your_identity, dict) else {}
                cta_url  = identity.get("calendly_url", "") or settings.book_a_call_url

                video_url = await upload_video(final_video_path, lead_id, settings)

                thumbnail_url = ""
                if email_thumb_path.exists():
                    thumbnail_url = await upload_thumbnail(email_thumb_path, lead_id, settings)

                landing_url = await generate_landing_page(
                    lead=lead, video_url=video_url, settings=settings, cta_url=cta_url,
                )

                worker_url   = getattr(settings, "cloudflare_worker_url", "").rstrip("/")
                tracking_url = (
                    f"{worker_url}/v/{lead_id}"
                    if worker_url
                    else landing_url  # no worker configured → link directly to R2 landing page
                )

                ledger.save_stage(lead_id, "hosting", {
                    "video_url":     video_url,
                    "thumbnail_url": thumbnail_url,
                    "landing_url":   landing_url,
                    "tracking_url":  tracking_url,
                })
                video_tracker.log_sent(
                    lead_id=lead_id,
                    variant_id=video_variant_id,
                    video_url=video_url,
                    email=lead.get("email", ""),
                    company=lead.get("company", ""),
                    cta_url=cta_url,
                )

    # ── Email-only path — runs for BOTH:
    #   (a) leads below the intent threshold (skip_video=True from the start), AND
    #   (b) leads whose scroll recording failed (skip_video set True by fallback).
    # Using `if skip_video` (not `else`) so the fallback case is also caught.
    if skip_video:
        # Email-only: no video generation, no R2 upload.
        # CTA button in the email links directly to Calendly.
        if not ledger.has_stage(lead_id, "hosting"):
            identity = settings.your_identity if isinstance(settings.your_identity, dict) else {}
            cta_url  = identity.get("calendly_url", "") or settings.book_a_call_url
            ledger.save_stage(lead_id, "hosting", {
                "video_url":     "",
                "thumbnail_url": "",
                "landing_url":   cta_url,
                "tracking_url":  cta_url,
                "email_only":    True,
            })
            video_tracker.log_email_only_sent(
                lead_id=lead_id,
                variant_id=variant_arm.get("id", "default"),
                email=lead.get("email", ""),
                company=lead.get("company", ""),
                cta_url=cta_url,
            )
            log.info(f"[{lead_id}] email-only hosting record saved (tracking_url → Calendly)")

    hosting = ledger.get_stage(lead_id, "hosting") or {}
    email   = ledger.get_stage(lead_id, "email") or {}

    # ── Gate 2: validate all remote URLs before sending anything ─────────────
    if not skip_video:
        identity = settings.your_identity if isinstance(settings.your_identity, dict) else {}
        expected_calendly = identity.get("calendly_url", "") or settings.book_a_call_url
        post_upload_gate(
            lead_id=lead_id,
            hosting=hosting,
            email=email,
            expected_calendly_url=expected_calendly,
        )

    # 11. Push to the variant arm's Smartlead campaign
    campaign_id   = variant_arm.get("smartlead_campaign_id") or settings.smartlead_campaign_id
    push_settings = settings.model_copy(update={"smartlead_campaign_id": campaign_id})

    if not dry_run and not ledger.has_stage(lead_id, "smartlead"):
        tracking_url  = hosting.get("tracking_url") or hosting.get("landing_url", "")
        thumbnail_url = hosting.get("thumbnail_url", "")

        # Start from the raw Claude-generated body every time.
        # email_body is defined here so all branches below can build on it safely.
        raw_body = email.get("body") or ""
        if not raw_body:
            raise ValueError(f"Email body is empty or None for lead {lead_id} — email stage may be corrupt. Clear the email stage and retry.")

        # Build the email body.
        #
        # Email-only path (no video):
        #   New emails (has_video=no): Claude writes the CTA directly — no {VIDEO_LINK}
        #   in the body. Strip any residual video language from older cached emails and
        #   inject the Reply VIDEO block only if the placeholder is still present.
        #
        # Video path:
        #   Replace {VIDEO_LINK} with a clickable thumbnail image (or plain URL).
        if hosting.get("email_only"):
            company  = lead.get("company", "")
            market   = lead.get("market", "") or analysis.get("market", "")
            cta_term = _market_cta_term(market)
            # Always strip residual video language (handles older cached email bodies).
            raw_body = _strip_video_references(raw_body, company)

            if "{VIDEO_LINK}" in raw_body:
                # Legacy cached email body — replace the placeholder with the CTA block.
                video_block = (
                    f'<p style="margin:20px 0;font-family:Arial,sans-serif;font-size:14px;'
                    f'color:#1a1a1a;line-height:1.6;">'
                    f'Reply <strong>AI DEMO</strong> &#8212; I&#8217;ll send a 60-second demo showing '
                    f'exactly how the system books {company} 30 {cta_term} in 30 days. '
                    f'No call, no pitch. Just the demo.'
                    f'</p>'
                )
                email_body = raw_body.replace("{VIDEO_LINK}", video_block)
            else:
                # New-format email body — CTA already written by Claude, no replacement needed.
                email_body = raw_body

        elif thumbnail_url:
            video_block = (
                f'<a href="{tracking_url}" style="display:block;text-decoration:none;'
                f'margin:20px 0;">'
                f'<img src="{thumbnail_url}" width="560" alt="Click to watch" '
                f'style="border-radius:8px;max-width:100%;display:block;border:0;" />'
                f'</a>'
            )
            email_body = raw_body.replace("{VIDEO_LINK}", video_block)
        else:
            email_body = raw_body.replace("{VIDEO_LINK}", tracking_url)

        result = await push_to_smartlead(
            lead=lead,
            email_subject=email["subject"],
            email_body=email_body,
            settings=push_settings,
        )
        ledger.save_stage(lead_id, "smartlead", result)

    final_status = "dry_run" if dry_run else "sent"
    ledger.mark_complete(lead_id, status=final_status)
    log.info(f"[{lead_id}] Complete. Cost: ${cost_tracker.lead_cost(lead_id):.4f}")
    return {"lead_id": lead_id, "status": final_status, "landing_url": hosting["landing_url"]}


async def run_pipeline(
    csv_path: Path,
    single_lead_index: int | None,
    resume: bool,
    dry_run: bool,
    settings: Settings,
    status_ref: "dict | None" = None,
    batch_size: int = 100,
) -> None:
    """Run the full pipeline for every lead in the CSV.

    batch_size  — cap how many leads are processed per run (default 100).
    status_ref  — optional mutable dict (shared with the dashboard) that
                  receives live counts and a per-lead activity feed.
    """
    from datetime import datetime as _dt

    ledger = Ledger("ledger.sqlite")
    cost_tracker = CostTracker(daily_budget_usd=settings.max_daily_budget_usd)

    all_leads = read_leads(csv_path)

    if single_lead_index is not None:
        leads_to_run = [all_leads[single_lead_index]]
        duplicate_count = 0
    else:
        # ── Smart deduplication ───────────────────────────────────────────────
        # Skip any lead whose email was already successfully sent to Smartlead.
        # The lead_id is a hash of the email, so the same prospect in two
        # different CSVs produces the same ID and is automatically deduplicated.
        leads_to_run: list = []
        duplicate_count = 0
        for lead in all_leads:
            row = ledger._execute(
                "SELECT status FROM leads WHERE lead_id=?", (lead["lead_id"],)
            ).fetchone()
            existing_status = row["status"] if row else None

            if existing_status in ("sent", "success"):
                # Already pushed to Smartlead — never re-process.
                duplicate_count += 1
                log.debug(
                    "[%s] duplicate — already sent, skipping",
                    lead.get("email", lead["lead_id"]),
                )
            elif dry_run and existing_status in ("dry_run",):
                # Phase 1 (Personalise): already personalised —
                # no need to re-run.  dry_run leads sit in the queue until Phase 2
                # (Push to Smartlead) picks them up.
                duplicate_count += 1
                log.debug(
                    "[%s] already personalised (status=%s) — skipping Phase 1 re-run",
                    lead.get("email", lead["lead_id"]), existing_status,
                )
            else:
                leads_to_run.append(lead)

        if resume:
            # resume skips already-sent/dry_run leads (everything in is_complete)
            leads_to_run = [l for l in leads_to_run if not ledger.is_complete(l["lead_id"])]

    # ── Batch cap ─────────────────────────────────────────────────────────────
    # Prevent enormous runs from overwhelming the system.  The UI defaults to
    # 100 leads per click; re-click to process the next 100.
    if single_lead_index is None and batch_size and len(leads_to_run) > batch_size:
        log.info("Batch cap %d applied — %d leads queued, processing first %d",
                 batch_size, len(leads_to_run), batch_size)
        leads_to_run = leads_to_run[:batch_size]

    # Report initial totals to the live status dashboard
    if status_ref is not None:
        status_ref["total"]           = len(leads_to_run)
        status_ref["duplicate_count"] = duplicate_count
        status_ref["recent_activity"] = []   # clear feed for this run

    log.info(
        "Processing %d leads  (%d duplicates skipped, %d in batch)",
        len(leads_to_run), duplicate_count, len(leads_to_run),
    )
    semaphore = asyncio.Semaphore(settings.max_concurrent_leads)

    async def bounded(lead):
        async with semaphore:
            last_error = None
            result = None
            for attempt in range(1, 3):  # up to 2 in-run attempts for system errors
                try:
                    result = await process_lead(lead, settings, ledger, cost_tracker, dry_run)
                    break  # success
                except ValidationError as e:
                    log.error(
                        "[%s] VALIDATION ERROR (not retrying): %s", lead["lead_id"], e
                    )
                    ledger.mark_failed(lead["lead_id"], f"VALIDATION: {e}")
                    result = {"lead_id": lead["lead_id"], "status": "failed", "error": str(e)}
                    break
                except Exception as e:
                    from tenacity import RetryError
                    cause = e
                    if isinstance(e, RetryError):
                        try:
                            cause = e.last_attempt.exception()
                        except Exception:
                            pass
                    err_msg = f"{type(cause).__name__}: {cause}"
                    last_error = err_msg

                    if _is_system_error(cause):
                        if attempt < 2:
                            log.warning(
                                "[%s] System error on attempt %d — clearing stages and retrying: %s",
                                lead["lead_id"], attempt, err_msg[:120],
                            )
                            # Clear any partial stages so the retry starts fresh
                            _db = _get_ledger_db(ledger)
                            if _db:
                                _db.execute(
                                    "DELETE FROM stages WHERE lead_id = ?",
                                    (lead["lead_id"],),
                                )
                                _db.commit()
                            await asyncio.sleep(3 * attempt)  # brief back-off
                            continue
                        else:
                            # Still failing after retry — clear the record entirely so the
                            # next batch run picks it up fresh (do NOT mark as failed).
                            log.error(
                                "[%s] System error persists after %d attempts — "
                                "clearing record for next-run retry: %s",
                                lead["lead_id"], attempt, err_msg[:120],
                            )
                            _db = _get_ledger_db(ledger)
                            if _db:
                                _db.execute(
                                    "DELETE FROM stages WHERE lead_id = ?",
                                    (lead["lead_id"],),
                                )
                                _db.execute(
                                    "DELETE FROM leads WHERE lead_id = ?",
                                    (lead["lead_id"],),
                                )
                                _db.commit()
                            result = {
                                "lead_id": lead["lead_id"],
                                "status": "retrying",
                                "error": err_msg,
                            }
                            break
                    else:
                        # Non-system error — mark as failed immediately, no retry
                        log.error(
                            "[%s] Non-system error: %s", lead["lead_id"], err_msg,
                            exc_info=True,
                        )
                        ledger.mark_failed(lead["lead_id"], err_msg)
                        result = {
                            "lead_id": lead["lead_id"],
                            "status": "failed",
                            "error": err_msg,
                        }
                        break
            else:
                # Exhausted loop without breaking (safety net — should not happen)
                ledger.mark_failed(lead["lead_id"], last_error or "Unknown error")
                result = {
                    "lead_id": lead["lead_id"],
                    "status": "failed",
                    "error": last_error,
                }

            # Push to the live activity feed visible in the dashboard
            if status_ref is not None:
                feed = status_ref.setdefault("recent_activity", [])
                feed.insert(0, {
                    "name":    f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
                    "company": lead.get("company", ""),
                    "email":   lead.get("email", ""),
                    "status":  result["status"],
                    "label":   "Queued for retry" if result["status"] == "retrying" else "",
                    "error":   result.get("error", ""),
                    "time":    _dt.utcnow().strftime("%H:%M:%S"),
                })
                del feed[50:]   # keep the 50 most recent

            return result

    results = await asyncio.gather(*(bounded(lead) for lead in leads_to_run))

    # Summary
    sent     = sum(1 for r in results if r["status"] == "sent")
    skipped  = sum(1 for r in results if r["status"] == "skipped")
    failed   = sum(1 for r in results if r["status"] == "failed")
    retrying = sum(1 for r in results if r["status"] == "retrying")
    log.info(
        "Done. Sent: %d, Skipped: %d, Failed: %d, Queued-for-retry: %d, Duplicates: %d",
        sent, skipped, failed, retrying, duplicate_count,
    )
    log.info(f"Total cost: ${cost_tracker.total():.2f}")
