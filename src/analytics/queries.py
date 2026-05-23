"""
Analytics queries.

All SQL aggregations the dashboard and CLI use. Read-only on the ledger.

The schema we read from:
  leads (lead_id, email, vertical, motion, intent_confidence, variant_id,
         framework, recommended_angle, test_id, status, created_at, ...)
  events (lead_id, event_type, occurred_at, smartlead_payload)

The orchestrator writes `framework` to leads when it generates an email
(it comes from the `framework_used` field in the email JSON output).
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VariantStats:
    variant_id: str
    framework: str
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    bounced: int = 0
    booked: int = 0

    @property
    def open_rate(self) -> float:
        return self.opened / self.sent if self.sent else 0.0

    @property
    def reply_rate(self) -> float:
        return self.replied / self.sent if self.sent else 0.0

    @property
    def click_rate(self) -> float:
        return self.clicked / self.sent if self.sent else 0.0

    @property
    def book_rate(self) -> float:
        return self.booked / self.sent if self.sent else 0.0

    @property
    def bounce_rate(self) -> float:
        return self.bounced / self.sent if self.sent else 0.0


@dataclass
class FrameworkStats:
    framework: str
    sent: int = 0
    opened: int = 0
    replied: int = 0
    booked: int = 0
    variant_ids: list[str] = field(default_factory=list)

    @property
    def open_rate(self) -> float:
        return self.opened / self.sent if self.sent else 0.0

    @property
    def reply_rate(self) -> float:
        return self.replied / self.sent if self.sent else 0.0

    @property
    def book_rate(self) -> float:
        return self.booked / self.sent if self.sent else 0.0


@dataclass
class HeatmapCell:
    """One cell in a 2D heatmap (e.g. framework × motion)."""

    row_key: str
    col_key: str
    sent: int
    replied: int
    booked: int

    @property
    def reply_rate(self) -> float:
        return self.replied / self.sent if self.sent else 0.0

    @property
    def book_rate(self) -> float:
        return self.booked / self.sent if self.sent else 0.0


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def variant_stats(db_path: Path, test_id: str) -> list[VariantStats]:
    """Per-variant aggregate. Each variant joins to its framework via leads.framework."""
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            l.variant_id,
            COALESCE(l.framework, 'unknown') AS framework,
            SUM(CASE WHEN e.event_type = 'sent'        THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN e.event_type = 'opened'      THEN 1 ELSE 0 END) AS opened,
            SUM(CASE WHEN e.event_type = 'clicked'     THEN 1 ELSE 0 END) AS clicked,
            SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
            SUM(CASE WHEN e.event_type = 'bounced'     THEN 1 ELSE 0 END) AS bounced,
            SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
        FROM leads l
        LEFT JOIN events e ON e.lead_id = l.lead_id
        WHERE l.test_id = ?
        GROUP BY l.variant_id, l.framework
        ORDER BY l.variant_id
        """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        VariantStats(
            variant_id=r["variant_id"],
            framework=r["framework"],
            sent=r["sent"] or 0,
            opened=r["opened"] or 0,
            clicked=r["clicked"] or 0,
            replied=r["replied"] or 0,
            bounced=r["bounced"] or 0,
            booked=r["booked"] or 0,
        )
        for r in rows
        if r["variant_id"] is not None
    ]


def framework_stats(db_path: Path, test_id: str) -> list[FrameworkStats]:
    """Roll-up by framework. Multiple variants may share a framework (e.g. PPP for V1, V2, V3)."""
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COALESCE(l.framework, 'unknown') AS framework,
            GROUP_CONCAT(DISTINCT l.variant_id) AS variant_ids,
            SUM(CASE WHEN e.event_type = 'sent'        THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN e.event_type = 'opened'      THEN 1 ELSE 0 END) AS opened,
            SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
            SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
        FROM leads l
        LEFT JOIN events e ON e.lead_id = l.lead_id
        WHERE l.test_id = ?
        GROUP BY l.framework
        ORDER BY replied DESC
        """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        FrameworkStats(
            framework=r["framework"],
            sent=r["sent"] or 0,
            opened=r["opened"] or 0,
            replied=r["replied"] or 0,
            booked=r["booked"] or 0,
            variant_ids=(r["variant_ids"] or "").split(",") if r["variant_ids"] else [],
        )
        for r in rows
    ]


def framework_motion_heatmap(db_path: Path, test_id: str) -> list[HeatmapCell]:
    """Reply + book rates by framework × motion. The killer chart."""
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COALESCE(l.framework, 'unknown') AS framework,
            COALESCE(l.motion, 'unknown')   AS motion,
            COUNT(DISTINCT l.lead_id) AS sent,
            SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
            SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
        FROM leads l
        LEFT JOIN events e ON e.lead_id = l.lead_id
        WHERE l.test_id = ?
        GROUP BY l.framework, l.motion
        """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        HeatmapCell(
            row_key=r["framework"],
            col_key=r["motion"],
            sent=r["sent"] or 0,
            replied=r["replied"] or 0,
            booked=r["booked"] or 0,
        )
        for r in rows
    ]


