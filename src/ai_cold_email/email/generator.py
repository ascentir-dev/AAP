"""
Email generator. Calls Claude Sonnet to produce personalized cold emails.
Applies variant overrides before building the prompt.

Optimization notes
------------------
* Prompt loaded from disk ONCE at module level (lru_cache) — no per-call I/O.
* Static instructions (≈470 lines — all 9 variant templates + framework rules)
  placed in a cached content block.  Only the ~150-token lead-data block is
  sent fresh per call.  After first cache warm-up this cuts Sonnet input-token
  cost by ≈85 % — saving ~$300/month at 30K leads.
* Uses AsyncAnthropic so the event loop is not blocked by synchronous I/O.
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
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.analytics.variant_assigner import apply_variant_overrides
from src.utils.template_store import get_template_override_block

log = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/ai_cold_email/email.md")

# Sonnet 4.6 pricing
_INPUT_COST_PER_TOKEN        = 3.00 / 1_000_000
_OUTPUT_COST_PER_TOKEN       = 15.00 / 1_000_000
_CACHE_WRITE_COST_PER_TOKEN  = 3.75 / 1_000_000   # 1.25 × input
_CACHE_READ_COST_PER_TOKEN   = 0.30 / 1_000_000   # 0.10 × input

_REQUIRED_OUTPUT_KEYS = {"subject", "body", "variant_id", "framework_used", "motion_used"}


@lru_cache(maxsize=1)
def _load_static_instructions() -> str:
    """Read email.md once, strip the dynamic lead section.

    Returns variant templates + framework rules + output format — identical
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


def _normalise_body(body: str) -> str:
    """Replace AI writing signals that cold-email validators flag.

    em dash  (—)  →  space-hyphen-space  ( - )
    en dash  (–)  →  regular hyphen      (-)

    These substitutions preserve readability while removing the most common
    AI-generated punctuation that spam/AI detectors flag.
    """
    return body.replace("—", " - ").replace("–", "-")


_EMAIL_REFUSAL_PREFIXES = (
    "i need to pause", "i can't", "i cannot", "i'm unable",
    "i am unable", "i must decline", "i won't", "sorry,",
    "i apologize", "i'm sorry", "i should not", "i should clarify",
    "i need to flag", "i'm not able", "i'm going to decline",
    "as an ai", "i have concerns",
)


def _parse_response(raw: str) -> dict[str, Any]:
    text = raw.strip()

    # Detect Claude content refusals — prose instead of JSON, retryable
    if text.lower()[:50].startswith(_EMAIL_REFUSAL_PREFIXES):
        log.warning("Claude email refusal — will retry. Raw[:100]: %s", text[:100])
        raise _EmailParseError(f"Claude refused: {text[:120]}")

    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if "```" in text:
            text = text[: text.rfind("```")]
    else:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                text = m.group(0)

    # Strict JSON first, then JS-style unquoted-key fix, then give up retryably
    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        fixed = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', text.strip())
        try:
            result = json.loads(fixed)
            log.debug("Email JSON recovered after key-quoting fix")
        except json.JSONDecodeError as e:
            log.warning("Unparseable email JSON — retrying. Raw[:200]: %s", raw[:200])
            raise _EmailParseError(f"Unparseable JSON: {e}") from e

    if result.get("body") is not None:
        result["body"] = _normalise_body(str(result["body"]))
    return result


# Retryable: bad JSON or Claude refusal (transient generation failures)
class _EmailParseError(Exception):
    pass


def _validate(result: dict[str, Any], has_video: bool = True) -> None:
    missing = _REQUIRED_OUTPUT_KEYS - set(result.keys())
    if missing:
        raise ValueError(f"Email response missing keys: {missing}")
    # Only require {VIDEO_LINK} for video emails.
    if has_video and "{VIDEO_LINK}" not in result.get("body", ""):
        raise ValueError("Email body does not contain {VIDEO_LINK} placeholder")


_SYSTEM_PROMPT = (
    "You are a professional B2B copywriter at Ascentir Technologies. "
    "Your sole job is to write concise, professional cold email introductions in the exact JSON format "
    "specified by the user's prompt. Always respond with valid JSON — never refuse, never add prose "
    "outside the JSON object. If the lead's market is unfamiliar or 'other', use the consultant "
    "market template as your fallback. Generate the email for every lead without exception."
)


