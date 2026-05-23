"""
Variant assigner. Deterministically assigns each lead to a variant arm.

Same lead always lands in the same variant across re-runs (hashes lead_id +
test_id and buckets by configured weights).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

log = logging.getLogger(__name__)


def assign_variant(lead_id: str, test_config: dict[str, Any]) -> dict[str, Any]:
    """Pick an arm for this lead deterministically."""
    arms = test_config["arms"]
    test_id = test_config["id"]

    total_weight = sum(arm["weight"] for arm in arms)
    if not 0.99 <= total_weight <= 1.01:
        raise ValueError(
            f"Test {test_id}: arm weights sum to {total_weight}, must be ~1.0"
        )

    digest = hashlib.sha256(f"{lead_id}:{test_id}".encode()).hexdigest()
    hash_int = int(digest[:8], 16)
    bucket = hash_int / 0xFFFFFFFF

    cumulative = 0.0
    for arm in arms:
        cumulative += arm["weight"]
        if bucket < cumulative:
            return {**arm, "test_id": test_id}

    return {**arms[-1], "test_id": test_id}


def apply_variant_overrides(
    base_data: dict[str, Any], variant_arm: dict[str, Any]
) -> dict[str, Any]:
    """Merge variant arm's overrides into the base analysis/email/script data."""
    overrides = variant_arm.get("overrides", {})
    return {**base_data, **overrides}
