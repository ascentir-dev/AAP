"""Tests for src/enrichment/linkedin.py — Apify client mocked."""
from unittest.mock import MagicMock, patch

import pytest

from src.enrichment.linkedin import enrich_linkedin


def make_settings(token: str = "fake-token", actor: str = "curious_coder/linkedin-profile-scraper"):
    s = MagicMock()
    s.apify_api_token = token
    s.apify_linkedin_actor = actor
    return s


def make_cost_tracker():
    ct = MagicMock()
    ct.log = MagicMock()
    return ct


def make_apify_client(profile_data: dict):
    """Build a mock ApifyClient that returns one profile item."""
    dataset = MagicMock()
    dataset.iterate_items.return_value = iter([profile_data])

    actor_mock = MagicMock()
    actor_mock.call.return_value = {"defaultDatasetId": "ds-123"}

    client = MagicMock()
    client.actor.return_value = actor_mock
    client.dataset.return_value = dataset
    return client


@pytest.mark.asyncio
async def test_returns_expected_shape():
    profile = {
        "headline": "VP of Sales at Acme",
        "jobTitle": "VP of Sales",
        "summary": "10 years in B2B sales",
        "recentPost": "Just closed a big deal",
        "companySize": "500-1000",
    }
    mock_client = make_apify_client(profile)
    settings = make_settings()
    ct = make_cost_tracker()

    with patch("src.enrichment.linkedin.ApifyClient", return_value=mock_client):
        result = await enrich_linkedin("https://linkedin.com/in/alice", settings, ct)

    assert result["headline"] == "VP of Sales at Acme"
    assert result["current_role"] == "VP of Sales"
    assert result["about"] == "10 years in B2B sales"
    assert result["recent_post"] == "Just closed a big deal"
    assert result["company_size"] == "500-1000"


@pytest.mark.asyncio
async def test_cost_is_logged():
    profile = {"headline": "CTO", "jobTitle": "CTO", "summary": "", "recentPost": "", "companySize": ""}
    mock_client = make_apify_client(profile)
    settings = make_settings()
    ct = make_cost_tracker()

    with patch("src.enrichment.linkedin.ApifyClient", return_value=mock_client):
        await enrich_linkedin("https://linkedin.com/in/bob", settings, ct)

    ct.log.assert_called_once()
    call_args = ct.log.call_args[0]
    assert call_args[1] == "apify"
    assert call_args[3] == pytest.approx(0.008)


@pytest.mark.asyncio
async def test_returns_empty_dict_on_failure():
    settings = make_settings()
    ct = make_cost_tracker()

    with patch("src.enrichment.linkedin.ApifyClient", side_effect=Exception("API down")):
        result = await enrich_linkedin("https://linkedin.com/in/error", settings, ct)

    assert result == {}
    ct.log.assert_not_called()


@pytest.mark.asyncio
async def test_returns_empty_dict_when_no_url():
    settings = make_settings()
    ct = make_cost_tracker()

    result = await enrich_linkedin("", settings, ct)
    assert result == {}
    ct.log.assert_not_called()


@pytest.mark.asyncio
async def test_returns_empty_dict_when_no_token():
    settings = make_settings(token="")
    ct = make_cost_tracker()

    result = await enrich_linkedin("https://linkedin.com/in/alice", settings, ct)
    assert result == {}
    ct.log.assert_not_called()