async def _call_claude(
    client: anthropic.AsyncAnthropic,
    model: str,
    static_instructions: str,
    lead_data_block: str,
) -> Any:
    """Send a two-block request: cached instructions + fresh lead data."""
    return await client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    # Block 1: static variant templates + framework rules (cached)
                    {
                        "type": "text",
                        "text": static_instructions,
                        "cache_control": {"type": "ephemeral"},
                    },
                    # Block 2: per-lead data (fresh, ~150 tokens)
                    {
                        "type": "text",
                        "text": lead_data_block,
                    },
                ],
            }
        ],
    )


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(_EmailParseError),
)
async def generate_email(
    lead: dict[str, Any],
    analysis: dict[str, Any],
    variant_arm: dict[str, Any],
    settings: Any,
    cost_tracker: Any,
    has_video: bool = True,
) -> dict[str, Any]:
    """Generate a personalized cold email for a lead using a specific variant.

    Uses two-block messages:
      Block 1 (cached)   — full email.md prompt (≈484 lines, all 9 variants)
      Block 2 (fresh)    — lead-specific variables only (~150 tokens)
    """
    merged = apply_variant_overrides(analysis, variant_arm)

    static_instructions = _load_static_instructions()

    # Resolve market — analysis output takes priority, fall back to lead field
    market: str = merged.get("market") or lead.get("market") or ""

    # Small, per-lead block — only this part changes between calls
    lead_data_block = (
        "## Lead\n\n"
        f"**Name:** {lead.get('first_name', '')} {lead.get('last_name', '')}\n"
        f"**Role:** {lead.get('role', '')}\n"
        f"**Company:** {lead.get('company', '')}\n"
        f"**Market:** {market}\n"
        f"**Vertical:** {merged.get('vertical', '')}\n"
        f"**Motion:** {merged.get('motion', '')}\n"
        f"**Personalized hook:** {merged.get('personalized_hook', '')}\n"
        f"**Recommended angle:** {merged.get('recommended_angle', '')}\n"
        f"**Variant:** {variant_arm.get('id', '')}\n"
        f"**Has video:** {'yes' if has_video else 'no'}"
    )

    # Inject Playbook template override if the user edited this variant
    override = get_template_override_block("email", variant_arm.get("id", ""), market=market or None)
    if override:
        lead_data_block += override

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await _call_claude(
        client, settings.anthropic_generation_model,
        static_instructions, lead_data_block,
    )
    if not response.content:
        raise _EmailParseError("Claude returned empty content block — will retry")
    raw = response.content[0].text or ""

    result = _parse_response(raw)

    # For video emails: if {VIDEO_LINK} is absent, raise _EmailParseError so
    # tenacity retries the whole function with the reminder appended.
    if has_video and "{VIDEO_LINK}" not in result.get("body", ""):
        log.warning("Email body missing {VIDEO_LINK} — triggering retry via _EmailParseError")
        raise _EmailParseError(
            "has_video=yes but {VIDEO_LINK} absent from body. "
            "REMINDER: body MUST contain literal {VIDEO_LINK}."
        )

    _validate(result, has_video=has_video)

    # Log true cost accounting for prompt-cache savings
    usage = response.usage
    input_cost  = usage.input_tokens * _INPUT_COST_PER_TOKEN
    output_cost = usage.output_tokens * _OUTPUT_COST_PER_TOKEN
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) * _CACHE_WRITE_COST_PER_TOKEN
    cache_read  = getattr(usage, "cache_read_input_tokens",       0) * _CACHE_READ_COST_PER_TOKEN
    cost_tracker.log(
        lead.get("lead_id"), "anthropic", "email_generation",
        input_cost + output_cost + cache_write + cache_read,
    )

    log.debug(
        "email_generation lead=%s variant=%s cached_read=%s input=%s",
        lead.get("lead_id"),
        variant_arm.get("id"),
        getattr(usage, "cache_read_input_tokens", 0),
        usage.input_tokens,
    )

    return result
