"""
Smartlead API client.

Pushes a lead + their personalized email body into a Smartlead campaign.
Smartlead handles deliverability, sending schedule, warm-up, reply tracking.

Docs: https://api.smartlead.ai/reference/
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from src.utils.settings import Settings

log = logging.getLogger(__name__)

BASE_URL = "https://server.smartlead.ai/api/v1"


async def push_to_smartlead(
    lead: dict[str, Any],
    email_subject: str,
    email_body: str,
    settings: Settings,
) -> dict[str, Any]:
    """
    Add the lead to the configured campaign with their personalized email
    queued. Smartlead will send it on the campaign's schedule.
    """
    campaign_id = settings.smartlead_campaign_id
    api_key = settings.smartlead_api_key

    # Step 1: add the lead with custom fields containing the personalized content
    add_url = f"{BASE_URL}/campaigns/{campaign_id}/leads?api_key={api_key}"
    payload = {
        "lead_list": [
            {
                "first_name": lead["first_name"],
                "last_name": lead.get("last_name", ""),
                "email": lead["email"],
                "company_name": lead.get("company", ""),
                "website": lead.get("website", ""),
                "linkedin_profile": lead.get("linkedin_url", ""),
                # Custom fields you'll reference in your Smartlead campaign template
                # as {{custom_subject}} and {{custom_body}}
                "custom_fields": {
                    "custom_subject": email_subject,
                    "custom_body": email_body,
                },
            }
        ],
        "settings": {
            "ignore_global_block_list": False,
            "ignore_unsubscribe_list": False,
            "ignore_duplicate_leads_in_other_campaign": True,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(add_url, json=payload)
        r.raise_for_status()
        result = r.json()
        log.info(f"Pushed to Smartlead: {lead['email']} → campaign {campaign_id}")
        return result


# IMPORTANT: For this to actually use the personalized subject/body, your
# Smartlead campaign's email template must look like this:
#
#   Subject: {{custom_subject}}
#   Body:    {{custom_body}}
#
# Smartlead will substitute the per-lead values when sending.


async def _check_one_campaign(
    campaign_id: str,
    api_key: str,
    client: Any,
    variant_label: str = "",
) -> list[str]:
    """Check a single campaign. Returns a list of issue strings (empty = OK)."""
    issues: list[str] = []
    prefix = f"[{variant_label}] " if variant_label else ""

    r = await client.get(f"{BASE_URL}/campaigns/{campaign_id}?api_key={api_key}")
    if r.status_code == 404:
        issues.append(f"{prefix}Campaign {campaign_id} not found — check settings.yaml")
        return issues
    if r.status_code == 401:
        issues.append(f"{prefix}Smartlead API key is invalid — check SMARTLEAD_API_KEY in .env")
        return issues
    r.raise_for_status()

    campaign = r.json()
    status = campaign.get("status", "UNKNOWN")
    if status != "ACTIVE":
        issues.append(f"{prefix}Campaign {campaign_id} is {status} — must be ACTIVE")

    seq_r = await client.get(f"{BASE_URL}/campaigns/{campaign_id}/sequences?api_key={api_key}")
    if not seq_r.is_success:
        issues.append(f"{prefix}Campaign {campaign_id}: could not retrieve sequences")
        return issues

    seq_data = seq_r.json()
    sequences = seq_data if isinstance(seq_data, list) else seq_data.get("sequences", [])
    if not sequences:
        issues.append(
            f"{prefix}Campaign {campaign_id} has no sequence steps — "
            "add Step 1 with Subject: {{{{custom_subject}}}} and Body: {{{{custom_body}}}}"
        )
        return issues

    step1 = sequences[0]
    subject = (
        step1.get("email_subject") or step1.get("subject") or
        step1.get("template", {}).get("subject", "") or ""
    )
    body = (
        step1.get("email_body") or step1.get("body") or
        step1.get("template", {}).get("body", "") or ""
    )
    if "{{custom_subject}}" not in subject:
        issues.append(
            f"{prefix}Campaign {campaign_id} Step 1 subject missing {{{{custom_subject}}}}"
        )
    if "{{custom_body}}" not in body:
        issues.append(
            f"{prefix}Campaign {campaign_id} Step 1 body missing {{{{custom_body}}}}"
        )
    return issues


async def validate_campaign(settings: "Settings") -> dict:
    """Check ALL variant campaign IDs are correctly configured for personalised sends.

    Iterates every arm in the active test config and validates each campaign:
      1. Campaign exists and API key is valid
      2. Campaign status is ACTIVE
      3. Step 1 subject contains {{custom_subject}}
      4. Step 1 body contains {{custom_body}}

    Returns a dict with keys:
      ok          — bool, True only if all campaigns pass
      campaign_id — str (first/global campaign checked)
      name        — str or None
      status      — str or None
      issues      — list[str] of all problems across all campaigns
    """
    api_key = settings.smartlead_api_key
    issues: list[str] = []

    if not api_key:
        return {"ok": False, "campaign_id": None, "name": None, "status": None,
                "issues": ["SMARTLEAD_API_KEY is not set in .env"]}

    # Collect all campaign IDs from variant arms. Fall back to global .env ID
    # if no active test is configured.
    test_config = settings.active_test_config()
    if test_config:
        arms = test_config.get("arms", [])
        campaign_ids = [
            (arm.get("id", f"arm_{i}"), str(arm["smartlead_campaign_id"]))
            for i, arm in enumerate(arms)
            if arm.get("smartlead_campaign_id")
        ]
        missing_arms = [
            arm.get("id", f"arm_{i}")
            for i, arm in enumerate(arms)
            if not arm.get("smartlead_campaign_id")
        ]
        for arm_id in missing_arms:
            issues.append(f"Variant arm '{arm_id}' has no smartlead_campaign_id in settings.yaml")
    else:
        global_id = settings.smartlead_campaign_id
        if not global_id:
            return {"ok": False, "campaign_id": None, "name": None, "status": None,
                    "issues": ["SMARTLEAD_CAMPAIGN_ID is not set in .env and no active test configured"]}
        campaign_ids = [("global", global_id)]

    first_id = campaign_ids[0][1] if campaign_ids else None
    first_name = None
    first_status = None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Check every variant campaign
            for variant_label, campaign_id in campaign_ids:
                arm_issues = await _check_one_campaign(
                    campaign_id, api_key, client, variant_label=variant_label
                )
                issues.extend(arm_issues)

                # Capture name/status from the first campaign for the response envelope.
                # Always fetch regardless of issues so the UI has something to display.
                if variant_label == campaign_ids[0][0] and first_name is None:
                    r = await client.get(
                        f"{BASE_URL}/campaigns/{campaign_id}?api_key={api_key}"
                    )
                    if r.is_success:
                        c = r.json()
                        first_name   = c.get("name") or c.get("campaign_name") or campaign_id
                        first_status = c.get("status", "UNKNOWN")

    except httpx.TimeoutException:
        issues.append("Smartlead API timed out — check internet connection and retry")
    except Exception as e:
        issues.append(f"Unexpected error checking campaigns: {type(e).__name__}: {e}")

    return {
        "ok":          len(issues) == 0,
        "campaign_id": first_id,
        "name":        first_name,
        "status":      first_status,
        "issues":      issues,
    }
