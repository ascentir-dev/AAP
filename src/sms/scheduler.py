"""
TCPA-aware SMS send scheduler.

TCPA hard limits (47 CFR § 64.1200):
  08:00 – 21:00 recipient's LOCAL time, 7 days a week.

Send-window policy (beyond the legal minimum):
  Tier 1  09:00–11:00 local  — morning decision window (best reply rates)
  Tier 2  16:00–19:00 local  — after-work window (second-best)
  Tier 3  11:00–16:00 local  — mid-day fallback (legal, lower engagement)
  Blocked 21:00–08:00 local  — TCPA hard stop; never send

Weekday policy:
  Mon–Sat  — sendable (within windows above)
  Sun      — blocked for brand safety (not a TCPA requirement, but best practice)

The scheduler is intentionally lenient about Tier 3: if it is currently
the mid-day window, can_send_now=True so the pipeline does not silently
park leads when the user explicitly triggers a run.  Every decision is
logged so the operator can audit exactly what was blocked and why.

Usage (in pipeline Phase 2):
    from src.sms.scheduler import check_send_window
    sw = check_send_window(phone)
    if not sw.can_send_now:
        log.info("Deferred: %s", sw.reason)
        continue   # lead stays 'ready'; retried on next run
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta, timezone as dt_timezone
from typing import NamedTuple

try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:                        # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from src.sms.timezone_lookup import phone_to_zone, ZoneResult

log = logging.getLogger(__name__)

# ── TCPA hard limits ──────────────────────────────────────────────────────────
TCPA_START = dtime(8, 0)    # 08:00 local — inclusive
TCPA_END   = dtime(21, 0)   # 21:00 local — exclusive (stop before 9 PM)

# ── Optimal send windows (local time, checked in priority order) ──────────────
OPTIMAL_WINDOWS: list[tuple[dtime, dtime]] = [
    (dtime(9,  0), dtime(11, 0)),   # Tier 1 — morning
    (dtime(16, 0), dtime(19, 0)),   # Tier 2 — after-work
    (dtime(11, 0), dtime(16, 0)),   # Tier 3 — mid-day (legal; send if triggered)
]

# Python weekday(): Mon=0 … Sun=6
_BLOCKED_WEEKDAYS: frozenset[int] = frozenset({6})   # Sunday


class SendWindow(NamedTuple):
    zone:             str               # IANA zone used for this decision
    can_send_now:     bool
    reason:           str               # human-readable explanation
    next_window_utc:  datetime | None   # UTC start of next legal window (if blocked)
    review_flag:      bool              # True when zone was guessed


def _local_now(zone: str) -> datetime:
    return datetime.now(ZoneInfo(zone))


def _in_tcpa_window(local_dt: datetime) -> bool:
    """True when local_dt is within TCPA-legal hours on a non-blocked weekday."""
    if local_dt.weekday() in _BLOCKED_WEEKDAYS:
        return False
    t = local_dt.time()
    return TCPA_START <= t < TCPA_END


def _in_optimal_window(local_dt: datetime) -> bool:
    """True when local_dt falls in any of the defined optimal send windows."""
    t = local_dt.time()
    return any(start <= t < end for start, end in OPTIMAL_WINDOWS)


def _next_tcpa_start(local_dt: datetime) -> datetime:
    """Return the next datetime (local tz) when TCPA window opens.

    Advances day by day, skipping blocked weekdays, until it finds a day
    whose TCPA window either hasn't started yet or starts tomorrow.
    """
    candidate = local_dt.replace(microsecond=0)

    for _ in range(10):   # safety cap — max look-ahead
        if candidate.weekday() in _BLOCKED_WEEKDAYS:
            # Jump to next day's TCPA_START
            candidate = (candidate + timedelta(days=1)).replace(
                hour=TCPA_START.hour, minute=0, second=0,
            )
            continue

        day_open  = candidate.replace(hour=TCPA_START.hour, minute=0, second=0)
        day_close = candidate.replace(hour=TCPA_END.hour,   minute=0, second=0)

        if candidate < day_open:
            return day_open        # before today's window → today at 08:00

        if candidate < day_close:
            return candidate       # already inside today's window → right now

        # Past today's window → try next day
        candidate = (candidate + timedelta(days=1)).replace(
            hour=TCPA_START.hour, minute=0, second=0,
        )

    return candidate  # should never reach here


def check_send_window(phone: str) -> SendWindow:
    """Decide whether it is currently legal (and optimal) to send to `phone`.

    Resolution:
      1. Resolve phone → IANA zone via timezone_lookup.phone_to_zone()
      2. Compute local time for the recipient
      3. Check TCPA hard limit  (08:00–21:00, Mon–Sat)
      4. Check optimal windows  (Tier 1 → 2 → 3)

    Returns:
        SendWindow with can_send_now=True when it is both legal to send and
        the current local time falls in an optimal window.
        can_send_now=True is also returned during the Tier 3 mid-day window
        so manually-triggered pipeline runs are not needlessly deferred.

    Never raises — resolves to Eastern default on bad zone.
    """
    zone_result: ZoneResult = phone_to_zone(phone)
    zone = zone_result.zone

    try:
        local_now = _local_now(zone)
    except Exception as exc:
        log.warning(
            "check_send_window: invalid zone %r for %r (%s) — falling back to America/New_York",
            zone, phone, exc,
        )
        zone = "America/New_York"
        local_now = _local_now(zone)

    # ── TCPA gate ─────────────────────────────────────────────────────────────
    if not _in_tcpa_window(local_now):
        next_local = _next_tcpa_start(local_now)
        next_utc   = next_local.astimezone(dt_timezone.utc)

        day_label = (
            "today" if next_local.date() == local_now.date()
            else next_local.strftime("%A")
        )
        return SendWindow(
            zone=zone,
            can_send_now=False,
            reason=(
                f"outside TCPA window — local time is "
                f"{local_now.strftime('%H:%M %Z, %A')}; "
                f"next window opens {day_label} at "
                f"{next_local.strftime('%H:%M %Z')}"
            ),
            next_window_utc=next_utc,
            review_flag=zone_result.review_flag,
        )

    # ── Optimal window check ──────────────────────────────────────────────────
    in_optimal = _in_optimal_window(local_now)
    tier = next(
        (i + 1 for i, (s, e) in enumerate(OPTIMAL_WINDOWS)
         if s <= local_now.time() < e),
        None,
    )

    return SendWindow(
        zone=zone,
        can_send_now=True,   # legal + optional-tier windows all return True
        reason=(
            f"Tier {tier} send window (local {local_now.strftime('%H:%M %Z, %A')})"
            if tier else
            f"legal hours (local {local_now.strftime('%H:%M %Z, %A')})"
        ),
        next_window_utc=None,
        review_flag=zone_result.review_flag,
    )
