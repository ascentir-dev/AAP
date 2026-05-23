"""Tests for src/analysis/fit_analyzer.py — Anthropic async client mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analysis.fit_analyzer import analyze_fit, _load_static_instructions


VALID_RESPONSE = {
    "vertical": "B2B SaaS",
    "motion": "sales_led_outbound",
    "motion_evidence": "Homepage shows 'Book a Demo' CTA, no self-serve pricing.",
    "personalized_hook": "Saw your post on expanding SDR team for Q3.",
    "recommended_angle": "aap_outbound",
    "intent_confidence": 8,
    "skip": False,
    "skip_reason": "",
}


def make_settings():
    s = MagicMock()
    s.anthropic_api_key = "fake-key"
    s.anthropic_analysis_model = "claude-haiku-4-5-20251001"
    return s


def make_cost_tracker():
    ct = MagicMock()
    ct.log = MagicMock()
    return ct


def make_usage(input_tokens=1000, output_tokens=200, cache_read=500, cache_write=0):
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


def make_lead():
    return {
        "lead_id": "abc123",
        "first_name": "Alice",
        "last_name": "Smith",
        "role": "CRO",
        "company": "Acme",
        "website": "https://acme.com",
    }


def make_enrichment():
    return {
        "website": {
            "homepage_text": "We help companies close more deals.",
            "about_text": "",
            "product_text": "",
        },
        "linkedin": {
            "headline": "CRO at Acme",
            "current_role": "CRO",
            "about": "",
            "recent_post": "",
            "company_size": "200-500",
        },
    }


def _make_async_client(response):
    """Build a mock AsyncAnthropic client whose messages.create is awaitable."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=response)
    return mock_client


@pytest.mark.asyncio
async def test_successful_parse():
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_RESPONSE)))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await analyze_fit(make_lead(), make_enrichment(), make_settings(), make_cost_tracker())

    assert result["vertical"] == "B2B SaaS"
    assert result["motion"] == "sales_led_outbound"
    assert result["intent_confidence"] == 8
    assert result["skip"] is False


@pytest.mark.asyncio
async def test_cost_is_logged():
    ct = make_cost_tracker()
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_RESPONSE)))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        await analyze_fit(make_lead(), make_enrichment(), make_settings(), ct)

    ct.log.assert_called_once()
    call_args = ct.log.call_args[0]
    assert call_args[1] == "anthropic"
    assert call_args[3] > 0


@pytest.mark.asyncio
async def test_cache_read_tokens_reduce_cost():
    """Cache-read tokens are billed at 10% of input price — cost should be lower."""
    ct_no_cache   = make_cost_tracker()
    ct_with_cache = make_cost_tracker()

    # No cache: 1000 regular input tokens
    no_cache_resp   = make_anthropic_response(json.dumps(VALID_RESPONSE), input_tokens=1000, cache_read=0)
    # With cache: 200 regular + 800 cache-read tokens (much cheaper)
    with_cache_resp = make_anthropic_response(json.dumps(VALID_RESPONSE), input_tokens=200, cache_read=800)

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic") as MockCls:
        MockCls.return_value.messages.create = AsyncMock(return_value=no_cache_resp)
        await analyze_fit(make_lead(), make_enrichment(), make_settings(), ct_no_cache)

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic") as MockCls:
        MockCls.return_value.messages.create = AsyncMock(return_value=with_cache_resp)
        await analyze_fit(make_lead(), make_enrichment(), make_settings(), ct_with_cache)

    cost_no_cache   = ct_no_cache.log.call_args[0][3]
    cost_with_cache = ct_with_cache.log.call_args[0][3]
    assert cost_with_cache < cost_no_cache


@pytest.mark.asyncio
async def test_invalid_motion_raises():
    bad_response = {**VALID_RESPONSE, "motion": "invalid_motion"}
    mock_client = _make_async_client(make_anthropic_response(json.dumps(bad_response)))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(ValueError, match="Invalid motion"):
            await analyze_fit(make_lead(), make_enrichment(), make_settings(), make_cost_tracker())


@pytest.mark.asyncio
async def test_missing_keys_raises():
    incomplete = {"vertical": "B2B SaaS", "motion": "sales_led_outbound"}
    mock_client = _make_async_client(make_anthropic_response(json.dumps(incomplete)))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(ValueError, match="missing keys"):
            await analyze_fit(make_lead(), make_enrichment(), make_settings(), make_cost_tracker())


@pytest.mark.asyncio
async def test_strips_markdown_fences():
    fenced = f"```json\n{json.dumps(VALID_RESPONSE)}\n```"
    mock_client = _make_async_client(make_anthropic_response(fenced))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await analyze_fit(make_lead(), make_enrichment(), make_settings(), make_cost_tracker())

    assert result["vertical"] == "B2B SaaS"


@pytest.mark.asyncio
async def test_messages_use_two_content_blocks():
    """The API call should use two content blocks: cached instructions + fresh lead data."""
    mock_client = _make_async_client(make_anthropic_response(json.dumps(VALID_RESPONSE)))

    with patch("src.analysis.fit_analyzer.anthropic.AsyncAnthropic", return_value=mock_client):
        await analyze_fit(make_lead(), make_enrichment(), make_settings(), make_cost_tracker())

    call_kwargs = mock_client.messages.create.call_args
    messages = call_kwargs[1].get("messages") or call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]["messages"]
    # Normalise — create() is called with keyword args
    kwargs = call_kwargs.kwargs if hasattr(call_kwargs, "kwargs") else call_kwargs[1]
    user_message = kwargs["messages"][0]
    content_blocks = user_message["content"]
    assert len(content_blocks) == 2, "Expected two content blocks (cached + fresh)"
    assert content_blocks[0].get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in content_blocks[1]


def test_static_instructions_excludes_lead_data_section():
    """The cached instructions should not contain the raw {first_name} placeholder."""
    instructions = _load_static_instructions()
    # Should contain the analysis instructions
    assert "sales motion" in instructions.lower() or "motion" in instructions
    # Should NOT contain the lead-data placeholder template lines
    assert "{first_name}" not in instructions
    assert "{website_summary}" not in instructions
