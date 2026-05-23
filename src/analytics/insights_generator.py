"""
AI insights generator.

Calls Claude Sonnet 4.6 with the multi-dimensional analytics view (variants,
frameworks, motions, verticals, sample replies) and asks for 2-4 actionable
patterns prioritized by impact.

Run weekly. Costs ~$0.05 per run.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from anthropic import Anthropic

from src.analytics.queries import (
    framework_motion_heatmap,
    framework_stats,
    variant_stats,
    variant_vertical_heatmap,
)
from src.utils.settings import load_settings

log = logging.getLogger(__name__)


PROMPT_TEMPLATE = """You are an expert cold-email analytics professional analyzing the performance of an A/B test.

Your job: read the multi-dimensional data below and surface 2-4 actionable patterns that should change what we do next. Prioritize patterns that affect booked-call rate (the metric that produces revenue) over patterns that only affect reply rate.

## The Active Test

Test ID: {test_id}
Description: {description}
Primary metric: {primary_metric}
Day: {day_of_test}

The test has 9 variants modeled on proven cold-email frameworks:
- PPP (Variants 1, 2, 3) — Praise / Picture / Push (gym "On Framework")
- AIDA (Variant 4) — Attention / Interest / Desire / Action
- 3 Cs (Variant 5) — Compliment / Case study / CTA (Berman's Cold Email Manifesto)
- QVC (Variant 6) — Question / Value / CTA (shortest)
- Authority (Variant 7) — Suby's authority + aggregate proof
- InvertedDemand (Variant 8) — scarcity-flavored heads-up framing
- PAS (Variant 9) — Problem / Agitate / Solve (concerning observation)

Each lead is also tagged with motion (plg_self_serve | hybrid_sales_assisted | sales_led_outbound) and vertical.

## Framework Performance (roll-up)

{framework_table}

## Variant Performance

{variant_table}

## Framework × Motion Heatmap (reply rate, sent count)

{heatmap_table}

## Variant × Vertical (cells with 50+ sent)

{vertical_table}

## Sample Replies (last 7 days, random {n_replies})

{sample_replies}

## Sample Booked Calls (last 7 days)

{sample_booked}

## Your Task

Surface 2-4 actionable patterns. For each:

**Pattern N: [one-line summary]**
[2-3 sentences explaining the data behind it. Cite specific numbers.]
[1-2 sentences with a specific recommended action — e.g., "drop Variants 1, 2, 3 from PLG traffic" or "promote Variant 6 to 50% weight for sales-led leads".]

Rules:
- Only surface patterns where the data is statistically meaningful (variant or cell has at least 1,000 sent).
- Don't speculate. If a pattern doesn't have enough data, say so honestly.
- If the test is too early to surface meaningful patterns, say "Need more data. Earliest signal expected at X sent per variant. Currently at Y."
- Pattern recommendations should be concrete actions, not vague ("consider exploring X").
- Output as plain text. No markdown headers above patterns. Use **bold** only for pattern titles.
"""


def generate_insights(db_path: Path) -> str:
    settings = load_settings()
    test = settings.active_test_config()
    if not test:
        return "No active test configured."

    test_id = test["id"]
    primary_metric = test.get("primary_metric", "reply_rate")

    # Framework roll-up
    framework_data = framework_stats(db_path, test_id)
    framework_table = _format_framework_table(framework_data)

    # Variant detail
    variant_data = variant_stats(db_path, test_id)
    variant_table = _format_variant_table(variant_data)

    # Framework × motion heatmap
    heatmap = framework_motion_heatmap(db_path, test_id)
    heatmap_table = _format_heatmap(heatmap)

    # Variant × vertical
    vertical = variant_vertical_heatmap(db_path, test_id)
    vertical_table = _format_vertical_heatmap(vertical)

    # Sample replies + bookings
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT smartlead_payload FROM events
        WHERE event_type='replied' AND occurred_at > datetime('now','-7 days')
        ORDER BY RANDOM() LIMIT 20
        """
    )
    reply_payloads = [json.loads(r[0]) for r in cur.fetchall() if r[0]]
    sample_replies = _format_replies(reply_payloads)
    n_replies = len(reply_payloads)

    cur.execute(
        """
        SELECT smartlead_payload FROM events
        WHERE event_type='booked_call' AND occurred_at > datetime('now','-7 days')
        LIMIT 10
        """
    )
    booked_payloads = [json.loads(r[0]) for r in cur.fetchall() if r[0]]
    sample_booked = _format_booked(booked_payloads)
    conn.close()

    prompt = PROMPT_TEMPLATE.format(
        test_id=test_id,
        description=test.get("description", ""),
        primary_metric=primary_metric,
        day_of_test=test.get("day_of_test", "unknown"),
        framework_table=framework_table,
        variant_table=variant_table,
        heatmap_table=heatmap_table,
        vertical_table=vertical_table,
        sample_replies=sample_replies,
        sample_booked=sample_booked,
        n_replies=n_replies,
    )

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.generation_model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _format_framework_table(stats) -> str:
    if not stats:
        return "(no data)"
    lines = ["framework | sent | open% | reply% | booked | book%"]
    for s in stats:
        if s.sent < 100:
            continue
        lines.append(
            f"{s.framework} | {s.sent:,} | {s.open_rate * 100:.1f} | "
            f"{s.reply_rate * 100:.2f} | {s.booked} | {s.book_rate * 100:.2f}"
        )
    return "\n".join(lines)


def _format_variant_table(stats) -> str:
    if not stats:
        return "(no data)"
    lines = ["variant_id | framework | sent | open% | reply% | click% | booked | book%"]
    for s in stats:
        if s.sent < 100:
            continue
        lines.append(
            f"{s.variant_id} | {s.framework} | {s.sent:,} | "
            f"{s.open_rate * 100:.1f} | {s.reply_rate * 100:.2f} | "
            f"{s.click_rate * 100:.1f} | {s.booked} | {s.book_rate * 100:.2f}"
        )
    return "\n".join(lines)


def _format_heatmap(cells) -> str:
    if not cells:
        return "(no data)"
    lines = ["framework | motion | sent | reply% | book%"]
    for c in cells:
        if c.sent < 100:
            continue
        lines.append(
            f"{c.row_key} | {c.col_key} | {c.sent:,} | "
            f"{c.reply_rate * 100:.2f} | {c.book_rate * 100:.2f}"
        )
    return "\n".join(lines)


def _format_vertical_heatmap(cells) -> str:
    if not cells:
        return "(no vertical data yet)"
    lines = ["variant | vertical | sent | reply% | book%"]
    for c in sorted(cells, key=lambda c: -c.reply_rate)[:30]:
        lines.append(
            f"{c.row_key} | {c.col_key} | {c.sent:,} | "
            f"{c.reply_rate * 100:.2f} | {c.book_rate * 100:.2f}"
        )
    return "\n".join(lines)


def _format_replies(payloads) -> str:
    if not payloads:
        return "(no replies in last 7 days)"
    out = []
    for i, p in enumerate(payloads, 1):
        body = p.get("reply_body") or p.get("message") or ""
        out.append(f"Reply {i}: {body[:300]}")
    return "\n\n".join(out)


def _format_booked(payloads) -> str:
    if not payloads:
        return "(no booked calls in last 7 days)"
    return f"{len(payloads)} bookings in the last 7 days"
