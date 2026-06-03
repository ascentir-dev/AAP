"""
Video script variant selector.

Loads the 4 Loom-style script variants from config/video_scripts.yaml,
deterministically assigns a variant per lead (hash of lead_id % 4),
and renders the script with lead-specific placeholders.

Market support (Phase 4):
  Variants are nested by market key in video_scripts.yaml:
    variants:
      coach:
        V1: ...
        V2: ...
      agency:
        V1: ...
      ...
  When a lead has a `market` field that matches a key in the YAML, the
  market-specific scripts are used.  Falls back to the top-level flat
  structure for backward compat.

Usage:
    from src.ai_cold_email.video.script.video_scripts import (
        get_script_for_lead, list_variants, VARIANT_IDS
    )

    script_text, variant_id = get_script_for_lead(lead)
"""
from __future__ import annotations

import hashlib
import textwrap
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path("config/video_scripts.yaml")
VARIANT_IDS  = ["V1", "V2", "V3", "V4"]
VALID_MARKETS = frozenset({"coach", "agency", "consultant", "financial_advisor", "msp"})


@lru_cache(maxsize=1)
def _load_variants_raw() -> dict[str, Any]:
    """Load video_scripts.yaml once and cache the raw variants dict."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["variants"]


def _get_market_variants(market: str | None) -> dict[str, Any]:
    """Return the correct variant dict for a market (or flat fallback)."""
    raw = _load_variants_raw()
    if market and market in VALID_MARKETS and market in raw:
        return raw[market]
    # Flat fallback: top-level keys are V1..V4
    return raw


# Keep backward-compat alias used by dashboard
def _load_variants() -> dict[str, Any]:
    """Return the flat variant dict (legacy/dashboard usage)."""
    return _load_variants_raw()


def list_variants(market: str | None = None) -> list[dict[str, str]]:
    """Return lightweight metadata for all variants (for UI/API use)."""
    variants = _get_market_variants(market)
    return [
        {
            "id":          vid,
            "name":        v["name"],
            "hook_style":  v["hook_style"],
            "description": v["description"].strip(),
        }
        for vid, v in variants.items()
        if vid in VARIANT_IDS
    ]


def assign_variant(lead_id: str) -> str:
    """
    Deterministically assign a variant ID to a lead.
    Same lead always gets the same variant — consistent across retries.
    Uses MD5 of lead_id mod 4.
    """
    idx = int(hashlib.md5(lead_id.encode()).hexdigest(), 16) % len(VARIANT_IDS)
    return VARIANT_IDS[idx]


def render_script(
    variant_id: str,
    lead: dict[str, Any],
    market: str | None = None,
) -> str:
    """
    Load the raw script for variant_id and fill in lead-specific placeholders.

    Supported placeholders:
        {first_name}  — lead's first name
        {company}     — lead's company name
    """
    variants = _get_market_variants(market)
    if variant_id not in variants:
        raise ValueError(
            f"Unknown video script variant: {variant_id!r}. "
            f"Valid: {list(variants.keys())}"
        )

    raw = textwrap.dedent(variants[variant_id]["script"]).strip()

    first_name = lead.get("first_name") or lead.get("name", "there")
    company    = lead.get("company", "your company")

    return raw.replace("{first_name}", first_name).replace("{company}", company)


def get_script_for_lead(lead: dict[str, Any]) -> tuple[str, str]:
    """
    Convenience function: assign variant + render script in one call.
    Respects the lead's `market` field for market-specific scripts.

    Returns:
        (script_text, variant_id)
    """
    lead_id    = str(lead.get("lead_id") or lead.get("email") or lead.get("company", ""))
    market     = lead.get("market") or None
    variant_id = assign_variant(lead_id)
    script     = render_script(variant_id, lead, market=market)
    return script, variant_id
