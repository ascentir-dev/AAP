"""
CSV ingestion. Reads a leads CSV, validates required fields, generates lead IDs.
"""
from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED_COLS = {"first_name", "last_name", "email", "company", "website", "linkedin_url", "role"}
OPTIONAL_COLS = {"industry", "company_size", "priority"}


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _lead_id(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:16]


def read_leads(csv_path: Path) -> list[dict]:
    """Parse a leads CSV. Returns list of valid lead dicts."""
    leads: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = set(reader.fieldnames or [])
        missing_required = REQUIRED_COLS - headers
        if missing_required:
            log.warning(
                "CSV is missing required columns: %s — skipping file", missing_required
            )
            return []

        for i, row in enumerate(reader, start=2):  # row 1 is header
            email_raw = row.get("email", "").strip().lower()
            if not email_raw:
                log.warning("Row %d: missing email — skipping", i)
                continue

            # Check all required fields are non-empty
            skip = False
            for col in REQUIRED_COLS - {"email"}:
                if not row.get(col, "").strip():
                    log.warning(
                        "Row %d (email=%s): missing required field '%s' — skipping",
                        i, email_raw, col,
                    )
                    skip = True
                    break
            if skip:
                continue

            lead = {
                "lead_id": _lead_id(email_raw),
                "email": email_raw,
                "first_name": row["first_name"].strip(),
                "last_name": row["last_name"].strip(),
                "company": row["company"].strip(),
                "website": _normalize_url(row["website"]),
                "linkedin_url": row["linkedin_url"].strip(),
                "role": row["role"].strip(),
            }
            for col in OPTIONAL_COLS:
                if col in headers:
                    lead[col] = row[col].strip()

            leads.append(lead)

    return leads
