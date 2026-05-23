"""
Website scraper. Uses Playwright to extract signal-rich text from a company's
homepage and up to two key sub-pages.

Optimization notes
------------------
* Domain-level in-memory cache (1-hour TTL): scraping the same company twice
  (e.g. multiple leads from Acme Corp) costs zero extra Playwright time.
* Expanded noise-tag removal: script, style, iframe, noscript, aside, plus the
  original nav/footer/header — produces denser signal per token.
* Two-phase page load: try networkidle first (better for JS-heavy sites), fall
  back to domcontentloaded — no silent blank-page failures on dynamic SPAs.
* Default char cap reduced from 8 000 to 3 500 per page (overridable in
  settings.yaml).  Most motion-detection signals appear in the first 700 words;
  the old 8 000-char limit was inflating Haiku input costs by ≈56 %.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

# Tags whose entire subtree is noise — removes rendered JS, styles, and UI chrome
_NOISE_TAGS = (
    "nav", "footer", "header",        # original
    "script", "style", "noscript",    # code / hidden markup
    "iframe", "aside",                # embeds / sidebars
)

_SUB_PAGE_KEYWORDS = ("about", "product", "platform", "solutions", "pricing")

# In-process domain cache: domain → (result, timestamp)
_DOMAIN_CACHE: dict[str, tuple[dict[str, str], float]] = {}
_CACHE_TTL_SECONDS = 3_600  # 1 hour — long enough for a full batch run


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _cache_get(url: str) -> dict[str, str] | None:
    domain = _get_domain(url)
    entry = _DOMAIN_CACHE.get(domain)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        del _DOMAIN_CACHE[domain]
        return None
    log.debug("website cache HIT for domain %s", domain)
    return result


def _cache_set(url: str, result: dict[str, str]) -> None:
    _DOMAIN_CACHE[_get_domain(url)] = (result, time.monotonic())


def _cap(text: str, max_chars: int) -> str:
    return text[:max_chars] if len(text) > max_chars else text


async def _goto_with_fallback(page: Any, url: str, timeout_ms: int) -> None:
    """Navigate with networkidle (better JS rendering), fall back to domcontentloaded."""
    try:
        await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
    except Exception:
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        except Exception as e:
            log.debug("page.goto failed for %s: %s", url, e)
            raise


async def _page_text(page: Any, max_chars: int) -> str:
    """Strip all noise elements, then return visible body text."""
    try:
        # Single JS eval removes all noise tags in one round-trip
        tags_js = ", ".join(f"'{t}'" for t in _NOISE_TAGS)
        await page.evaluate(
            f"[{tags_js}].forEach(tag => "
            f"document.querySelectorAll(tag).forEach(el => el.remove()))"
        )
    except Exception:
        pass

    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""

    # Collapse excessive whitespace while preserving paragraph breaks
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return _cap(text.strip(), max_chars)


async def _find_sub_page_links(page: Any, _base_url: str) -> list[str]:
    """Return hrefs of <a> tags whose path contains any sub-page keyword."""
    try:
        hrefs = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
        )
    except Exception:
        return []

    seen: set[str] = set()
    results: list[str] = []
    for href in hrefs:
        if not isinstance(href, str):
            continue
        href = href.split("#")[0].rstrip("/")
        if not href.startswith("http"):
            continue
        if href in seen:
            continue
        if any(kw in href.lower() for kw in _SUB_PAGE_KEYWORDS):
            seen.add(href)
            results.append(href)
        if len(results) >= 2:
            break
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def scrape_website(url: str, settings: Any) -> dict[str, str]:
    """Scrape homepage + up to 2 sub-pages.  Returns structured text dict.

    Results are cached per domain for 1 hour so repeat calls (multiple leads
    from the same company) are free.
    """
    cached = _cache_get(url)
    if cached is not None:
        return cached

    max_chars: int = (
        settings.enrichment.get("website", {}).get("max_text_chars_per_page", 3_500)
        if isinstance(settings.enrichment, dict)
        else 3_500
    )

    result: dict[str, str] = {
        "homepage_text": "",
        "about_text": "",
        "product_text": "",
        "title": "",
        "meta_description": "",
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            # Disable images/fonts: faster load, no effect on text extraction
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        try:
            page = await context.new_page()

            # Block heavy media to speed up page load
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
                lambda route: route.abort(),
            )

            await _goto_with_fallback(page, url, timeout_ms=15_000)

            result["title"] = await page.title()
            try:
                meta = await page.get_attribute('meta[name="description"]', "content")
                result["meta_description"] = meta or ""
            except Exception:
                pass

            result["homepage_text"] = await _page_text(page, max_chars)

            sub_links = await _find_sub_page_links(page, url)
            sub_texts: dict[str, str] = {"about": "", "product": ""}

            for link in sub_links:
                try:
                    sub_page = await context.new_page()
                    await sub_page.route(
                        "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
                        lambda route: route.abort(),
                    )
                    await _goto_with_fallback(sub_page, link, timeout_ms=12_000)
                    text = await _page_text(sub_page, max_chars)
                    await sub_page.close()
                    if any(kw in link.lower() for kw in ("about",)):
                        sub_texts["about"] = text
                    else:
                        sub_texts["product"] = text
                except Exception as e:
                    log.debug("Failed fetching sub-page %s: %s", link, e)

            result["about_text"] = sub_texts["about"]
            result["product_text"] = sub_texts["product"]

        finally:
            await browser.close()

    _cache_set(url, result)
    return result
