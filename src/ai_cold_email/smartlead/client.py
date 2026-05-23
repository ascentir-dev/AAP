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
