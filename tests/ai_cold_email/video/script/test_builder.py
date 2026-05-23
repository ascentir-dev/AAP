"""Tests for src/video/script/builder.py — Anthropic async client mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai_cold_email.video.script.builder import build_script, _load_static_instructions


FIRST_HALF = (
    "Hey Alice, it's Frank here. I pulled your site up just to show I'm not a robot — "
    "scrolling through it as we speak. I saw Acme's been hiring SDRs pretty aggressively. "
    "Honestly, for a sales-led company in your space, that usually signals a cost-per-meeting "
    "problem brewing — which is exactly why I'm reaching out."
)

FIRST_HALF_RESPONSE = {"personalized_first_half": FIRST_HALF}


def make_settings(motion_second_half: str = "So let me be quick about this. We help mid-market companies..."):
    s = MagicMock()
    s.anthropic_api_key = "fake-key"
    s.anthropic_generation_model = "claude-sonnet-4-6"
    s.script = {"speaking_rate_words_per_minute": 165}
    s.fixed_second_half_for_motion = MagicMock(return_value=motion_second_half)
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


def make_analysis(motion: str = "sales_led_outbound"):
    return {
        "vertical": "B2B SaaS",
        "motion": motion,
        "personalized_hook": "Saw Acme's aggressive SDR hiring.",
        "recommended_angle": "aap_outbound",
        "intent_confidence": 8,
    }


def make_variant_arm():
    return {
        "id": "Variant 1",
        "weight": 0.111,
        "smartlead_campaign_id": "camp-001",
        "overrides": {},
    }


def make_usage(input_tokens=600, output_tokens=100, cache_read=400, cache_write=0):
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


def _make_async_client(response):
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=response)
    return mock_client


@pytest.mark.asyncio
async def test_returns_all_required_keys():
    mock_client = _make_async_client(
        make_anthropic_response(json.dumps(FIRST_HALF_RESPONSE))
    )
    settings = make_settings("So let me be quick. Fixed second half here.")

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await build_script(make_lead(), make_analysis(), make_variant_arm(), settings, make_cost_tracker())

    assert "personalized_first_half" in result
    assert "fixed_second_half" in result
    assert "full_script" in result
    assert "duration_seconds" in result


@pytest.mark.asyncio
async def test_full_script_is_concatenation():
    second_half = "So let me be quick. Here is the fixed second half."
    mock_client = _make_async_client(
        make_anthropic_response(json.dumps(FIRST_HALF_RESPONSE))
    )
    settings = make_settings(second_half)

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await build_script(make_lead(), make_analysis(), make_variant_arm(), settings, make_cost_tracker())

    assert result["full_script"] == FIRST_HALF + "\n\n" + second_half


@pytest.mark.asyncio
async def test_motion_correct_second_half_chosen():
    settings = make_settings()
    mock_client = _make_async_client(
        make_anthropic_response(json.dumps(FIRST_HALF_RESPONSE))
    )

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        await build_script(
            make_lead(), make_analysis(motion="plg_self_serve"),
            make_variant_arm(), settings, make_cost_tracker()
        )

    settings.fixed_second_half_for_motion.assert_called_once_with("plg_self_serve")


@pytest.mark.asyncio
async def test_duration_calculation():
    first = "word " * 50   # 50 words
    second = "word " * 50  # 50 words → total 100 words
    settings = make_settings(second.strip())

    mock_client = _make_async_client(
        make_anthropic_response(json.dumps({"personalized_first_half": first.strip()}))
    )

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await build_script(make_lead(), make_analysis(), make_variant_arm(), settings, make_cost_tracker())

    # 100 words / 165 wpm × 60 ≈ 36.4 seconds
    assert 35 < result["duration_seconds"] < 38


@pytest.mark.asyncio
async def test_cost_is_logged():
    ct = make_cost_tracker()
    mock_client = _make_async_client(
        make_anthropic_response(json.dumps(FIRST_HALF_RESPONSE))
    )

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        await build_script(make_lead(), make_analysis(), make_variant_arm(), make_settings(), ct)

    ct.log.assert_called_once()
    assert ct.log.call_args[0][1] == "anthropic"
    assert ct.log.call_args[0][3] > 0


@pytest.mark.asyncio
async def test_messages_use_two_content_blocks():
    """API call must use two content blocks: cached instructions + fresh lead data."""
    mock_client = _make_async_client(
        make_anthropic_response(json.dumps(FIRST_HALF_RESPONSE))
    )

    with patch("src.video.script.builder.anthropic.AsyncAnthropic", return_value=mock_client):
        await build_script(make_lead(), make_analysis(), make_variant_arm(), make_settings(), make_cost_tracker())

    kwargs = mock_client.messages.create.call_args.kwargs
    user_message = kwargs["messages"][0]
    content_blocks = user_message["content"]
    assert len(content_blocks) == 2
    assert content_blocks[0].get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in content_blocks[1]


def test_static_instructions_excludes_lead_section():
    """The cached instructions should not contain the Lead data section.

    Note: {first_name} can appear in beat examples inside the instructions
    (e.g. "Hey {first_name}, it's Frank here.") — that's expected static content.
    What we verify is that the ## Lead section (dynamic per-lead block) was stripped.
    """
    instructions = _load_static_instructions()
    assert "beat" in instructions.lower() or "script" in instructions.lower()
    # The Lead section header + first field should NOT be present
    assert "## Lead\n\n**Name:**" not in instructions
    assert "**Recommended angle:** {recommended_angle}" not in instructions
