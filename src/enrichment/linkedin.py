"""
LinkedIn enrichment via Apify. Returns profile data as a dict.

Graceful degradation: failures return {} and log a warning so the pipeline
never crashes on a missing LinkedIn profile.

Optimization note
-----------------
ApifyClient is a synchronous blocking library.  Running it directly in an
async function would block the entire event loop while the Apify run waits
(typically 10-30s), killing concurrency across the 8 parallel leads.
We push the blocking work onto a thread-pool executor via asyncio.to_thread()
so the event loop stays free for other async tasks.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from apify_client import ApifyClient
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_COST_PER_PROFILE_USD = 0.008


def _fetch_profile_sync(
    linkedin_url: str,
    api_token: str,
    actor: str,
) -> list[dict[str, Any]]:
    """Synchronous Apify call — runs in a thread pool via asyncio.to_thread."""
    client = ApifyClient(api_token)
    run = client.actor(actor).call(run_input={"profileUrls": [linkedin_url]})
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def enrich_linkedin(
    linkedin_url: str,
    settings: Any,
    cost_tracker: Any,
) -> dict[str, str]:
    """Fetch LinkedIn profile data via Apify.  Returns {} on failure.

    The blocking Apify SDK call runs in a thread pool so the event loop is
    not stalled while waiting for the remote Apify actor run.
    """
    if not linkedin_url or not settings.apify_api_token:
        log.debug("Skipping LinkedIn enrichment — no URL or API token")
        return {}

    try:
        items = await asyncio.to_thread(
            _fetch_profile_sync,
            linkedin_url,
            settings.apify_api_token,
            settings.apify_linkedin_actor,
        )

        if not items:
            log.warning("Apify returned no items for %s", linkedin_url)
            return {}

        profile = items[0]
        result = {
            "headline":     str(profile.get("headline", "")),
            "current_role": str(profile.get("jobTitle", profile.get("currentRole", ""))),
            "about":        str(profile.get("summary", profile.get("about", ""))),
            "recent_post":  str(profile.get("recentPost", "")),
            "company_size": str(profile.get("companySize", "")),
        }

        cost_tracker.log(None, "apify", "linkedin_profile", _COST_PER_PROFILE_USD)
        return result

    except Exception as e:
        log.warning("LinkedIn enrichment failed for %s: %s", linkedin_url, e)
        return {}
