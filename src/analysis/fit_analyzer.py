"""
Fit analyzer. Calls Claude Haiku with prompt caching to classify each lead
and generate a personalized hook.

Optimization notes
------------------
* Prompt loaded from disk ONCE at module level (lru_cache) — no per-call I/O.
* Static instructions (≈150 lines) placed in a cached content block; only the
  ~200-token lead-data block is sent fresh per call.  After the first cache
  warm-up this cuts Haiku input-token cost by ≈85 %.
* Uses AsyncAnthropic so the event loop stays free while concurrent leads run.
* Cost log accounts for cache-write, cache-read, and regular input tokens.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/ai_cold_email/analysis.md")
_VALID_MOTIONS  = {"plg_self_serve", "hybrid_sales_assisted", "sales_led_outbound"}
_VALID_MARKETS  = {"coach", "agency", "consultant", "financial_advisor", "msp", "other"}

# Haiku 4.5 pricing (per-token)
_INPUT_COST_PER_TOKEN        = 0.80 / 1_000_000
_OUTPUT_COST_PER_TOKEN       = 4.00 / 1_000_000
_CACHE_WRITE_COST_PER_TOKEN  = 1.00 / 1_000_000   # 1.25 × input
_CACHE_READ_COST_PER_TOKEN   = 0.08 / 1_000_000   # 0.10 × input


@lru_cache(maxsize=1)
def _load_static_instructions() -> str:
    """Read analysis.md once, strip the dynamic lead-data section.

    Returns the instructions part + output-format section — this is identical
    across every lead and will be served from Anthropic's prompt cache.
    """
    template = _PROMPT_PATH.read_text(encoding="utf-8")

    # Split at the ## Lead Data section (dynamic, per-lead)
    lead_match = re.search(r"\n## Lead(?: Data)?\n", template)
    if not lead_match:
        return template  # fallback: return as-is

    instructions_part = template[: lead_match.start()]
    rest = template[lead_match.end():]

    # Re-attach the output-format / output-rules sections that follow lead data
    output_match = re.search(r"\n## Output", rest)
    if output_match:
        output_part = rest[output_match.start():]
        return instructions_part.rstrip() + "\n" + output_part.lstrip()

    return instructions_part


def _format_website_summary(enrichment: dict[str, Any]) -> str:
    website = enrichment.get("website", {})
    parts = [
        website.get("homepage_text", ""),
        website.get("about_text", ""),
        website.get("product_text", ""),
    ]
    return "\n\n".join(p for p in parts if p).strip()


def _format_linkedin(linkedin: dict[str, Any]) -> str:
    if not linkedin:
        return "No LinkedIn data available."
    lines = []
    for key, label in [
        ("headline", "Headline"),
        ("current_role", "Role"),
        ("about", "About"),
        ("recent_post", "Recent Post"),
        ("company_size", "Company Size"),
    ]:
        val = linkedin.get(key, "")
        if val:
            lines.append(f"{label}: {val}")
    return "\n".join(lines) or "No LinkedIn data available."


# Sentinel for retryable generation failures (bad JSON, Claude refusal).
# Distinct from ValueError so the retry decorator can target it specifically.
class _AnalysisParseError(Exception):
    pass


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(_AnalysisParseError),
)
async def analyze_fit(
    lead: dict[str, Any],
    enrichment: dict[str, Any],
    settings: Any,
    cost_tracker: Any,
) -> dict[str, Any]:
    """Classify lead and generate personalized hook via Claude Haiku.

    Uses two-block messages:
      Block 1 (cached)   — full analysis instructions + output format
      Block 2 (fresh)    — lead-specific data only (~200 tokens)
    """
    static_instructions = _load_static_instructions()

    enrichment = enrichment or {}
    website_summary = _format_website_summary(enrichment)
    linkedin_data = _format_linkedin(enrichment.get("linkedin", {}))

    # Pre-detected market hint from CSV ingestion (Claude confirms or corrects it)
    pre_market  = lead.get("market", "")
    market_hint = (
        f"\n**Pre-detected market (confirm or correct):** {pre_market}"
        if pre_market else ""
    )

    # Small, per-lead block — only this changes between calls
    lead_data_block = (
        "## Lead Data\n\n"
        f"**Name:** {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
        f"**Role:** {lead.get('role', '')}\n"
        f"**Company:** {lead.get('company', '')}\n"
        f"**Website:** {lead.get('website', '')}"
        f"{market_hint}\n\n"
        f"**Website summary:**\n{website_summary}\n\n"
        f"**LinkedIn data:**\n{linkedin_data}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_analysis_model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    # Block 1: static — served from cache after first call
                    {
                        "type": "text",
                        "text": static_instructions,
                        "cache_control": {"type": "ephemeral"},
                    },
                    # Block 2: dynamic — fresh every call, small
                    {
                        "type": "text",
                        "text": lead_data_block,
                    },
                ],
            }
        ],
    )

    if not response.content:
        raise _AnalysisParseError("Claude returned empty content block — will retry")
    raw = (response.content[0].text or "").strip()

    # Detect Claude content refusals — model says prose instead of JSON.
    # These are transient; retry with the same prompt (model re-samples).
    _REFUSAL_PREFIXES = (
        "i need to pause", "i can't", "i cannot", "i'm unable",
        "i am unable", "i must decline", "i won't", "sorry,",
    )
    if raw.lower()[:50].startswith(_REFUSAL_PREFIXES):
        log.warning("Claude analysis refusal detected — retrying. Raw[:100]: %s", raw[:100])
        raise _AnalysisParseError(f"Claude refused to generate analysis: {raw[:120]}")

    # Strip markdown code fences if the model wraps them
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    # Try strict JSON first, then fall back to a lenient fix for unquoted keys
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Claude sometimes emits JS-style {key: value} without quoting keys.
        # Fix with a targeted regex before giving up.
        fixed = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', raw)
        try:
            result = json.loads(fixed)
            log.debug("JSON parse recovered after key-quoting fix for this lead")
        except json.JSONDecodeError as e:
            # Genuinely unparseable — raise retryable error so tenacity tries again
            log.warning("Claude returned unparseable JSON — retrying. Raw[:200]: %s", raw[:200])
            raise _AnalysisParseError(f"Unparseable JSON after fix attempt: {e}") from e

    # Validate required keys — this is a structural problem, not retryable
    required = {
        "market", "vertical", "motion", "motion_evidence", "personalized_hook",
        "recommended_angle", "intent_confidence", "skip", "skip_reason",
    }
    missing = required - set(result.keys())
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")

    # Validate motion value
    if result["motion"] not in _VALID_MOTIONS:
        raise ValueError(
            f"Invalid motion '{result['motion']}'. Must be one of {_VALID_MOTIONS}"
        )

    # Validate market value — normalise unknown values to 'other' rather than crashing
    if result.get("market") not in _VALID_MARKETS:
        log.warning(
            "Unexpected market '%s' for lead=%s — defaulting to 'other'",
            result.get("market"), lead.get("lead_id"),
        )
        result["market"] = "other"

    # Log true cost accounting for prompt-cache savings
    usage = response.usage
    input_cost = usage.input_tokens * _INPUT_COST_PER_TOKEN
    output_cost = usage.output_tokens * _OUTPUT_COST_PER_TOKEN
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) * _CACHE_WRITE_COST_PER_TOKEN
    cache_read  = getattr(usage, "cache_read_input_tokens",       0) * _CACHE_READ_COST_PER_TOKEN
    cost_tracker.log(
        lead.get("lead_id"), "anthropic", "fit_analysis",
        input_cost + output_cost + cache_write + cache_read,
    )

    log.debug(
        "fit_analysis lead=%s cached_read=%s cached_write=%s input=%s",
        lead.get("lead_id"),
        getattr(usage, "cache_read_input_tokens", 0),
        getattr(usage, "cache_creation_input_tokens", 0),
        usage.input_tokens,
    )

    return result
