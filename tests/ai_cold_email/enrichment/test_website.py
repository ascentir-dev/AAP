"""Tests for src/enrichment/website.py — Playwright fully mocked."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.enrichment.website as website_module
from src.enrichment.website import scrape_website


@pytest.fixture(autouse=True)
def clear_domain_cache():
    """Clear the in-process domain cache before every test."""
    website_module._DOMAIN_CACHE.clear()
    yield
    website_module._DOMAIN_CACHE.clear()


def make_settings(max_chars: int = 3500):
    s = MagicMock()
    s.enrichment = {"website": {"max_text_chars_per_page": max_chars}}
    return s


def make_page_mock(
    title: str = "Acme Corp",
    meta: str = "We build great software",
    body_text: str = "Welcome to Acme. We are awesome.",
    hrefs: list = None,
):
    page = AsyncMock()
    page.title = AsyncMock(return_value=title)
    page.get_attribute = AsyncMock(return_value=meta)
    page.inner_text = AsyncMock(return_value=body_text)
    page.goto = AsyncMock()
    page.route = AsyncMock()   # new: block media resources
    page.evaluate = AsyncMock(return_value=hrefs or [])
    page.close = AsyncMock()
    return page


def make_pw_harness(page):
    """Build the full Playwright async context-manager harness."""
    browser = AsyncMock()
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser.new_context = AsyncMock(return_value=context)

    pw_instance = AsyncMock()
    pw_instance.chromium.launch = AsyncMock(return_value=browser)
    pw_instance.__aenter__ = AsyncMock(return_value=pw_instance)
    pw_instance.__aexit__ = AsyncMock(return_value=False)
    return pw_instance


@pytest.mark.asyncio
async def test_output_shape():
    """scrape_website returns all required keys."""
    page = make_page_mock()

    with patch("src.enrichment.website.async_playwright", return_value=make_pw_harness(page)):
        result = await scrape_website("https://acme-shape.com", make_settings())

    assert "homepage_text" in result
    assert "about_text" in result
    assert "product_text" in result
    assert "title" in result
    assert "meta_description" in result


@pytest.mark.asyncio
async def test_homepage_text_is_capped():
    page = make_page_mock(body_text="A" * 20_000)

    with patch("src.enrichment.website.async_playwright", return_value=make_pw_harness(page)):
        result = await scrape_website("https://acme-cap.com", make_settings(max_chars=8000))

    assert len(result["homepage_text"]) <= 8000


@pytest.mark.asyncio
async def test_default_char_cap_is_3500():
    """Default max_chars_per_page should now be 3500 (was 8000)."""
    page = make_page_mock(body_text="X" * 10_000)

    with patch("src.enrichment.website.async_playwright", return_value=make_pw_harness(page)):
        result = await scrape_website("https://acme-cap2.com", make_settings(max_chars=3500))

    assert len(result["homepage_text"]) <= 3500


@pytest.mark.asyncio
async def test_title_and_meta_captured():
    page = make_page_mock(title="My SaaS", meta="The best SaaS ever")

    with patch("src.enrichment.website.async_playwright", return_value=make_pw_harness(page)):
        result = await scrape_website("https://myapp-meta.com", make_settings())

    assert result["title"] == "My SaaS"
    assert result["meta_description"] == "The best SaaS ever"


@pytest.mark.asyncio
async def test_domain_cache_hit_skips_playwright():
    """Second call for same domain returns cache — Playwright is not launched again."""
    page = make_page_mock()

    pw_harness = make_pw_harness(page)
    with patch("src.enrichment.website.async_playwright", return_value=pw_harness) as mock_pw:
        await scrape_website("https://cache-test.com", make_settings())   # first call
        result2 = await scrape_website("https://cache-test.com", make_settings())  # cache hit

    # async_playwright called only once (the second call was served from cache)
    assert mock_pw.call_count == 1
    assert "homepage_text" in result2


@pytest.mark.asyncio
async def test_different_domains_not_cached_together():
    """Different domains should make separate Playwright calls."""
    page = make_page_mock()

    with patch("src.enrichment.website.async_playwright", return_value=make_pw_harness(page)) as mock_pw:
        await scrape_website("https://domain-a.com", make_settings())
        await scrape_website("https://domain-b.com", make_settings())

    assert mock_pw.call_count == 2
