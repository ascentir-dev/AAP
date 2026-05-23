"""Tests for src/utils/cost_tracker.py"""
import tempfile

import pytest
from src.utils.cost_tracker import CostTracker


@pytest.fixture
def tracker():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    ct = CostTracker(path=path, daily_budget_usd=10.0)
    yield ct
    ct.close()


def test_log_and_lead_cost(tracker):
    tracker.log("lead-1", "anthropic", "analysis", 0.0006)
    tracker.log("lead-1", "openai", "tts", 0.009)
    total = tracker.lead_cost("lead-1")
    assert abs(total - 0.0096) < 1e-9


def test_log_multiple_leads(tracker):
    tracker.log("lead-A", "anthropic", "email", 0.003)
    tracker.log("lead-B", "apify", "linkedin", 0.008)
    assert abs(tracker.lead_cost("lead-A") - 0.003) < 1e-9
    assert abs(tracker.lead_cost("lead-B") - 0.008) < 1e-9


def test_total_across_all(tracker):
    tracker.log("lead-X", "anthropic", "analysis", 0.001)
    tracker.log("lead-Y", "openai", "tts", 0.002)
    tracker.log(None, "cloudflare", "storage", 0.001)
    assert abs(tracker.total() - 0.004) < 1e-9


def test_daily_total_includes_todays_costs(tracker):
    tracker.log("lead-Z", "anthropic", "script", 0.002)
    assert tracker.daily_total() >= 0.002


def test_check_budget_under_limit(tracker):
    tracker.log("lead-1", "anthropic", "analysis", 0.50)
    assert tracker.check_budget() is True  # 0.50 < 10.0


def test_check_budget_over_limit(tracker):
    tracker.log("lead-1", "anthropic", "big-batch", 11.0)
    assert tracker.check_budget() is False  # 11.0 >= 10.0


def test_lead_cost_zero_for_unknown_lead(tracker):
    assert tracker.lead_cost("nobody") == 0.0
