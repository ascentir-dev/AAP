"""
One-time script to create all 9 Ascentir variant campaigns in Smartlead.

Run ONCE after you activate a Smartlead plan:
    python3 scripts/create_smartlead_campaigns.py

What it does:
  1. Creates 9 campaigns (one per copywriting framework variant)
  2. Adds a one-step email sequence to each with {{custom_subject}} / {{custom_body}}
  3. Prints the campaign IDs so you can paste them into config/settings.yaml

Why {{custom_subject}} and {{custom_body}}?
  The pipeline generates 100% personalised subject + body per lead using Claude.
  Smartlead just delivers it. These placeholders tell Smartlead to use whatever
  the pipeline sent — no manual writing needed.
"""
from __future__ import annotations

import asyncio
import httpx
from src.utils.settings import load_settings


CAMPAIGNS = [
    {
        "variant": "Variant 1",
        "framework": "3C Berman",
        "description": "Compliment + Case Study + CTA — highest-volume default",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_1",
    },
    {
        "variant": "Variant 2",
        "framework": "Predictable Revenue",
        "description": "Referral / Right Person — asks for the right contact",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_2",
    },
    {
        "variant": "Variant 3",
        "framework": "AIDA",
        "description": "Attention / Interest / Desire / Action — classical copywriting",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_3",
    },
    {
        "variant": "Variant 4",
        "framework": "PAS",
        "description": "Problem / Agitate / Solve — strongest with visible pain signal",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_4",
    },
    {
        "variant": "Variant 5",
        "framework": "BAB",
        "description": "Before / After / Bridge — best for companies in transition",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_5",
    },
    {
        "variant": "Variant 6",
        "framework": "3Ps",
        "description": "Praise / Picture / Push — peer tone, best for VP+ buyers",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_6",
    },
    {
        "variant": "Variant 7",
        "framework": "One-Sentence",
        "description": "Berman one-sentence — highest reply rate per word",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_7",
    },
    {
        "variant": "Variant 8",
        "framework": "Inverted Demand",
        "description": "Heads-Up / Scarcity — flips the power dynamic",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_8",
    },
    {
        "variant": "Variant 9",
        "framework": "Pay-on-Results",
        "description": "Risk-Reversal — for prospects burned by AI vendors before",
        "yaml_key": "REPLACE_WITH_REAL_CAMPAIGN_ID_9",
    },
]


async def create_campaigns() -> None:
    settings = load_settings()
    api_key = settings.smartlead_api_key
    base = "https://server.smartlead.ai/api/v1"

    print(f"\n🚀 Creating {len(CAMPAIGNS)} Smartlead campaigns...\n")

    created = []

    async with httpx.AsyncClient(timeout=30) as client:
        for c in CAMPAIGNS:
            name = f"Ascentir — {c['variant']} ({c['framework']})"

            # ── Step 1: Create the campaign ──────────────────────────────────
            r = await client.post(
                f"{base}/campaigns/create?api_key={api_key}",
                json={"name": name},
            )

            if r.status_code not in (200, 201):
                print(f"  ❌ {c['variant']} — {r.status_code}: {r.text[:200]}")
                continue

            campaign_id = r.json().get("id")
            print(f"  ✅ {name}")
            print(f"     Campaign ID: {campaign_id}")

            # ── Step 2: Add email sequence ────────────────────────────────────
            # The template uses {{custom_subject}} and {{custom_body}} —
            # the pipeline fills these in per lead via the Smartlead API.
            seq_r = await client.post(
                f"{base}/campaigns/{campaign_id}/sequences?api_key={api_key}",
                json={
                    "sequences": [
                        {
                            "seq_number": 1,
                            "seq_delay_details": {"delay_in_days": 0},
                            "subject": "{{custom_subject}}",
                            "email_body": "{{custom_body}}",
                        }
                    ]
                },
            )

            if seq_r.status_code not in (200, 201):
                print(f"     ⚠️  Sequence warning: {seq_r.status_code} {seq_r.text[:80]}")
            else:
                print(f"     Email template: {{{{custom_subject}}}} / {{{{custom_body}}}} ✓")

            created.append(
                {"variant": c["variant"], "id": campaign_id, "name": name}
            )
            print()

    # ── Print the YAML snippet to copy into settings.yaml ────────────────────
    if not created:
        print("❌ No campaigns created. Check your Smartlead plan is active.")
        return

    print("\n" + "=" * 60)
    print("PASTE THESE IDs INTO config/settings.yaml")
    print("Under variants.framework_tournament_v1.arms[N].smartlead_campaign_id")
    print("=" * 60 + "\n")

    for c in created:
        print(f"  {c['variant']}: {c['id']}")

    print("\nAlso set SMARTLEAD_CAMPAIGN_ID in .env to the Variant 1 ID (default fallback):")
    if created:
        print(f"  SMARTLEAD_CAMPAIGN_ID={created[0]['id']}")

    print("\n✅ Done. Run the pipeline when ready:\n")
    print("  python3 -m src.orchestrator \\")
    print("    --csv data/input/your_leads.csv \\")
    print("    --single-lead 0 \\")
    print("    --dry-run")


if __name__ == "__main__":
    asyncio.run(create_campaigns())
