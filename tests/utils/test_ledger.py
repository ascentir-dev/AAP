"""Tests for src/utils/ledger.py"""
import tempfile
from datetime import datetime

import pytest
from src.utils.ledger import Ledger


@pytest.fixture
def ledger():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    db = Ledger(path)
    yield db
    db.close()


def test_save_and_read_stage(ledger):
    data = {"key": "value", "number": 42, "nested": {"a": 1}}
    ledger.save_stage("lead-001", "enrichment", data)
    assert ledger.has_stage("lead-001", "enrichment")
    result = ledger.get_stage("lead-001", "enrichment")
    assert result == data


def test_has_stage_returns_false_when_missing(ledger):
    assert not ledger.has_stage("lead-002", "analysis")


def test_get_stage_returns_none_when_missing(ledger):
    assert ledger.get_stage("lead-003", "email") is None


def test_save_stage_overwrites(ledger):
    ledger.save_stage("lead-004", "analysis", {"v": 1})
    ledger.save_stage("lead-004", "analysis", {"v": 2})
    result = ledger.get_stage("lead-004", "analysis")
    assert result == {"v": 2}


def test_save_lead_metadata_with_variant_and_framework(ledger):
    ledger.save_lead_metadata(
        "lead-005",
        email="test@example.com",
        variant_id="Variant 3",
        framework="AIDA",
        motion="sales_led_outbound",
        vertical="B2B SaaS",
    )
    # Verify we can look it up by email
    found = ledger.lead_id_for_email("test@example.com")
    assert found == "lead-005"


def test_mark_complete_and_is_complete(ledger):
    # Must have a leads row first
    ledger.save_lead_metadata("lead-006", email="a@b.com")
    ledger.mark_complete("lead-006", status="sent")
    assert ledger.is_complete("lead-006")


def test_mark_failed(ledger):
    ledger.save_lead_metadata("lead-007", email="c@d.com")
    ledger.mark_failed("lead-007", "playwright timeout")
    # failed leads are NOT "complete" in pipeline terms
    assert not ledger.is_complete("lead-007")


def test_record_event(ledger):
    ledger.save_lead_metadata("lead-008", email="ev@test.com")
    ledger.record_event(
        lead_id="lead-008",
        event_type="email_opened",
        occurred_at=datetime(2026, 5, 9, 10, 0, 0),
        smartlead_payload={"campaign_id": "123", "opened": True},
    )
    # No assertion needed on read-back (queries module isn't built yet),
    # just verify it doesn't raise
    assert True


def test_lead_id_for_email_returns_none_when_not_found(ledger):
    result = ledger.lead_id_for_email("nobody@example.com")
    assert result is None


def test_is_complete_returns_false_for_unknown_lead(ledger):
    assert not ledger.is_complete("nonexistent-lead")
