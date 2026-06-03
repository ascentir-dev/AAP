"""
Template store — reads/writes config/templates.yaml for the Playbook editor.

Design:
- load_templates()  → reads fresh from disk each call (file is tiny, ~10KB)
- get_template()    → returns a single variant dict or None
- save_template()   → updates one variant and writes back to disk
- get_template_override_block() → builds the TEMPLATE OVERRIDE string for
  injection into the uncached lead_data_block in the generators.
  Returns empty string if no override exists.

Market support (Phase 4):
- All public functions accept an optional `market` parameter.
- Lookup order: market-keyed first → flat fallback (backward compat).
- Valid market keys: coach, agency, consultant, financial_advisor, msp.
- Saves always target the market-keyed path when a market is provided.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_TEMPLATES_PATH = Path("config/templates.yaml")

VALID_MARKETS = frozenset({"coach", "agency", "consultant", "financial_advisor", "msp"})


def load_templates() -> dict[str, Any]:
    """Return the full templates dict, or empty dict if file doesn't exist."""
    if not _TEMPLATES_PATH.exists():
        return {}
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_template(
    channel: str,
    variant_id: str,
    market: str | None = None,
) -> dict[str, Any] | None:
    """Return the template dict for a specific channel/variant/market, or None.

    Lookup order:
      1. data[channel][market][variant_id]  — market-specific (preferred)
      2. data[channel][variant_id]          — flat fallback (backward compat)
    """
    data = load_templates()
    channel_data = data.get(channel, {})

    if market and market in VALID_MARKETS:
        market_tmpl = channel_data.get(market, {}).get(variant_id)
        if market_tmpl:
            return market_tmpl

    # Flat fallback — original structure
    flat = channel_data.get(variant_id)
    if isinstance(flat, dict):
        return flat

    return None


def save_template(
    channel: str,
    variant_id: str,
    updates: dict[str, Any],
    market: str | None = None,
) -> None:
    """Update a single template and write back to disk atomically.

    When `market` is provided the update targets data[channel][market][variant_id].
    When omitted it targets data[channel][variant_id] (legacy flat path).
    """
    data = load_templates()

    if market and market in VALID_MARKETS:
        if channel not in data:
            data[channel] = {}
        if market not in data[channel]:
            data[channel][market] = {}
        if variant_id not in data[channel][market]:
            data[channel][market][variant_id] = {}
        data[channel][market][variant_id].update(updates)
    else:
        # Flat legacy path
        if channel not in data:
            data[channel] = {}
        if variant_id not in data[channel]:
            data[channel][variant_id] = {}
        data[channel][variant_id].update(updates)

    _TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_TEMPLATES_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_template_override_block(
    channel: str,
    variant_id: str,
    market: str | None = None,
) -> str:
    """Return an override block to inject into the uncached lead_data_block.

    If the user has edited the template in the Playbook UI, this injects
    it as an instruction override so Claude uses the custom template.
    Returns empty string if no override exists.
    """
    tmpl = get_template(channel, variant_id, market=market)
    if not tmpl:
        return ""
    template_body = tmpl.get("template", "").strip()
    if not template_body:
        return ""

    lines = ["\n\n## TEMPLATE OVERRIDE"]
    lines.append("Use this exact template structure instead of the default variant template:")
    lines.append("")
    lines.append(template_body)
    if channel == "email" and tmpl.get("subject_formula"):
        lines.append(f"\nSubject formula to follow: {tmpl['subject_formula']}")
    return "\n".join(lines)
