"""
Core pipeline. For each lead, runs all stages in order with retries + cost tracking.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.ingestion.csv_reader import read_leads
from src.enrichment.website import scrape_website
from src.enrichment.linkedin import enrich_linkedin
from src.analysis.fit_analyzer import analyze_fit
from src.analytics.variant_assigner import assign_variant
from src.ai_cold_email.email.generator import generate_email
from src.ai_cold_email.video.script.builder import build_script
from src.ai_cold_email.video.tts.tts_client import synthesize
from src.ai_cold_email.video.scroll.recorder import record_scroll
from src.ai_cold_email.video.composite.compositor import composite_video
from src.hosting.uploader import upload_video, generate_landing_page
from src.ai_cold_email.smartlead.client import push_to_smartlead
from src.utils.ledger import Ledger
from src.utils.cost_tracker import CostTracker
from src.utils.settings import Settings

log = logging.getLogger(__name__)


async def process_lead(
    lead: dict[str, Any],
    settings: Settings,
    ledger: Ledger,
    cost_tracker: CostTracker,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run all pipeline stages for a single lead. Returns final state."""
    lead_id = lead["lead_id"]
    log.info(f"[{lead_id}] Processing {lead['first_name']} @ {lead['company']}")

    # 1. Enrichment
    if not ledger.has_stage(lead_id, "enrichment"):
        website_data = await scrape_website(lead["website"], settings)
        linkedin_data = await enrich_linkedin(lead["linkedin_url"], settings, cost_tracker)
        ledger.save_stage(lead_id, "enrichment", {
            "website": website_data,
            "linkedin": linkedin_data,
        })

    enrichment = ledger.get_stage(lead_id, "enrichment")

    # 2. Fit analysis (Claude Haiku)
    if not ledger.has_stage(lead_id, "analysis"):
        analysis = await analyze_fit(lead, enrichment, settings, cost_tracker)
        ledger.save_stage(lead_id, "analysis", analysis)

    analysis = ledger.get_stage(lead_id, "analysis")
    if analysis.get("skip"):
        log.info(f"[{lead_id}] Skipping: {analysis.get('skip_reason')}")
        ledger.mark_complete(lead_id, status="skipped")
        return {"lead_id": lead_id, "status": "skipped"}

    # Save vertical, motion, intent_confidence to ledger
    ledger.save_lead_metadata(
        lead_id,
        email=lead.get("email", ""),
        vertical=analysis.get("vertical", ""),
        motion=analysis.get("motion", ""),
        intent_confidence=analysis.get("intent_confidence"),
        recommended_angle=analysis.get("recommended_angle", ""),
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

    # Save variant_id and test_id to ledger
    ledger.save_lead_metadata(
        lead_id,
        variant_id=variant_arm.get("id", ""),
        test_id=variant_arm.get("test_id", ""),
    )

    # 4. Email generation (Claude Sonnet, variant-aware)
    if not ledger.has_stage(lead_id, "email"):
        email = await generate_email(lead, analysis, variant_arm, settings, cost_tracker)
        ledger.save_stage(lead_id, "email", email)

    email = ledger.get_stage(lead_id, "email")

    # Save framework_used to ledger for analytics
    ledger.save_lead_metadata(
        lead_id,
        framework=email.get("framework_used", ""),
    )

    # 5. Script generation (Claude Sonnet, variant-aware)
    if not ledger.has_stage(lead_id, "script"):
        script = await build_script(lead, analysis, variant_arm, settings, cost_tracker)
        ledger.save_stage(lead_id, "script", script)

    script = ledger.get_stage(lead_id, "script")

    # 6. TTS
    audio_path = Path(f"data/videos/{lead_id}_audio.mp3")
    if not audio_path.exists():
        await synthesize(script["full_script"], audio_path, settings, cost_tracker)

    # 7. Scroll capture
    scroll_path = Path(f"data/videos/{lead_id}_scroll.mp4")
    if not scroll_path.exists():
        await record_scroll(
            url=lead["website"],
            duration_seconds=script["duration_seconds"],
            output_path=scroll_path,
            settings=settings,
        )

    # 8. Composite final video
    final_video_path = Path(f"data/videos/{lead_id}_final.mp4")
    if not final_video_path.exists():
        await composite_video(
            scroll_video=scroll_path,
            audio=audio_path,
            corner_image=Path("assets/corner_image.png"),
            output_path=final_video_path,
            settings=settings,
        )

    # 9. Upload + landing page
    if not ledger.has_stage(lead_id, "hosting"):
        video_url = await upload_video(final_video_path, lead_id, settings)
        landing_url = await generate_landing_page(lead, video_url, settings)
        ledger.save_stage(lead_id, "hosting", {
            "video_url": video_url,
            "landing_url": landing_url,
        })

    hosting = ledger.get_stage(lead_id, "hosting")
    email = ledger.get_stage(lead_id, "email")

    # 10. Push to the variant arm's Smartlead campaign (not the global default)
    # Build a settings copy with the variant's campaign_id so push_to_smartlead
    # uses the correct per-variant campaign without modifying the original settings.
    campaign_id = variant_arm.get("smartlead_campaign_id") or settings.smartlead_campaign_id
    push_settings = settings.model_copy(update={"smartlead_campaign_id": campaign_id})
    if not dry_run and not ledger.has_stage(lead_id, "smartlead"):
        result = await push_to_smartlead(
            lead=lead,
            email_subject=email["subject"],
            email_body=email["body"].replace("{VIDEO_LINK}", hosting["landing_url"]),
            settings=push_settings,
        )
        ledger.save_stage(lead_id, "smartlead", result)

    ledger.mark_complete(lead_id, status="sent" if not dry_run else "dry_run")
    log.info(f"[{lead_id}] Complete. Cost: ${cost_tracker.lead_cost(lead_id):.4f}")
    return {"lead_id": lead_id, "status": "sent", "landing_url": hosting["landing_url"]}


async def run_pipeline(
    csv_path: Path,
    single_lead_index: int | None,
    resume: bool,
    dry_run: bool,
    settings: Settings,
) -> None:
    ledger = Ledger("ledger.sqlite")
    cost_tracker = CostTracker(daily_budget_usd=settings.max_daily_budget_usd)

    leads = read_leads(csv_path)
    if single_lead_index is not None:
        leads = [leads[single_lead_index]]
    elif resume:
        leads = [l for l in leads if not ledger.is_complete(l["lead_id"])]

    log.info(f"Processing {len(leads)} leads")
    semaphore = asyncio.Semaphore(settings.max_concurrent_leads)

    async def bounded(lead):
        async with semaphore:
            try:
                return await process_lead(lead, settings, ledger, cost_tracker, dry_run)
            except Exception as e:
                log.error(f"[{lead['lead_id']}] FAILED: {e}", exc_info=True)
                ledger.mark_failed(lead["lead_id"], str(e))
                return {"lead_id": lead["lead_id"], "status": "failed", "error": str(e)}

    results = await asyncio.gather(*(bounded(lead) for lead in leads))

    # Summary
    sent = sum(1 for r in results if r["status"] == "sent")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    log.info(f"Done. Sent: {sent}, Skipped: {skipped}, Failed: {failed}")
    log.info(f"Total cost: ${cost_tracker.total():.2f}")
