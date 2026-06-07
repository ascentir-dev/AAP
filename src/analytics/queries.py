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
    sent: int = 0       # emails actually delivered (from SmartLead analytics)
    in_queue: int = 0   # leads added to SmartLead campaign
    sent_video: int = 0
    sent_email_only: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
    bounced: int = 0
    booked: int = 0

    @property
    def video_pct(self) -> float:
        return self.sent_video / self.sent if self.sent else 0.0

    @property
    def email_only_pct(self) -> float:
        return self.sent_email_only / self.sent if self.sent else 0.0

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
    """One cell in a 2D heatmap (e.g. framework × motion).

    ``replied`` and ``opened`` are stored as float so the campaign-stats
    proportional path can preserve fractional counts (e.g. 0.43 replies for
    a small ICP cell) rather than rounding them to zero.  The per-lead-event
    fallback path always passes plain integers, which are also valid floats.
    """

    row_key: str
    col_key: str
    sent: int
    replied: float
    booked: float
    opened: float = 0

    @property
    def open_rate(self) -> float:
        return self.opened / self.sent if self.sent else 0.0

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
    """Per-variant aggregate. Each variant joins to its framework via leads.framework.

    Sent count prefers campaign_stats.delivered (emails actually delivered, from
    SmartLead analytics sync) and falls back to leads.status count (leads added to
    SmartLead queue) when no analytics have been synced yet.
    in_queue = leads added to SmartLead campaigns (leads.status = 'sent').
    Engagement counts come from the events table (manual sync or webhooks).
    """
    conn = _connect(db_path)
    cur = conn.cursor()

    # Check whether campaign_stats table exists and has data
    try:
        cs_count = conn.execute(
            "SELECT COUNT(*) FROM campaign_stats WHERE variant_id LIKE 'Variant%'"
        ).fetchone()[0]
    except Exception:
        cs_count = 0

    if cs_count > 0:
        # Group by variant_id only (not framework) so each variant produces exactly
        # one row, even if leads have different framework values (e.g. a fallback lead).
        # Delivered/opened/replied come from campaign_stats (per-campaign aggregate).
        # sent_video/sent_email_only/booked come from per-lead DB data.
        cur.execute(
            """
            SELECT
                l.variant_id,
                MAX(COALESCE(l.framework, 'unknown')) AS framework,
                MAX(COALESCE(cs.delivered, 0)) AS sent,
                MAX(COALESCE(cs.in_queue,  0)) AS in_queue,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') AND l.email_type = 'video'
                                    THEN l.lead_id END) AS sent_video,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') AND l.email_type = 'email_only'
                                    THEN l.lead_id END) AS sent_email_only,
                MAX(COALESCE(cs.opened,  0)) AS opened,
                MAX(COALESCE(cs.clicked, 0)) AS clicked,
                MAX(COALESCE(cs.replied, 0)) AS replied,
                MAX(COALESCE(cs.bounced, 0)) AS bounced,
                SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
            FROM leads l
            LEFT JOIN campaign_stats cs ON cs.variant_id = l.variant_id
            LEFT JOIN events e ON e.lead_id = l.lead_id
            WHERE l.test_id = ?
            GROUP BY l.variant_id
            ORDER BY l.variant_id
            """,
            (test_id,),
        )
    else:
        # No analytics synced yet — fall back to leads.status count for sent/in_queue.
        cur.execute(
            """
            SELECT
                l.variant_id,
                COALESCE(l.framework, 'unknown') AS framework,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') THEN l.lead_id END) AS sent,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') THEN l.lead_id END) AS in_queue,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') AND l.email_type = 'video'
                                    THEN l.lead_id END) AS sent_video,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success') AND l.email_type = 'email_only'
                                    THEN l.lead_id END) AS sent_email_only,
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
            in_queue=r["in_queue"] or 0,
            sent_video=r["sent_video"] or 0,
            sent_email_only=r["sent_email_only"] or 0,
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
    """ICP distribution by variant × vertical.

    Priority 1 — per-lead events (events table, populated by SmartLead sync):
        Joins leads → events to get true per-ICP opened/replied counts.
        Different ICPs CAN show different rates; this is the accurate view.

    Priority 2 — campaign-stats available, no per-lead events yet:
        Shows accurate per-ICP delivered SENT counts (proportionally scaled from
        campaign_stats.delivered) but 0% for open/reply rates.  Showing a uniform
        proportional rate for every ICP in a variant is misleading because it
        implies per-ICP differentiation that doesn't exist in the data.

    Priority 3 — nothing synced yet:
        Returns queue-count sent cells with 0% rates.
    """
    conn = _connect(db_path)
    cur = conn.cursor()

    # ── Check what data is available ────────────────────────────────────────────
    try:
        cs_count = conn.execute(
            "SELECT COUNT(*) FROM campaign_stats WHERE variant_id LIKE 'Variant%'"
        ).fetchone()[0]
    except Exception:
        cs_count = 0

    try:
        event_count = conn.execute(
            """
            SELECT COUNT(*) FROM events e
            JOIN leads l ON l.lead_id = e.lead_id
            WHERE l.test_id = ?
              AND e.event_type IN ('opened', 'replied', 'booked_call')
            """,
            (test_id,),
        ).fetchone()[0]
    except Exception:
        event_count = 0

    # ── Path 1: Per-lead events — true per-ICP rates ─────────────────────────
    # IMPORTANT: `sent` must use the same proportional scaling as Path 2 so the
    # matrix totals match SmartLead's delivered count (~543), NOT the leads-table
    # queue count (~1304).  We join campaign_stats for the delivered denominator
    # and compute icp_delivered = round(icp_queue / cs_in_queue * cs_delivered).
    # opened/replied/booked come from the real per-lead events — giving true
    # differentiated rates per ICP rather than a uniform distribution.
    if event_count > 0:
        cur.execute(
            """
            SELECT
                l.variant_id AS variant,
                COALESCE(l.vertical, 'unknown') AS vertical,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success')
                                    THEN l.lead_id END)                 AS icp_queue,
                MAX(COALESCE(cs.in_queue,  0))                          AS cs_in_queue,
                MAX(COALESCE(cs.delivered, 0))                          AS cs_delivered,
                SUM(CASE WHEN e.event_type = 'opened'      THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
                SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
            FROM leads l
            LEFT JOIN campaign_stats cs ON cs.variant_id = l.variant_id
            LEFT JOIN events e ON e.lead_id = l.lead_id
            WHERE l.test_id = ?
              AND l.vertical IS NOT NULL
            GROUP BY l.variant_id, l.vertical
            """,
            (test_id,),
        )
        rows = cur.fetchall()
        conn.close()
        result: list[HeatmapCell] = []
        for r in rows:
            icp_queue   = r["icp_queue"]    or 0
            cs_in_queue = r["cs_in_queue"]  or 0
            cs_delivered = r["cs_delivered"] or 0
            # Scale ICP queue count to actual SmartLead delivered count
            if cs_in_queue > 0 and cs_delivered > 0:
                icp_delivered = round(icp_queue / cs_in_queue * cs_delivered)
            else:
                icp_delivered = icp_queue
            if icp_delivered < 1:
                continue
            result.append(HeatmapCell(
                row_key = r["variant"],
                col_key = r["vertical"],
                sent    = icp_delivered,
                opened  = r["opened"]  or 0,
                replied = r["replied"] or 0,
                booked  = r["booked"]  or 0,
            ))
        return result

    # ── Path 2: Campaign-stats only — show accurate sent counts, 0% rates ────
    # We intentionally do NOT distribute the variant-level reply rate across ICPs
    # because that produces an identical rate for every ICP row in a column,
    # which is misleading.  Rates only make sense once per-lead events are synced.
    if cs_count > 0:
        cur.execute(
            """
            SELECT
                l.variant_id                                                    AS variant,
                COALESCE(l.vertical, 'unknown')                                 AS vertical,
                COUNT(DISTINCT CASE WHEN l.status IN ('sent','success')
                                    THEN l.lead_id END)                         AS icp_sent,
                MAX(COALESCE(cs.in_queue,  0))                                  AS cs_in_queue,
                MAX(COALESCE(cs.delivered, 0))                                  AS cs_delivered
            FROM leads l
            LEFT JOIN campaign_stats cs ON cs.variant_id = l.variant_id
            WHERE l.test_id = ?
              AND l.vertical IS NOT NULL
            GROUP BY l.variant_id, l.vertical
            HAVING icp_sent >= 1
            """,
            (test_id,),
        )
        rows = cur.fetchall()
        conn.close()

        result: list[HeatmapCell] = []
        for r in rows:
            icp_queue = r["icp_sent"]     or 0
            cs_del    = r["cs_delivered"] or 0
            cs_queue  = r["cs_in_queue"]  or 0
            # Scale queue count to delivered count proportionally
            icp_delivered = round(icp_queue / cs_queue * cs_del) if cs_queue > 0 and cs_del > 0 else icp_queue
            if icp_delivered < 1:
                continue
            result.append(HeatmapCell(
                row_key = r["variant"],
                col_key = r["vertical"],
                sent    = icp_delivered,
                opened  = 0,   # no per-ICP rate without per-lead events
                replied = 0,   # no per-ICP rate without per-lead events
                booked  = 0,
            ))
        return result

    # ── Path 3: Nothing synced — return queue counts with 0% rates ───────────
    cur.execute(
        """
        SELECT
            l.variant_id AS variant,
            COALESCE(l.vertical, 'unknown') AS vertical,
            COUNT(DISTINCT CASE WHEN l.status IN ('sent','success')
                                THEN l.lead_id END) AS sent
        FROM leads l
        WHERE l.test_id = ?
          AND l.vertical IS NOT NULL
        GROUP BY l.variant_id, l.vertical
        HAVING sent >= 1
        """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        HeatmapCell(
            row_key = r["variant"],
            col_key = r["vertical"],
            sent    = r["sent"] or 0,
            opened  = 0,
            replied = 0,
            booked  = 0,
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


@dataclass
class SubjectLineStats:
    """Per-subject-line open/reply performance. Isolates the subject line variable."""
    subject_line: str
    variant_id: str
    sent: int = 0
    opened: int = 0
    replied: int = 0
    booked: int = 0
    is_grouped: bool = False  # True = aggregate row for personalized/unique subjects

    @property
    def open_rate(self) -> float:
        return self.opened / self.sent if self.sent else 0.0

    @property
    def reply_rate(self) -> float:
        return self.replied / self.sent if self.sent else 0.0

    @property
    def book_rate(self) -> float:
        return self.booked / self.sent if self.sent else 0.0


def _subject_cluster_key(s: str) -> str:
    """Return the normalised key used to group subject lines by template.

    Special suffix rules fire first so ICP-suffix subjects ("X — one spot open",
    "[co] + ascentir") always land in their own dedicated cluster regardless of
    what their first words happen to be.
    """
    import re as _re
    sl = s.lower().strip()

    # Suffix-based special clusters
    if "ascentir" in sl:
        return "__ascentir__"
    if "one spot open" in sl:
        return "__one_spot_open__"

    words = [_re.sub(r"[^a-z0-9]", "", w) for w in sl.split()]
    words = [w for w in words if w]
    if not words:
        return "__empty__"
    if len(words) == 1:
        return "__single__"

    # Short lead words ("a", "i", "an") → use 3 words so "a thought on" ≠ "a few results"
    if len(words[0]) <= 2 and len(words) >= 3:
        return " ".join(words[:3])
    return " ".join(words[:2])


# Words that signal an industry / ICP vertical rather than a company name or first name
_INDUSTRY_KW: frozenset[str] = frozenset({
    "marketing", "consulting", "advisory", "agency", "agencies",
    "media", "b2b", "branding", "pr", "training", "coaching",
    "msp", "recruiting", "staffing", "financial", "operations",
    "management", "digital", "creative", "strategy", "sales",
    "advertising", "content", "fintech", "saas", "healthcare",
    "insurance", "accounting", "wealth", "investment", "advisor",
    "owner", "firms", "firm", "services",
})


def _infer_template(
    subjects: list[str],
    sent_weights: list[int] | None = None,
) -> tuple[str, bool]:
    """Given a cluster of subject lines that share a structural pattern, return
    (template_string, is_personalized).

    is_personalized=True when a [bracket] placeholder was inserted.

    sent_weights (optional) — parallel list of scaled-sent counts per subject.
    When provided, dominance is tested by sent volume rather than row count so
    that "taking on new clients?" (147×) correctly beats "members?" (1×) even
    though the DB returns only 4 distinct rows.

    Algorithm:
      1. Sent-weighted (or count-weighted) static check — if one subject covers
         ≥85% of the cluster’s volume, return it as-is.
      2. All single-word subjects → "[first name]".
      3. Majority-based (≥75%) word-level common prefix + suffix across the
         distinct subjects (tolerates a few outliers like "right now?" vs "now?").
      4. Replace the varying middle with a typed placeholder:
           "first name"  — short single words (avg ≤1.2 words, no multi-word)
           "company"     — possessive ending (…’s / …’) OR no industry keywords
           "industry"    — multi-word varying parts matching industry vocabulary
         The possessive token is preserved: "[company]’s".
      5. Fallback → most-sent subject as-is (static).
    """
    from collections import Counter as _Counter

    if not subjects:
        return ("", False)

    # ── 1. Dominance check ────────────────────────────────────────────────────
    if sent_weights and len(sent_weights) == len(subjects):
        # Weighted by actual sent volume
        total_w = sum(sent_weights)
        sent_by: dict[str, int] = {}
        for s, w in zip(subjects, sent_weights):
            sent_by[s] = sent_by.get(s, 0) + w
        top_s  = max(sent_by, key=sent_by.get)
        top_w  = sent_by[top_s]
        if total_w > 0 and top_w / total_w >= 0.85:
            return (top_s, False)
        # Representative for wording
        most_common_text = top_s
    else:
        counter = _Counter(subjects)
        most_common_text, top_cnt = counter.most_common(1)[0]
        if top_cnt / len(subjects) >= 0.85:
            return (most_common_text, False)

    distinct_subjects = list(dict.fromkeys(subjects))  # dedup, preserve order
    n_distinct = len(distinct_subjects)

    # ── 2. All single words → first names ─────────────────────────────────────
    if all(len(s.split()) == 1 for s in distinct_subjects):
        return ("[first name]", True)

    # ── 3. Majority word-level prefix + suffix (≥75% of distinct subjects) ────
    word_lists = [s.split() for s in distinct_subjects]
    min_words  = min(len(w) for w in word_lists)
    MAJORITY   = 0.75

    # Use 75th-percentile min length for suffix detection so a single short
    # outlier (e.g. bare "one spot open" in a cluster of "X — one spot open")
    # doesn't limit how far we can look back from the end.
    _wlens = sorted(len(w) for w in word_lists)
    majority_min = _wlens[max(0, int(len(_wlens) * 0.25))]

    prefix_words: list[str] = []
    for i in range(min_words):
        vals    = [w[i].lower().rstrip(",.!?—–-'\x27") for w in word_lists]
        ctr     = _Counter(vals)
        top_v, top_c = ctr.most_common(1)[0]
        if top_c / n_distinct >= MAJORITY:
            prefix_words.append(word_lists[0][i])   # keep original casing
        else:
            break
    prefix_len = len(prefix_words)

    suffix_words: list[str] = []
    for i in range(1, majority_min - prefix_len + 1):
        # Only consider subjects long enough to have this position
        long_enough = [w for w in word_lists if len(w) >= prefix_len + i]
        if len(long_enough) / n_distinct < MAJORITY:
            break  # too many subjects are too short — stop here
        vals = [w[-i].lower().rstrip(",.!?—–-'\x27") for w in long_enough]
        ctr  = _Counter(vals)
        top_v, top_c = ctr.most_common(1)[0]
        if top_c / n_distinct >= MAJORITY:
            # Take the suffix word from the first subject long enough to have it
            suffix_words.insert(0, long_enough[0][-i])
        else:
            break
    suffix_len = len(suffix_words)

    prefix_str = " ".join(prefix_words)
    suffix_str = " ".join(suffix_words)

    # ── 4. Classify the varying middle ────────────────────────────────────────
    varying_samples: list[str] = []
    for s in distinct_subjects[:40]:
        w     = s.split()
        start = prefix_len
        end   = len(w) - suffix_len if suffix_len > 0 else len(w)
        if start < end and end > 0:
            varying_samples.append(" ".join(w[start:end]))

    if not varying_samples:
        # Prefix + suffix cover everything → static
        return (most_common_text, False)

    avg_word_count = sum(len(v.split()) for v in varying_samples) / len(varying_samples)

    # Possessive: company names ending with 's or ' (ASCII apostrophe 0x27)
    # NOTE: use explicit \x27 (ASCII apostrophe) — curly quotes differ in DB
    possessive_count = sum(
        1 for v in varying_samples
        if v.rstrip().endswith("\x27s") or v.rstrip().endswith("\x27")
    )
    has_possessive = possessive_count / len(varying_samples) >= 0.50

    # Industry keywords present in varying samples
    industry_hits = sum(
        1 for v in varying_samples
        if any(kw in v.lower() for kw in _INDUSTRY_KW)
    )
    looks_like_industry = industry_hits / len(varying_samples) >= 0.40

    # Multi-word check (rules out first-name scenarios)
    has_multiword = any(len(v.split()) > 1 for v in varying_samples)

    if avg_word_count <= 1.2 and not has_multiword:
        placeholder      = "first name"
        possessive_token = ""
    elif has_possessive:
        placeholder      = "company"
        possessive_token = "\x27s"    # ASCII apostrophe + s
    elif looks_like_industry:
        placeholder      = "industry"
        possessive_token = ""
    else:
        placeholder      = "company"
        possessive_token = ""

    placeholder_token = f"[{placeholder}]{possessive_token}"

    parts: list[str] = []
    if prefix_str:
        parts.append(prefix_str)
    parts.append(placeholder_token)
    if suffix_str:
        parts.append(suffix_str)
    return (" ".join(parts), True)


def _build_template_rows(
    all_rows: list,     # sqlite3.Row objects: subject_line, variant_id, sl_queue,
                        #   cs_in_queue, cs_delivered, opened, replied, booked
    min_sent: int,
) -> list[SubjectLineStats]:
    """Build one SubjectLineStats row per (variant × template cluster).

    Steps:
    1. Proportionally scale each subject’s "sent" count via campaign_stats so
       variant totals match SmartLead’s delivered count.
    2. Within each variant, cluster subjects by 2-word (or 1-word when noisy)
       structural key.
    3. For each cluster: if one subject dominates by sent volume (≥85%) →
       static row; otherwise → infer template with [brackets].
    4. Return rows sorted by open rate descending.
    """
    from collections import Counter as _Counter, defaultdict as _defaultdict
    import re as _re

    def _scale(sl_queue: int, cs_q: int, cs_del: int) -> int:
        if cs_q > 0 and cs_del > 0:
            return round(sl_queue / cs_q * cs_del)
        return sl_queue

    # Each DB row is one distinct (subject_line, variant_id) pair
    # (subject, variant_id, sent_scaled, opened, replied, booked)
    expanded: list[tuple[str, str, int, int, int, int]] = []
    for r in all_rows:
        sent = _scale(r["sl_queue"] or 0, r["cs_in_queue"] or 0, r["cs_delivered"] or 0)
        expanded.append((
            r["subject_line"], r["variant_id"],
            sent, r["opened"] or 0, r["replied"] or 0, r["booked"] or 0,
        ))

    by_variant: dict[str, list] = _defaultdict(list)
    for item in expanded:
        by_variant[item[1]].append(item)

    result: list[SubjectLineStats] = []

    for vid, items in sorted(by_variant.items()):
        subjects = [item[0] for item in items]

        # Decide 1-word vs 2-word clustering.
        # When 2-word keys are too fragmented (top key < 20% of subjects AND
        # distinct keys > 50% of subject count) fall back to 1-word so that
        # variants like V1 — "saw waverly…", "saw west cary…" — collapse into
        # one "saw" cluster instead of hundreds of singletons.
        key2_ctr = _Counter(_subject_cluster_key(s) for s in subjects)
        top_k2, top_k2_cnt = key2_ctr.most_common(1)[0] if key2_ctr else ("", 0)
        use_1word = (
            top_k2_cnt / len(subjects) < 0.20
            and len(key2_ctr) > len(subjects) * 0.50
        )

        def _key(s: str) -> str:
            if len(s.split()) == 1:
                return "__single__"
            if use_1word:
                return _re.sub(r"[^a-z0-9]", "", s.lower().split()[0])
            return _subject_cluster_key(s)

        cluster_items: dict[str, list] = _defaultdict(list)
        for item in items:
            cluster_items[_key(item[0])].append(item)

        for _ck, c_items in cluster_items.items():
            c_subjects   = [x[0] for x in c_items]
            c_weights    = [x[2] for x in c_items]   # scaled sent per distinct subject
            total_sent   = sum(c_weights)
            total_open   = sum(x[3] for x in c_items)
            total_reply  = sum(x[4] for x in c_items)
            total_book   = sum(x[5] for x in c_items)

            if total_sent < min_sent:
                continue

            template, is_pers = _infer_template(c_subjects, c_weights)
            if not template:
                continue

            result.append(SubjectLineStats(
                subject_line=template,
                variant_id=vid,
                sent=total_sent,
                opened=total_open,
                replied=total_reply,
                booked=total_book,
                is_grouped=is_pers,
            ))

    result.sort(key=lambda x: x.open_rate, reverse=True)
    return result


def subject_line_stats(db_path: Path, min_sent: int = 3) -> list[SubjectLineStats]:
    """Per-subject-line performance. Groups the actual sent subject text (not formula).
    Shows open rate and reply rate so you can A/B the subject lines directly.
    Only returns rows with at least `min_sent` sends to avoid noise.

    Priority 1 — per-lead events exist (populated by SmartLead sync):
        opened/replied come directly from the events table — each subject line
        gets its own MEASURED open/reply count, not a proportional estimate.
        sent is proportionally scaled from campaign_stats.delivered so the total
        matches SmartLead's delivered count rather than the queue count.

    Priority 2 — campaign_stats exist, no per-lead events yet:
        Distributes campaign-level open/reply rates proportionally across subject
        lines within each variant.  Every subject line in the same variant will
        show the same rate — this is the honest "no per-lead data yet" view.

    Priority 3 — nothing synced:
        Falls back to raw per-lead events (queue counts, real engagement if any).
    """
    conn = _connect(db_path)

    # Check what data is available
    try:
        cs_count = conn.execute(
            "SELECT COUNT(*) FROM campaign_stats WHERE variant_id LIKE 'Variant%'"
        ).fetchone()[0]
    except Exception:
        cs_count = 0

    try:
        event_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type IN ('opened', 'replied')"
        ).fetchone()[0]
    except Exception:
        event_count = 0

    cur = conn.cursor()

    # ── Path 1: Per-lead events — true per-subject-line rates ────────────────
    # opened/replied come directly from the events table (real per-lead counts).
    # sent is proportionally scaled via campaign_stats so totals match SmartLead.
    #
    # Subjects are clustered by structural template within each variant so the
    # table shows one row per template (e.g. "quick question, [first name]")
    # rather than one row per individual personalised value.
    if event_count > 0 and cs_count > 0:
        cur.execute(
            """
            SELECT
                l.subject_line,
                COALESCE(l.variant_id, 'unknown')    AS variant_id,
                COUNT(DISTINCT l.lead_id)             AS sl_queue,
                MAX(COALESCE(cs.in_queue,  0))        AS cs_in_queue,
                MAX(COALESCE(cs.delivered, 0))        AS cs_delivered,
                SUM(CASE WHEN e.event_type = 'opened'      THEN 1 ELSE 0 END) AS opened,
                SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
                SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
            FROM leads l
            LEFT JOIN campaign_stats cs ON cs.variant_id = l.variant_id
            LEFT JOIN events e ON e.lead_id = l.lead_id
            WHERE l.subject_line IS NOT NULL
              AND l.subject_line != ''
              AND l.status IN ('sent', 'success')
            GROUP BY l.subject_line, l.variant_id
            """
        )
        all_rows = cur.fetchall()
        conn.close()
        return _build_template_rows(all_rows, min_sent)

    # ── Path 2: Campaign-stats only — proportional estimates ─────────────────
    # No per-lead events yet.  Every subject line in the same variant will show
    # the same open/reply rate (honest: we only have variant-level totals).
    if cs_count > 0:
        cur.execute(
            """
            SELECT
                l.subject_line,
                COALESCE(l.variant_id, 'unknown')   AS variant_id,
                COUNT(DISTINCT l.lead_id)            AS sl_queue,
                MAX(COALESCE(cs.in_queue,  0))       AS cs_in_queue,
                MAX(COALESCE(cs.delivered, 0))       AS cs_delivered,
                MAX(COALESCE(cs.opened,    0))       AS cs_opened,
                MAX(COALESCE(cs.replied,   0))       AS cs_replied
            FROM leads l
            LEFT JOIN campaign_stats cs ON cs.variant_id = l.variant_id
            WHERE l.subject_line IS NOT NULL
              AND l.subject_line != ''
              AND l.status IN ('sent', 'success')
            GROUP BY l.subject_line, l.variant_id
            HAVING sl_queue >= 1
            """
        )
        rows = cur.fetchall()
        conn.close()

        result2: list[SubjectLineStats] = []
        for r in rows:
            sl_queue     = r["sl_queue"]      or 0
            cs_in_queue  = r["cs_in_queue"]   or 0
            cs_delivered = r["cs_delivered"]  or 0
            cs_opened    = r["cs_opened"]     or 0
            cs_replied   = r["cs_replied"]    or 0

            if cs_in_queue > 0 and cs_delivered > 0:
                sl_delivered = round(sl_queue / cs_in_queue * cs_delivered)
                open_rate    = cs_opened  / cs_delivered
                reply_rate   = cs_replied / cs_delivered
                opened       = round(sl_delivered * open_rate)
                replied      = round(sl_delivered * reply_rate)
            elif cs_in_queue > 0:
                sl_delivered = sl_queue
                opened       = 0
                replied      = 0
            else:
                sl_delivered = 0
                opened       = 0
                replied      = 0

            if sl_delivered < min_sent:
                continue

            result2.append(SubjectLineStats(
                subject_line=r["subject_line"],
                variant_id=r["variant_id"],
                sent=sl_delivered,
                opened=opened,
                replied=replied,
                booked=0,
            ))

        result2.sort(key=lambda x: x.open_rate, reverse=True)
        return result2

    # ── Path 3: No campaign_stats — raw per-lead events ──────────────────────
    cur.execute(
        """
        SELECT
            l.subject_line,
            COALESCE(l.variant_id, 'unknown') AS variant_id,
            COUNT(DISTINCT l.lead_id) AS sent,
            SUM(CASE WHEN e.event_type = 'opened'      THEN 1 ELSE 0 END) AS opened,
            SUM(CASE WHEN e.event_type = 'replied'     THEN 1 ELSE 0 END) AS replied,
            SUM(CASE WHEN e.event_type = 'booked_call' THEN 1 ELSE 0 END) AS booked
        FROM leads l
        LEFT JOIN events e ON e.lead_id = l.lead_id
        WHERE l.subject_line IS NOT NULL
          AND l.subject_line != ''
          AND l.status IN ('sent', 'success')
        GROUP BY l.subject_line, l.variant_id
        HAVING sent >= ?
        ORDER BY replied DESC, opened DESC
        """,
        (min_sent,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        SubjectLineStats(
            subject_line=r["subject_line"],
            variant_id=r["variant_id"],
            sent=r["sent"] or 0,
            opened=r["opened"] or 0,
            replied=r["replied"] or 0,
            booked=r["booked"] or 0,
        )
        for r in rows
    ]


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
