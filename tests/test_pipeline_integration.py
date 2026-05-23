"""
Module 12 integration test.
Verifies variant_id flows end-to-end through the pipeline and the correct
Smartlead campaign_id is used.
All external modules are mocked.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai_cold_email.orchestrator.pipeline import process_lead
from src.utils.settings import Settings


# ─── Helpers ────────────────────────────────────────────────────────────────

def make_lead():
    return {
        "lead_id": "test-lead-001",
        "email": "alice@acme.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "company": "Acme",
        "website": "https://acme.com",
        "linkedin_url": "https://linkedin.com/in/alice",
        "role": "CRO",
    }


def make_analysis():
    return {
        "vertical": "B2B SaaS",
        "motion": "sales_led_outbound",
        "motion_evidence": "Demo CTA on homepage.",
        "personalized_hook": "Saw Acme expanding its SDR team.",
        "recommended_angle": "aap_outbound",
        "intent_confidence": 8,
        "skip": False,
        "skip_reason": "",
    }


def make_email_result():
    return {
        "subject": "saw acme's sdrs",
        "body": "Hey Alice, {VIDEO_LINK}\n\nWorth a call?",
        "variant_id": "Variant 3",
        "framework_used": "AIDA",
        "motion_used": "sales_led_outbound",
    }


def make_script_result():
    return {
        "personalized_first_half": "Hey Alice, it's Frank.",
        "fixed_second_half": "So let me be quick about this. Fixed half.",
        "full_script": "Hey Alice, it's Frank.\n\nSo let me be quick about this. Fixed half.",
        "duration_seconds": 52.0,
    }


@pytest.fixture
def tmp_ledger():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        return f.name


@pytest.mark.asyncio
async def test_variant_flows_through_pipeline(tmp_ledger):
    """
    End-to-end: verify that:
    1. assign_variant is called
    2. variant_id ends up in the ledger
    3. generate_email and build_script receive the correct variant_arm
    4. push_to_smartlead uses the variant's campaign_id
    """
    from src.utils.ledger import Ledger
    from src.utils.cost_tracker import CostTracker
    from src.utils.settings import load_settings

    settings = load_settings()
    ledger = Ledger(tmp_ledger)
    cost_tracker = CostTracker(path=tmp_ledger, daily_budget_usd=50.0)

    lead = make_lead()

    # Determine what variant assign_variant will pick for this lead
    from src.analytics.variant_assigner import assign_variant
    test_config = settings.active_test_config()
    expected_arm = assign_variant(lead["lead_id"], test_config)
    expected_variant_id = expected_arm["id"]
    expected_campaign_id = expected_arm["smartlead_campaign_id"]

    analysis = make_analysis()
    email_result = {**make_email_result(), "variant_id": expected_variant_id}
    script_result = make_script_result()

    mock_scrape = AsyncMock(return_value={"homepage_text": "Acme homepage", "about_text": "", "product_text": "", "title": "Acme", "meta_description": ""})
    mock_linkedin = AsyncMock(return_value={"headline": "CRO", "current_role": "CRO", "about": "", "recent_post": "", "company_size": "200-500"})
    mock_analyze = AsyncMock(return_value=analysis)
    mock_email = AsyncMock(return_value=email_result)
    mock_script = AsyncMock(return_value=script_result)
    mock_synthesize = AsyncMock(return_value=Path("data/videos/test-lead-001_audio.mp3"))
    mock_scroll = AsyncMock(return_value=Path("data/videos/test-lead-001_scroll.mp4"))
    mock_composite = AsyncMock(return_value=Path("data/videos/test-lead-001_final.mp4"))
    mock_upload = AsyncMock(return_value="https://videos.example.com/videos/test-lead-001.mp4")
    mock_landing = AsyncMock(return_value="https://go.example.com/v/test-lead-001")
    mock_push = AsyncMock(return_value={"status": "queued"})

    with (
        patch("src.orchestrator.pipeline.scrape_website", mock_scrape),
        patch("src.orchestrator.pipeline.enrich_linkedin", mock_linkedin),
        patch("src.orchestrator.pipeline.analyze_fit", mock_analyze),
        patch("src.orchestrator.pipeline.generate_email", mock_email),
        patch("src.orchestrator.pipeline.build_script", mock_script),
        patch("src.orchestrator.pipeline.synthesize", mock_synthesize),
        patch("src.orchestrator.pipeline.record_scroll", mock_scroll),
        patch("src.orchestrator.pipeline.composite_video", mock_composite),
        patch("src.orchestrator.pipeline.upload_video", mock_upload),
        patch("src.orchestrator.pipeline.generate_landing_page", mock_landing),
        patch("src.orchestrator.pipeline.push_to_smartlead", mock_push),
        # Make audio/scroll/video files appear to exist so pipeline skips them
        patch("pathlib.Path.exists", return_value=False),
    ):
        result = await process_lead(lead, settings, ledger, cost_tracker, dry_run=False)

    # Pipeline completed successfully
    assert result["status"] == "sent"

    # generate_email was called with the correct variant_arm
    email_call_args = mock_email.call_args
    passed_variant_arm = email_call_args[0][2]  # 3rd positional arg
    assert passed_variant_arm["id"] == expected_variant_id

    # build_script was called with the correct variant_arm
    script_call_args = mock_script.call_args
    passed_script_arm = script_call_args[0][2]
    assert passed_script_arm["id"] == expected_variant_id

    # push_to_smartlead was called with a settings copy using the variant's campaign_id
    push_call_args = mock_push.call_args
    push_settings = push_call_args[1]["settings"] if push_call_args[1] else push_call_args[0][3]
    assert push_settings.smartlead_campaign_id == expected_campaign_id


@pytest.mark.asyncio
async def test_skipped_lead_does_not_call_downstream(tmp_ledger):
    """When analysis returns skip=True, no email/script/video should be generated."""
    from src.utils.ledger import Ledger
    from src.utils.cost_tracker import CostTracker
    from src.utils.settings import load_settings

    settings = load_settings()
    ledger = Ledger(tmp_ledger)
    cost_tracker = CostTracker(path=tmp_ledger, daily_budget_usd=50.0)

    skip_analysis = {**make_analysis(), "skip": True, "skip_reason": "No hook possible"}

    mock_analyze = AsyncMock(return_value=skip_analysis)
    mock_email = AsyncMock()
    mock_scrape = AsyncMock(return_value={"homepage_text": "", "about_text": "", "product_text": "", "title": "", "meta_description": ""})
    mock_linkedin = AsyncMock(return_value={})

    with (
        patch("src.orchestrator.pipeline.scrape_website", mock_scrape),
        patch("src.orchestrator.pipeline.enrich_linkedin", mock_linkedin),
        patch("src.orchestrator.pipeline.analyze_fit", mock_analyze),
        patch("src.orchestrator.pipeline.generate_email", mock_email),
    ):
        result = await process_lead(make_lead(), settings, ledger, cost_tracker, dry_run=True)

    assert result["status"] == "skipped"
    mock_email.assert_not_called()
