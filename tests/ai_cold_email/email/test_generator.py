"""Tests for src/email/generator.py — Anthropic async client mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai_cold_email.email.generator import generate_email, _load_static_instructions


VALID_EMAIL_RESPONSE = {
    "subject": "saw acme's hiring push",
    "body": "Hey Alice,\n\nI saw Acme is growing. {VIDEO_LINK}\n\nWorth a call?\n\nFrank",
    "variant_id": "Variant 1",
    "framework_used": "PPP",
    "motion_used": "sales_led_outbound",
}


def make_settings():
    s = MagicMock()
    s.anthropic_api_key = "fake-key"
    s.anthropic_generation_model = "claude-sonnet-4-6"
    return s


def make_cost_tracker():
    ct = MagicMock()
    ct.log = MagicMock()
    return ct


def make_lead():
    return {
        "lead_id": "abc123",
        "first_name": "Alice",
        "last_name": "Smith",
        "role": "CRO",
        "company": "Acme",
    }


def make_analysis():
    return {
        "vertical": "B2B SaaS",
        "motion": "sales_led_outbound",
        "personalized_hook": "Saw your new SDR hiring push on LinkedIn.",
        "recommended_angle": "aap_outbound",
        "intent_confidence": 8,
        "skip": False,
        "skip_reason": "",
    }


def make_variant_arm():
    return {
        "id": "Variant 1",
        "weight": 0.111,
        "smartlead_campaign_id": "camp-001",
        "overrides": {
            "email_template_id": "v1_ppp",
            "variant_framework": "PPP",
        },
    }


def make_usage(input_tokens=800, output_tokens=150, cache_read=600, cache_write=0):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write
    return usage


def make_anthropic_response(content: str, **usage_kwargs):
    content_block = MagicMock()
    content_block.text = content
    response = MagicMock()
    response.content = [content_block]
    response.usage = make_usage(**usage_kwargs)
    return response


def _make_async_client(response_or_side_effect):
    """Build a mock AsyncAnthropic client with an async-compatible messages.create."""
    mock_client = MagicMock()
    if isinstance(response_or_side_effect, list):
        mock_client.messages.create = AsyncMock(side_effect=response_or_side_effect)
    else:
        mock_client.messages.create = AsyncMock(return_value=response_or_side_effect)
    return mock_client


@pytest.mark.asyncio
async def test_successful_generation():
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_email(
            make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker()
        )

    assert result["subject"] == "saw acme's hiring push"
    assert len(result["subject"]) < 50
    assert "{VIDEO_LINK}" in result["body"]
    assert result["variant_id"] == "Variant 1"
    assert result["framework_used"] == "PPP"


@pytest.mark.asyncio
async def test_subject_is_under_50_chars():
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_email(
            make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker()
        )

    assert len(result["subject"]) < 50


@pytest.mark.asyncio
async def test_body_contains_video_link():
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_email(
            make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker()
        )

    assert "{VIDEO_LINK}" in result["body"]


@pytest.mark.asyncio
async def test_variant_id_matches_arm():
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_email(
            make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker()
        )

    assert result["variant_id"] == make_variant_arm()["id"]


@pytest.mark.asyncio
async def test_cost_is_logged():
    ct = make_cost_tracker()
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        await generate_email(make_lead(), make_analysis(), make_variant_arm(), make_settings(), ct)

    ct.log.assert_called_once()
    call_args = ct.log.call_args[0]
    assert call_args[1] == "anthropic"
    assert call_args[3] > 0


@pytest.mark.asyncio
async def test_missing_video_link_retries():
    """When first response lacks {VIDEO_LINK}, generator retries once."""
    no_link = {**VALID_EMAIL_RESPONSE, "body": "Hey Alice, check this out!\n\nFrank"}
    mock_client = _make_async_client([
        make_anthropic_response(json.dumps(no_link)),
        make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)),
    ])

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await generate_email(
            make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker()
        )

    assert "{VIDEO_LINK}" in result["body"]
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_messages_use_two_content_blocks():
    """The API call should use two content blocks: cached instructions + fresh lead data."""
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_EMAIL_RESPONSE)))

    with patch("src.email.generator.anthropic.AsyncAnthropic", return_value=mock_client):
        await generate_email(make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker())

    kwargs = mock_client.messages.create.call_args.kwargs
    user_message = kwargs["messages"][0]
    content_blocks = user_message["content"]
    assert len(content_blocks) == 2
    assert content_blocks[0].get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in content_blocks[1]


def test_static_instructions_excludes_lead_section():
    """The cached instructions block should not contain the Lead data section header.

    Note: {first_name} can appear in variant template examples inside the instructions —
    that's expected.  What we verify is that the ## Lead section (the dynamic per-lead
    block with **Name:** etc.) was stripped from the static cache block.
    """
    instructions = _load_static_instructions()
    # Should contain framework definitions
    assert "VARIANT" in instructions or "variant" in instructions.lower()
    # The specific Lead section header + first field should NOT be present
    assert "## Lead\n\n**Name:**" not in instructions
    assert "**Variant:** {variant_id}" not in instructions
