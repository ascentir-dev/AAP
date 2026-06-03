"""
Email preview tool — generates real emails for the two test leads using the
live Claude pipeline and sends both to frankfrederico@ascentir.io via Smartlead.

  Lead 1: Jordan Mitchell @ Disruptive Advertising  → VIDEO email
  Lead 2: Rachel Torres  @ Amy Porterfield          → EMAIL-ONLY

Run:
    cd "/Users/frankfrederico/Desktop/Agentic Acquisition Platform"
    python3 tools/send_preview.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.csv_reader import read_leads
from src.enrichment.website import get_website_data
from src.enrichment.linkedin import get_linkedin_data
from src.analysis.fit_analyzer import analyze_fit
from src.ai_cold_email.email.generator import generate_email
from src.ai_cold_email.orchestrator.pipeline import _market_cta_term
from src.ai_cold_email.smartlead.client import push_to_smartlead
from src.utils.settings import Settings
from src.utils.cost_tracker import CostTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PREVIEW_TO   = "frankfrederico@ascentir.io"
TEST_CSV     = Path("data/input/test_leads.csv")
CALENDLY_URL = "https://calendly.com/aigenture/get-a-i-demo"

# ── CTA blocks ────────────────────────────────────────────────────────────��───

def _video_placeholder(company: str, website: str) -> str:
    """Styled mock thumbnail so the video email looks exactly right in the inbox."""
    domain = website.replace("https://", "").replace("http://", "").rstrip("/")
    return (
        '<table cellpadding="0" cellspacing="0" border="0" style="margin:20px 0;">'
        f'<tr><td style="background:#0f0f1a;border-radius:8px;width:560px;height:300px;'
        f'text-align:center;vertical-align:middle;border:1px solid #2a2a3a;">'
        f'<div style="color:#ffffff;font-family:Arial,sans-serif;">'
        f'<div style="font-size:52px;margin-bottom:10px;line-height:1;">&#9654;</div>'
        f'<div style="font-size:13px;color:#aaaaaa;letter-spacing:0.5px;">'
        f'{domain} &nbsp;&#183;&nbsp; 0:55</div>'
        f'</div></td></tr></table>'
        f'<p style="margin:0 0 4px 0;font-family:Arial,sans-serif;font-size:11px;'
        f'color:#aaaaaa;font-style:italic;">'
        f'&#9432; Preview only: live email shows a real screenshot of {domain} '
        f'with a play button. Clicking opens the landing page with the full video.</p>'
    )


def _dual_cta(company: str, market: str = "") -> str:
    """Reply-only CTA for email-only leads — no external links for deliverability.

    Uses market-appropriate vocabulary (Kennedy: market vocabulary is non-negotiable)
    and states exactly what the demo shows + pre-empts friction with 'No call, no pitch.'
    """
    cta_term = _market_cta_term(market)
    return (
        f'<p style="margin:20px 0;font-family:Arial,sans-serif;font-size:14px;'
        f'color:#1a1a1a;line-height:1.6;">'
        f'Reply <strong>AI DEMO</strong> &#8212; I&#8217;ll send a 60-second demo showing '
        f'exactly how the system books {company} 30 {cta_term} in 30 days. '
        f'No call, no pitch. Just the demo.'
        f'</p>'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

async def generate_preview(
    lead: dict,
    email_type: str,   # "video" | "email_only"
    settings: Settings,
    cost_tracker: CostTracker,
) -> tuple[str, str]:
    """Return (subject, html_body) for the given lead."""

    log.info(f"Enriching {lead['first_name']} @ {lead['company']} …")
    website_data  = await get_website_data(lead, settings)
    linkedin_data = await get_linkedin_data(lead, settings, cost_tracker)
    enrichment    = {"website": website_data, "linkedin": linkedin_data}

    log.info(f"Analysing fit …")
    analysis = await analyze_fit(lead, enrichment, settings, cost_tracker)
    if analysis.get("market"):
        lead["market"] = analysis["market"]

    log.info(f"Generating email with Claude …")
    variant_arm = {
        "id": "Variant 1",
        "test_id": "framework_tournament_v1",
        "smartlead_campaign_id": settings.smartlead_campaign_id,
        "overrides": {
            "email_template_id": "v1_3c_berman",
            "variant_framework": "3C (Berman) — Compliment + Case Study + CTA",
        },
    }
    email = await generate_email(lead, analysis, variant_arm, settings, cost_tracker)

    # Replace {VIDEO_LINK} with the right block
    market = lead.get("market", "") or analysis.get("market", "")
    if email_type == "video":
        cta_block = _video_placeholder(lead["company"], lead.get("website", ""))
        tag = "[PREVIEW — VIDEO EMAIL] "
    else:
        cta_block = _dual_cta(lead["company"], market)
        tag = "[PREVIEW — EMAIL-ONLY] "

    body = email["body"].replace("{VIDEO_LINK}", cta_block)

    # Wrap in a clean HTML envelope so it renders properly in the inbox
    html = f"""\
<html><body style="font-family:Arial,sans-serif;font-size:15px;
line-height:1.6;color:#1a1a1a;max-width:600px;margin:0 auto;padding:20px;">
{body.replace(chr(10), "<br>")}
</body></html>"""

    subject = tag + email["subject"]
    return subject, html


async def main() -> None:
    settings     = Settings()
    cost_tracker = CostTracker(daily_budget_usd=5.0)

    leads = read_leads(TEST_CSV)
    if len(leads) < 2:
        log.error("Need at least 2 leads in data/input/test_leads.csv")
        sys.exit(1)

    # Lead 0 → VIDEO,      Lead 1 → EMAIL-ONLY
    pairs = [
        (leads[0], "video"),
        (leads[1], "email_only"),
    ]

    for lead, email_type in pairs:
        log.info("")
        log.info(f"{'─'*60}")
        log.info(f"  {email_type.upper():12s}  {lead['first_name']} @ {lead['company']}")
        log.info(f"{'─'*60}")

        subject, html_body = await generate_preview(lead, email_type, settings, cost_tracker)

        preview_lead = {**lead, "email": PREVIEW_TO}

        log.info(f"Pushing to Smartlead → {PREVIEW_TO}")
        result = await push_to_smartlead(
            lead=preview_lead,
            email_subject=subject,
            email_body=html_body,
            settings=settings,
        )
        log.info(f"Smartlead response: {result}")
        log.info(f"Subject: {subject}")

    log.info("")
    log.info(f"Total generation cost: ${cost_tracker.total():.4f}")
    log.info(f"Both previews queued → {PREVIEW_TO}")
    log.info("Emails send on your Smartlead campaign schedule.")
    log.info("Make sure campaign 3379547 template body = {{{{custom_body}}}} "
             "and subject = {{{{custom_subject}}}}")


if __name__ == "__main__":
    asyncio.run(main())
