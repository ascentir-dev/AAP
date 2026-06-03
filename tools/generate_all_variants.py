"""
Generates all 9 email variants for a real lead and prints them exactly
as they would appear when sent to the prospect.

Run:
    cd "/Users/frankfrederico/Desktop/Agentic Acquisition Platform"
    python3 tools/generate_all_variants.py
"""
from __future__ import annotations
import asyncio, logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.csv_reader import read_leads
from src.enrichment.website import get_website_data
from src.enrichment.linkedin import get_linkedin_data
from src.analysis.fit_analyzer import analyze_fit
from src.ai_cold_email.email.generator import generate_email
from src.ai_cold_email.orchestrator.pipeline import _strip_video_references, _market_cta_term
from src.utils.settings import Settings
from src.utils.cost_tracker import CostTracker

logging.basicConfig(level=logging.WARNING)   # suppress noise — we only want the email output

VARIANTS = [
    {"id": "Variant 1", "framework": "PPP — Praise / Picture / Push"},
    {"id": "Variant 2", "framework": "Predictable Revenue — Referral / Right Person"},
    {"id": "Variant 3", "framework": "AIDA — Attention / Interest / Desire / Action"},
    {"id": "Variant 4", "framework": "PAS — Problem / Agitate / Solve"},
    {"id": "Variant 5", "framework": "BAB — Before / After / Bridge"},
    {"id": "Variant 6", "framework": "3Ps — Praise / Picture / Push (Compact)"},
    {"id": "Variant 7", "framework": "Demand Flip — Are you taking on new clients?"},
    {"id": "Variant 8", "framework": "Inverted Demand — Heads-Up / Scarcity"},
    {"id": "Variant 9", "framework": "Risk-Reversal — Pay on Results"},
]

DIVIDER = "=" * 72

def email_only_block(company: str, market: str = "") -> str:
    cta_term = _market_cta_term(market)
    return (
        "\n"
        f"  Reply AI DEMO — I'll send a 60-second demo showing exactly how the system\n"
        f"  books {company} 30 {cta_term} in 30 days.\n"
        f"  No call, no pitch. Just the demo.\n"
    )


async def gen_one(lead, analysis, variant, settings, cost_tracker):
    arm = {
        "id": variant["id"],
        "test_id": "framework_tournament_v1",
        "smartlead_campaign_id": settings.smartlead_campaign_id,
        "overrides": {"variant_framework": variant["framework"]},
    }
    try:
        email = await generate_email(lead, analysis, arm, settings, cost_tracker)
        return variant, email, None
    except Exception as e:
        return variant, None, str(e)


async def main():
    settings     = Settings()
    cost_tracker = CostTracker(daily_budget_usd=10.0)

    lead = read_leads(Path("data/input/test_leads.csv"))[0]
    print(f"\nEnriching {lead['first_name']} @ {lead['company']} …", flush=True)

    website_data  = await get_website_data(lead, settings)
    linkedin_data = await get_linkedin_data(lead, settings, cost_tracker)
    enrichment    = {"website": website_data, "linkedin": linkedin_data}

    print("Analysing fit …", flush=True)
    analysis = await analyze_fit(lead, enrichment, settings, cost_tracker)
    if analysis.get("market"):
        lead["market"] = analysis["market"]

    print(f"Generating all 9 variants in parallel …\n", flush=True)
    tasks = [
        gen_one(lead, analysis, v, settings, cost_tracker)
        for v in VARIANTS
    ]
    results = await asyncio.gather(*tasks)

    for variant, email, err in results:
        print(DIVIDER)
        print(f"  {variant['id'].upper()}  |  {variant['framework']}")
        print(DIVIDER)

        if err:
            print(f"  ERROR: {err}\n")
            continue

        subject = email.get("subject", "")
        market  = lead.get("market", "") or analysis.get("market", "")
        body    = _strip_video_references(email.get("body", ""), lead["company"])
        body    = body.replace("{VIDEO_LINK}", email_only_block(lead["company"], market))

        print(f"  FROM:    Frank <frank@ascentir.co>")
        print(f"  TO:      {lead['first_name']} {lead.get('last_name','')} <{lead['email']}>")
        print(f"  SUBJECT: {subject}")
        print()
        print(body)
        print()

    total = cost_tracker.total()
    print(DIVIDER)
    print(f"  Total API cost for generation: ${total:.4f}")
    print(DIVIDER)


if __name__ == "__main__":
    asyncio.run(main())
