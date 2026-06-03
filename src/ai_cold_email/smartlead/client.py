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


async def validate_campaign(settings: "Settings") -> dict:
    """Check that the Smartlead campaign is correctly configured for personalised sends.

    Verifies:
      1. Campaign exists and API key is valid
      2. Campaign status is ACTIVE (not COMPLETED / PAUSED / DRAFT)
      3. At least one email sequence step exists
      4. Step 1 subject contains {{custom_subject}}
      5. Step 1 body contains {{custom_body}}

    Returns a dict with keys:
      ok          — bool, True only if all checks pass
      campaign_id — str
      name        — str or None
      status      — str or None ("ACTIVE", "COMPLETED", etc.)
      issues      — list[str] of human-readable problems (empty if ok=True)
    """
    campaign_id = settings.smartlead_campaign_id
    api_key = settings.smartlead_api_key
    issues: list[str] = []

    if not campaign_id:
        return {"ok": False, "campaign_id": None, "name": None, "status": None,
                "issues": ["SMARTLEAD_CAMPAIGN_ID is not set in .env"]}
    if not api_key:
        return {"ok": False, "campaign_id": campaign_id, "name": None, "status": None,
                "issues": ["SMARTLEAD_API_KEY is not set in .env"]}

    campaign_name = None
    campaign_status = None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 1. Fetch campaign details
            r = await client.get(
                f"{BASE_URL}/campaigns/{campaign_id}?api_key={api_key}"
            )
            if r.status_code == 404:
                return {"ok": False, "campaign_id": campaign_id, "name": None,
                        "status": None, "issues": [f"Campaign {campaign_id} not found — check SMARTLEAD_CAMPAIGN_ID in .env"]}
            if r.status_code == 401:
                return {"ok": False, "campaign_id": campaign_id, "name": None,
                        "status": None, "issues": ["Smartlead API key is invalid — check SMARTLEAD_API_KEY in .env"]}
            r.raise_for_status()
            campaign = r.json()
            campaign_name   = campaign.get("name") or campaign.get("campaign_name") or str(campaign_id)
            campaign_status = campaign.get("status", "UNKNOWN")

            if campaign_status != "ACTIVE":
                issues.append(
                    f"Campaign is {campaign_status} — must be set to ACTIVE in Smartlead before pushing leads"
                )

            # 2. Fetch email sequences / steps
            seq_r = await client.get(
                f"{BASE_URL}/campaigns/{campaign_id}/sequences?api_key={api_key}"
            )
            if not seq_r.is_success:
                issues.append("Could not retrieve campaign sequences — check campaign permissions")
            else:
                seq_data = seq_r.json()
                # Smartlead returns either a list or {"sequences": [...]}
                sequences = seq_data if isinstance(seq_data, list) else seq_data.get("sequences", [])

                if not sequences:
                    issues.append(
                        "Campaign has no email sequence steps — add Step 1 with "
                        "Subject: {{custom_subject}} and Body: {{custom_body}}"
                    )
                else:
                    # Check Step 1 (index 0 or seq_number == 1)
                    step1 = sequences[0]
                    # Sequences can nest the email template in different keys
                    subject = (
                        step1.get("email_subject") or
                        step1.get("subject") or
                        step1.get("template", {}).get("subject", "") or ""
                    )
                    body = (
                        step1.get("email_body") or
                        step1.get("body") or
                        step1.get("template", {}).get("body", "") or ""
                    )
                    if "{{custom_subject}}" not in subject:
                        issues.append(
                            "Step 1 subject does not contain {{custom_subject}} — "
                            "set Step 1 subject to exactly: {{custom_subject}}"
                        )
                    if "{{custom_body}}" not in body:
                        issues.append(
                            "Step 1 body does not contain {{custom_body}} — "
                            "set Step 1 body to exactly: {{custom_body}}"
                        )

    except httpx.TimeoutException:
        issues.append("Smartlead API timed out — check your internet connection and try again")
    except Exception as e:
        issues.append(f"Unexpected error checking campaign: {type(e).__name__}: {e}")

    return {
        "ok":          len(issues) == 0,
        "campaign_id": str(campaign_id),
        "name":        campaign_name,
        "status":      campaign_status,
        "issues":      issues,
    }
