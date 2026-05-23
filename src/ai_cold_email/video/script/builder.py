"""
Script builder. Generates the personalized first half of the video script,
then appends the motion-appropriate fixed second half from settings.

Optimization notes
------------------
* Prompt loaded from disk ONCE at module level (lru_cache) — no per-call I/O.
* Static instructions (≈70 lines — 4-beat structure + voice rules + output format)
  placed in a cached content block; only the ~100-token lead-data block is
  sent fresh per call.
* Uses AsyncAnthropic so the event loop stays free during concurrent lead runs.
* Full cache-aware cost accounting (write, read, and regular input tokens).
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

log = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/ai_cold_email/script.md")

# Sonnet 4.6 pricing
_INPUT_COST_PER_TOKEN        = 3.00 / 1_000_000
_OUTPUT_COST_PER_TOKEN       = 15.00 / 1_000_000
_CACHE_WRITE_COST_PER_TOKEN  = 3.75 / 1_000_000
_CACHE_READ_COST_PER_TOKEN   = 0.30 / 1_000_000


@lru_cache(maxsize=1)
def _load_static_instructions() -> str:
    """Read script.md once, strip the dynamic lead section.

    Returns the 4-beat structure + voice rules + output format — identical
    across every lead and will be served from Anthropic's prompt cache.
    """
    template = _PROMPT_PATH.read_text(encoding="utf-8")

    # Split at "## Lead" — the dynamic per-lead variables section
    lead_match = re.search(r"\n## Lead\n", template)
    if not lead_match:
        return template  # fallback

    instructions_part = template[: lead_match.start()]
    rest = template[lead_match.end():]

    # Re-attach the output-format / output-rules sections that follow
    output_match = re.search(r"\n## Output", rest)
    if output_match:
        output_part = rest[output_match.start():]
        return instructions_part.rstrip() + "\n" + output_part.lstrip()

    return instructions_part


def _word_count(text: str) -> int:
    return len(text.split())


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(ValueError),
)
async def build_script(
    lead: dict[str, Any],
    analysis: dict[str, Any],
    variant_arm: dict[str, Any],
    settings: Any,
    cost_tracker: Any,
) -> dict[str, Any]:
    """Generate script first half, append fixed second half, calculate duration.

    Uses two-block messages:
      Block 1 (cached)   — full script.md instructions + output format
      Block 2 (fresh)    — lead-specific variables only (~100 tokens)
    """
    merged = apply_variant_overrides(analysis, variant_arm)

    static_instructions = _load_static_instructions()

    # Small, per-lead block — only this part changes between calls
    lead_data_block = (
        "## Lead\n\n"
        f"**Name:** {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
        f"**Role:** {lead.get('role', '')}\n"
        f"**Company:** {lead.get('company', '')}\n"
        f"**Vertical:** {merged.get('vertical', '')}\n"
        f"**Motion:** {merged.get('motion', '')}\n"
        f"**Personalized hook:** {merged.get('personalized_hook', '')}\n"
        f"**Recommended angle:** {merged.get('recommended_angle', '')}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_generation_model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    # Block 1: static instructions (cached after first call)
                    {
                        "type": "text",
                        "text": static_instructions,
                        "cache_control": {"type": "ephemeral"},
                    },
                    # Block 2: per-lead data (fresh, ~100 tokens)
                    {
                        "type": "text",
                        "text": lead_data_block,
                    },
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:200]}") from e

    if "personalized_first_half" not in result:
        raise ValueError("Script response missing 'personalized_first_half' key")

    personalized_first_half = result["personalized_first_half"]

    # Get the motion-correct fixed second half from settings
    motion = analysis.get("motion", "sales_led_outbound")
    fixed_second_half = settings.fixed_second_half_for_motion(motion)

    full_script = personalized_first_half + "\n\n" + fixed_second_half

    # Duration estimate: word count / speaking rate × 60
    speaking_rate = settings.script.get("speaking_rate_words_per_minute", 165)
    duration_seconds = _word_count(full_script) / speaking_rate * 60

    # Log true cost accounting for prompt-cache savings
    usage = response.usage
    input_cost  = usage.input_tokens * _INPUT_COST_PER_TOKEN
    output_cost = usage.output_tokens * _OUTPUT_COST_PER_TOKEN
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) * _CACHE_WRITE_COST_PER_TOKEN
    cache_read  = getattr(usage, "cache_read_input_tokens",       0) * _CACHE_READ_COST_PER_TOKEN
    cost_tracker.log(
        lead.get("lead_id"), "anthropic", "script_generation",
        input_cost + output_cost + cache_write + cache_read,
    )

    log.debug(
        "script_generation lead=%s cached_read=%s input=%s",
        lead.get("lead_id"),
        getattr(usage, "cache_read_input_tokens", 0),
        usage.input_tokens,
    )

    return {
        "personalized_first_half": personalized_first_half,
        "fixed_second_half": fixed_second_half,
        "full_script": full_script,
        "duration_seconds": round(duration_seconds, 1),
    }
