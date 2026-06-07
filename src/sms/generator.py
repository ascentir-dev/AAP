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
# Body-only limit (pipeline.py appends a ~22-char opt-out footer before sending).
# 2 concatenated SMS segments = 306 chars total; subtract 22 footer + 4 buffer = 280.
_MAX_CHARS = 280

_SIGN_OFF_RE = re.compile(r"\.?\s*Frank\s*$")


class SmsJsonError(Exception):
    """Claude returned prose instead of JSON — safe to retry."""


class SmsLengthError(Exception):
    """Body exceeds character limit after trimming — safe to retry with tighter prompt."""

# Sonnet 4.6 pricing
_INPUT_COST_PER_TOKEN       = 3.00 / 1_000_000
_OUTPUT_COST_PER_TOKEN      = 15.00 / 1_000_000
_CACHE_WRITE_COST_PER_TOKEN = 3.75 / 1_000_000
_CACHE_READ_COST_PER_TOKEN  = 0.30 / 1_000_000

_REQUIRED_KEYS = {"body", "variant_id", "framework_used", "motion_used", "char_count"}

_OPT_OUT_FOOTER = "\nReply STOP to opt out."


def _bust_prompt_cache() -> None:
    """Call after editing sms.md to force the lru_cache to reload."""
    _load_static_instructions.cache_clear()


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

    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]).strip()
        if "```" in text:
            text = text[: text.rfind("```")].strip()

    # 2. Strip any prose preamble — find the first '{' and last '}'
    #    Handles "Here is your SMS:\n{...}" or "Here's the JSON: {...}"
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    elif start != -1:
        text = text[start:]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Raise SmsJsonError (NOT ValueError) so the retry decorator will retry
        raise SmsJsonError(
            f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}"
        ) from e


def _trim_to_limit(body: str, max_chars: int = 275) -> str:
    """Trim body to at most max_chars at a natural sentence boundary.

    Detaches the trailing 'Frank' sign-off first, trims the content, then
    reattaches it — so the sign-off is never cut.
    """
    if len(body) <= max_chars:
        return body

    # Detach the trailing 'Frank' sign-off (". Frank" or " Frank")
    m = _SIGN_OFF_RE.search(body)
    sign_off = m.group(0) if m else ""
    content  = body[: m.start()] if m else body

    # Budget available for the content block
    budget = max_chars - len(sign_off)

    if len(content) <= budget:
        return body  # already fits once we know the sign-off size

    # 1. Last sentence boundary (., !, ?) within budget
    for sep in (".", "!", "?"):
        idx = content.rfind(sep, 0, budget)
        if idx >= max(budget // 2, 40):
            trimmed = content[: idx + 1].strip()
            # Avoid double-punct: ". Frank" appended after content ending in "." → ".. Frank"
            clean_sign = sign_off.lstrip(".")   # ". Frank" → " Frank" when punct already present
            return trimmed + clean_sign

    # 2. Last comma within budget
    idx = content.rfind(",", 0, budget)
    if idx >= max(budget // 2, 40):
        return content[:idx].rstrip().strip() + "." + sign_off

    # 3. Last word boundary within budget
    idx = content.rfind(" ", 0, budget)
    if idx > 0:
        return content[:idx].rstrip(" ,").strip() + "." + sign_off

    # 4. Hard cut (shouldn't reach here in practice)
    return content[:budget].rstrip().strip() + sign_off


def _humanize_body(body: str, first_name: str) -> str:
    """Post-process the SMS body to strip AI-sounding patterns.

    1. Em-dash / en-dash mid-sentence  → ", " (e.g. "120 calls — or refund" → "120 calls, or refund")
    2. Spaced hyphen clause separator  → ". " with next word capitalised
       (e.g. "scaling - wanted" → "scaling. Wanted")
    3. Ensure the first name is followed by a comma.
    """
    # Em-dash / en-dash → comma-space, absorbing any surrounding whitespace
    # e.g. "Laura — Inpowered"  → "Laura, Inpowered"
    #      "120 calls — or"     → "120 calls, or"
    body = re.sub(r"\s*[—–]\s*", ", ", body)

    # Spaced hyphen as clause separator: " - word" → ". Word"
    def _hyphen_to_period(m: re.Match) -> str:
        rest = m.group(1)
        return ". " + rest[0].upper() + rest[1:] if rest else ". "

    body = re.sub(r"\s+-\s+(\S)", _hyphen_to_period, body)

    # Ensure comma after first name at position 0 ("Morgan noticed" → "Morgan, noticed")
    if first_name:
        body = re.sub(
            rf"^({re.escape(first_name)})\s+(?=[^,])",
            rf"\1, ",
            body,
        )

    # Clean up artefacts: double-comma, ", ," space issues
    body = re.sub(r",\s{2,}", ", ", body)   # collapse multiple spaces after comma
    body = re.sub(r",\s*,",  ",",  body)    # double comma
    body = re.sub(r",\s*\.", ".",  body)    # ",." → "."

    return body.strip()


def _validate(result: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - set(result.keys())
    if missing:
        raise ValueError(f"SMS response missing keys: {missing}")
    body = result.get("body", "")
    if len(body) > _MAX_CHARS:
        # SmsLengthError (not ValueError) → tenacity WILL retry this
        raise SmsLengthError(
            f"SMS body too long: {len(body)} chars (max {_MAX_CHARS}). Body: {body[:80]}..."
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    # ValueError  = missing keys (malformed response) → do NOT retry
    # SmsJsonError  = Claude returned prose instead of JSON → DO retry
    # SmsLengthError = body still too long after trim  → DO retry
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

    Returns a dict with 'body' (ready to send — no substitution needed),
    variant_id, framework_used, motion_used, char_count.
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
        # Force JSON-only output at the model level — no preamble, no markdown
        system=(
            "You are an SMS copywriter. "
            "Respond ONLY with a valid JSON object. "
            "Do NOT write any text before or after the JSON. "
            "Do NOT use markdown code fences. "
            "Begin your response with '{' and end with '}'."
        ),
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

    raw    = response.content[0].text
    result = _parse_response(raw)

    # Strip any AI-sounding dashes and ensure "Name," comma format
    first_name = lead.get("first_name", "")
    result["body"] = _humanize_body(result.get("body", ""), first_name)

    # Silently trim to fit within the body budget (footer appended later)
    result["body"] = _trim_to_limit(result["body"], max_chars=_MAX_CHARS - 5)
    result["char_count"] = len(result["body"])   # recount after cleanup

    _validate(result)

    # Log cost
    usage = response.usage
    input_cost  = usage.input_tokens * _INPUT_COST_PER_TOKEN
    output_cost = usage.output_tokens * _OUTPUT_COST_PER_TOKEN
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) * _CACHE_WRITE_COST_PER_TOKEN
    cache_read  = getattr(usage, "cache_read_input_tokens",       0) * _CACHE_READ_COST_PER_TOKEN
    total_cost  = input_cost + output_cost + cache_write + cache_read
    cost_tracker.log(
        lead.get("lead_id"), "anthropic", "sms_generation", total_cost,
    )

    # Return the cost so the pipeline can store it on the sms_leads record
    result["ai_cost_usd"] = round(total_cost, 8)

    return result
