"""
SMS generator. Calls Claude Sonnet with prompt caching to produce a
personalized SMS body for a lead.

Same two-block caching pattern as the email generator:
  Block 1 (cached)  — full sms.md instructions + variant templates
  Block 2 (fresh)   — per-lead data only (~100 tokens)

SMS constraint: body must be ≤ 320 characters (2 segments).
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from src.analytics.variant_assigner import apply_variant_overrides
from src.utils.template_store import get_template_override_block

log = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/sms/sms.md")
_MAX_CHARS = 320

# Sonnet 4.6 pricing
_INPUT_COST_PER_TOKEN       = 3.00 / 1_000_000
_OUTPUT_COST_PER_TOKEN      = 15.00 / 1_000_000
_CACHE_WRITE_COST_PER_TOKEN = 3.75 / 1_000_000
_CACHE_READ_COST_PER_TOKEN  = 0.30 / 1_000_000

_REQUIRED_KEYS = {"body", "variant_id", "framework_used", "motion_used", "char_count"}

_OPT_OUT_FOOTER = "\nReply STOP to opt out."


@lru_cache(maxsize=1)
def _load_static_instructions() -> str:
    """Read sms.md once, strip the ## Lead section for caching."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    lead_match = re.search(r"\n## Lead\n", template)
    if not lead_match:
        return template
    instructions_part = template[: lead_match.start()]
    rest = template[lead_match.end():]
    output_match = re.search(r"\n## Output", rest)
    if output_match:
        return instructions_part.rstrip() + "\n" + rest[output_match.start():].lstrip()
    return instructions_part


def _parse_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}") from e


def _validate(result: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - set(result.keys())
    if missing:
        raise ValueError(f"SMS response missing keys: {missing}")
    body = result.get("body", "")
    if "{VIDEO_LINK}" not in body:
        raise ValueError("SMS body does not contain {VIDEO_LINK} placeholder")
    # Check char count (without the opt-out footer which we add separately)
    if len(body) > _MAX_CHARS:
        raise ValueError(
            f"SMS body too long: {len(body)} chars (max {_MAX_CHARS}). Body: {body[:80]}..."
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(ValueError),
)
async def generate_sms(
    lead: dict[str, Any],
    analysis: dict[str, Any],
    variant_arm: dict[str, Any],
    settings: Any,
    cost_tracker: Any,
) -> dict[str, Any]:
    """Generate a personalized SMS body for a lead.

    Returns a dict with 'body' (containing {VIDEO_LINK} placeholder),
    variant_id, framework_used, motion_used, char_count.
    The caller substitutes the real video URL for {VIDEO_LINK}.
    """
    merged = apply_variant_overrides(analysis, variant_arm)
    static_instructions = _load_static_instructions()

    lead_data_block = (
        "## Lead\n\n"
        f"**Name:** {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
        f"**Role:** {lead.get('role', '')}\n"
        f"**Company:** {lead.get('company', '')}\n"
        f"**Vertical:** {merged.get('vertical', '')}\n"
        f"**Motion:** {merged.get('motion', '')}\n"
        f"**Personalized hook:** {merged.get('personalized_hook', '')}\n"
        f"**Recommended angle:** {merged.get('recommended_angle', '')}\n"
        f"**Variant:** {variant_arm.get('id', '')}"
    )

    # Inject Playbook template override if the user edited this variant
    override = get_template_override_block("sms", variant_arm.get("id", ""))
    if override:
        lead_data_block += override

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_generation_model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": static_instructions,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": lead_data_block,
                    },
                ],
            }
        ],
    )

    raw = response.content[0].text
    result = _parse_response(raw)
    _validate(result)

    # Log cost
    usage = response.usage
    input_cost  = usage.input_tokens * _INPUT_COST_PER_TOKEN
    output_cost = usage.output_tokens * _OUTPUT_COST_PER_TOKEN
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) * _CACHE_WRITE_COST_PER_TOKEN
    cache_read  = getattr(usage, "cache_read_input_tokens",       0) * _CACHE_READ_COST_PER_TOKEN
    cost_tracker.log(
        lead.get("lead_id"), "anthropic", "sms_generation",
        input_cost + output_cost + cache_write + cache_read,
    )

    return result
