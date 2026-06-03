"""
Smartlead Sequence Setup — run once per campaign variant.

What it does:
  1. Reads all 9 variant campaign IDs from settings.yaml
  2. For each campaign, adds the 3 cold follow-up steps from config/settings.yaml
  3. Confirms each step was created

The follow-up sequence:
  Day 2 — "Hey {first_name}, did you get the chance to check out that video I sent?"
  Day 4 — "Hey {first_name}, figured this got buried. Any thoughts on the video?"  + video link
  Day 6 — "Hi {first_name}, any thoughts on the video I sent?"

Usage:
  python3 tools/setup_smartlead_sequence.py

  # Dry-run (show what would be pushed, don't call API):
  python3 tools/setup_smartlead_sequence.py --dry-run

  # Single campaign only:
  python3 tools/setup_smartlead_sequence.py --campaign-id 3379547

Notes:
  • Smartlead sequences are 1-indexed. Step 1 is the INITIAL email (already set up
    by your campaign template). Steps 2–4 are follow-ups.
  • If a step already exists it will be skipped — safe to re-run.
  • The {first_name} placeholder is a Smartlead native variable.
  • {VIDEO_LINK} is a custom field populated per-lead by the pipeline.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Push cold follow-up sequence to Smartlead campaigns")
    p.add_argument("--dry-run", action="store_true", help="Print what would be pushed, don't call API")
    p.add_argument("--campaign-id", default=None, help="Only update this campaign ID")
    return p.parse_args()


def _get_all_campaign_ids(settings) -> list[tuple[str, str]]:
    """Return list of (variant_id, campaign_id) for all active test arms."""
    test_cfg = settings.active_test_config()
    pairs: list[tuple[str, str]] = []
    if test_cfg:
        for arm in test_cfg.get("arms", []):
            cid = arm.get("smartlead_campaign_id", "")
            if cid:
                pairs.append((arm["id"], cid))
    # Always include the global fallback
    if settings.smartlead_campaign_id and settings.smartlead_campaign_id not in [c for _, c in pairs]:
        pairs.append(("default", settings.smartlead_campaign_id))
    return pairs


def _build_sequence_payload(followups: list[dict]) -> list[dict]:
    """
    Build Smartlead sequence step payloads.
    Steps are 1-indexed — step 1 is the initial email (already in campaign).
    Follow-ups start at step 2.
    """
    steps = []
    for fu in followups:
        step_num = fu["step"] + 1   # +1 because step 1 = initial email
        steps.append({
            "seq_number": step_num,
            "seq_delay_details": {
                "delay_in_days": fu["delay_days"],
            },
            "subject": fu["subject"],
            "email_body": fu["body"].strip(),
        })
    return steps


def push_sequence(campaign_id: str, variant_id: str, steps: list[dict],
                  api_key: str, dry_run: bool) -> None:
    """Push follow-up steps to a single Smartlead campaign."""
    import httpx

    base = "https://server.smartlead.ai/api/v1"

    for step in steps:
        label = f"  Step {step['seq_number']} (+{step['seq_delay_details']['delay_in_days']}d)"
        preview = step["email_body"][:60].replace("\n", " ") + "…"

        if dry_run:
            print(f"    [DRY RUN] {label}")
            print(f"             Subject : {step['subject']}")
            print(f"             Body    : {preview}")
            continue

        url = f"{base}/campaigns/{campaign_id}/sequences?api_key={api_key}"
        try:
            resp = httpx.post(url, json={"sequences": [step]}, timeout=15)
            if resp.status_code == 200:
                print(f"    ✓  {label} — {preview}")
            elif resp.status_code == 409:
                print(f"    –  {label} — already exists (skipped)")
            else:
                print(f"    ✗  {label} — HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"    ✗  {label} — {e}")


def main() -> None:
    args = _parse()

    from src.utils.settings import Settings
    import yaml

    settings = Settings()

    if not settings.smartlead_api_key:
        print("✗  SMARTLEAD_API_KEY not set in .env")
        sys.exit(1)

    # Load follow-ups from settings.yaml
    with open("config/settings.yaml") as f:
        cfg = yaml.safe_load(f)
    followups = cfg.get("cold_followups", [])
    if not followups:
        print("✗  No cold_followups found in config/settings.yaml")
        sys.exit(1)

    steps = _build_sequence_payload(followups)

    # Decide which campaigns to update
    if args.campaign_id:
        campaigns = [("custom", args.campaign_id)]
    else:
        campaigns = _get_all_campaign_ids(settings)

    if not campaigns:
        print("✗  No campaign IDs found in settings.yaml or .env")
        sys.exit(1)

    print(f"\n── Smartlead Sequence Setup {'(DRY RUN) ' if args.dry_run else ''}──────────────────────────\n")
    print(f"  Follow-up steps to push: {len(steps)}")
    print(f"  Campaigns to update:     {len(campaigns)}")
    print()

    print("  Sequence:")
    for fu in followups:
        print(f"    Day {fu['delay_days']:>2} — Step {fu['step']}: {fu['body'].strip()[:70]}")
    print()

    for variant_id, campaign_id in campaigns:
        print(f"  Campaign {campaign_id}  ({variant_id})")
        push_sequence(
            campaign_id=campaign_id,
            variant_id=variant_id,
            steps=steps,
            api_key=settings.smartlead_api_key,
            dry_run=args.dry_run,
        )
        print()

    print("  Done." if not args.dry_run else "  Dry run complete — re-run without --dry-run to push.")
    print()


if __name__ == "__main__":
    main()