def variant_vertical_heatmap(db_path: Path, test_id: str) -> list[HeatmapCell]:
    """Reply rate by variant × vertical. Useful for vertical-specific allocation."""
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            l.variant_id AS variant,
            COALESCE(l.vertical, 'unknown') AS vertical,
            COUNT(DISTINCT l.lead_id) AS sent,
            SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
            SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
        FROM leads l
        LEFT JOIN events e ON e.lead_id = l.lead_id
        WHERE l.test_id = ?
        GROUP BY l.variant_id, l.vertical
        HAVING sent >= 50
        """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        HeatmapCell(
            row_key=r["variant"],
            col_key=r["vertical"],
            sent=r["sent"] or 0,
            replied=r["replied"] or 0,
            booked=r["booked"] or 0,
        )
        for r in rows
    ]


def two_proportion_z_test(s_a: int, n_a: int, s_b: int, n_b: int) -> float:
    """p-value for H0: p_a == p_b. Two-tailed."""
    if n_a == 0 or n_b == 0:
        return 1.0
    p_a = s_a / n_a
    p_b = s_b / n_b
    p_pool = (s_a + s_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 1.0
    z = (p_a - p_b) / se
    return 2 * (1 - _normal_cdf(abs(z)))


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def significance_status(
    variants: list[VariantStats], min_per_variant: int, primary_metric: str
) -> dict:
    """
    Returns a dict with:
      - ready: bool — all variants have minimum sample
      - leader_variant_id: str | None
      - significant_winners: list[str] — variants statistically beaten by leader
      - days_to_ready: int | None — rough estimate
    """
    if not variants:
        return {
            "ready": False,
            "leader_variant_id": None,
            "significant_winners": [],
            "min_sent": 0,
            "min_required": min_per_variant,
        }

    min_sent = min(v.sent for v in variants)
    ready = min_sent >= min_per_variant

    metric_attr = primary_metric.replace("_rate", "")
    if metric_attr == "book":
        metric_attr = "booked"
    leader = max(variants, key=lambda v: getattr(v, primary_metric))

    significant_winners = []
    if ready:
        for v in variants:
            if v.variant_id == leader.variant_id:
                continue
            p = two_proportion_z_test(
                getattr(leader, metric_attr),
                leader.sent,
                getattr(v, metric_attr),
                v.sent,
            )
            if p < 0.05:
                significant_winners.append(v.variant_id)

    return {
        "ready": ready,
        "leader_variant_id": leader.variant_id,
        "leader_framework": leader.framework,
        "significant_winners": significant_winners,
        "min_sent": min_sent,
        "min_required": min_per_variant,
    }


def cost_summary(db_path: Path, test_id: str) -> dict:
    """Total pipeline cost + cost per booked call."""
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(c.cost_usd), 0) AS total_cost
        FROM leads l
        LEFT JOIN costs c ON c.lead_id = l.lead_id
        WHERE l.test_id = ?
        """,
        (test_id,),
    )
    total_cost = cur.fetchone()["total_cost"]
    cur.execute(
        """
        SELECT COUNT(*) AS booked FROM events e
        JOIN leads l ON l.lead_id = e.lead_id
        WHERE l.test_id = ? AND e.event_type = 'booked_call'
        """,
        (test_id,),
    )
    booked = cur.fetchone()["booked"]
    conn.close()
    return {
        "total_cost_usd": total_cost or 0,
        "booked": booked,
        "cost_per_booked": (total_cost / booked) if booked else None,
    }
