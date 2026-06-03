"""
CSV ingestion. Reads a leads CSV, validates required fields, generates lead IDs.

Supports two CSV formats:

1. NATIVE FORMAT — lowercase columns produced by this platform:
      first_name, last_name, email, company, website, linkedin_url, role
      Optional: industry, company_size, priority

2. SKIPTRACE FORMAT — uppercase columns from skip-trace / data enrichment exports
      (e.g. Apollo skip-trace, Clay, etc.):
      UUID, FIRST_NAME, LAST_NAME, BUSINESS_EMAIL, COMPANY_NAME,
      COMPANY_DOMAIN, LINKEDIN_URL, JOB_TITLE, COMPANY_INDUSTRY, ...

   Auto-detected from the header row. Skiptrace columns are mapped to the
   pipeline's expected field names. Multi-value fields (comma-separated
   phone / email lists) take the first valid value. DNC flags are parsed
   so the SMS pipeline can honour them.

   Pre-enrichment bonus fields carried through to bypass web-scraping and
   LinkedIn enrichment:
       pre_enrichment_company_description  →  replaces website scrape
       pre_enrichment_linkedin_headline    →  replaces Apify LinkedIn call
       pre_enrichment_skills               →  supplements LinkedIn data
"""
from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ── Native format ─────────────────────────────────────────────────────────────
REQUIRED_COLS  = {"first_name", "last_name", "email", "company", "website", "linkedin_url", "role"}
OPTIONAL_COLS  = {"industry", "company_size", "priority"}

# ── Skiptrace format ──────────────────────────────────────────────────────────
# Maps skiptrace column names → pipeline field names.
SKIPTRACE_COLUMN_MAP: dict[str, str] = {
    # Required
    "FIRST_NAME":               "first_name",
    "LAST_NAME":                "last_name",
    "BUSINESS_EMAIL":           "email",
    "COMPANY_NAME":             "company",
    "COMPANY_DOMAIN":           "website",          # https:// added below
    "LINKEDIN_URL":             "linkedin_url",
    "JOB_TITLE":                "role",
    # Optional standard
    "UUID":                     "uuid",
    "COMPANY_INDUSTRY":         "industry",
    "COMPANY_EMPLOYEE_COUNT":   "company_size",
    "COMPANY_REVENUE":          "company_revenue",
    "SENIORITY_LEVEL":          "seniority_level",
    "COMPANY_CITY":             "company_city",
    "COMPANY_STATE":            "company_state",
    "NET_WORTH":                "net_worth",
    "INCOME_RANGE":             "income_range",
    "AGE_RANGE":                "age_range",
    # Pre-enrichment — these bypass Playwright + Apify for this dataset
    "COMPANY_DESCRIPTION":      "pre_enrichment_company_description",
    "HEADLINE":                 "pre_enrichment_linkedin_headline",
    "SKILLS":                   "pre_enrichment_skills",
    "INTERESTS":                "pre_enrichment_interests",
    "JOB_TITLE_HISTORY":        "pre_enrichment_job_history",
    "COMPANY_NAME_HISTORY":     "pre_enrichment_company_history",
    # Phone + DNC (kept raw for SMS pipeline)
    "MOBILE_PHONE":             "mobile_phone_raw",
    "MOBILE_PHONE_DNC":         "mobile_phone_dnc_raw",
    "DIRECT_NUMBER":            "direct_number_raw",
    "DIRECT_NUMBER_DNC":        "direct_number_dnc_raw",
}

# ── Industry → market pre-detection ──────────────────────────────────────────
# Used to set lead["market"] before analysis, saving Claude tokens.
INDUSTRY_TO_MARKET: dict[str, str] = {
    "financial services":                  "financial_advisor",
    "advertising services":                "agency",
    "business consulting and services":    "consultant",
    "professional training and coaching":  "coach",
    "it services and it consulting":       "msp",
    "managed it services":                 "msp",
    "managed security services":           "msp",
    "cybersecurity":                       "msp",
    "marketing services":                  "agency",
    "marketing and advertising":           "agency",
    "online and direct marketing":         "agency",
    "consulting":                          "consultant",
    "management consulting":               "consultant",
    "business intelligence platforms":     "consultant",
    "coaching & mentoring":                "coach",
    "professional training":               "coach",
    "e-learning":                          "coach",
    "online learning":                     "coach",
    "wealth management":                   "financial_advisor",
    "investment management":               "financial_advisor",
    "insurance":                           "financial_advisor",
    "accounting":                          "financial_advisor",
    "banking":                             "financial_advisor",
    "information technology and services": "msp",
    "technology, information and media":   "msp",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _lead_id(identifier: str) -> str:
    """16-char hex ID derived from UUID or email."""
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]


def _first_value(field_str: str) -> str:
    """Return first non-empty value from a comma-separated multi-value field."""
    if not field_str:
        return ""
    for val in field_str.split(","):
        val = val.strip()
        if val:
            return val
    return ""


def _pick_phone(phones_str: str, dnc_str: str) -> tuple[str, bool]:
    """Return (first_non_dnc_phone, is_all_dnc).

    Phones and DNC flags are parallel comma-separated lists:
      MOBILE_PHONE:     +16174292066, +13177888319
      MOBILE_PHONE_DNC: Y, N
    Returns the first phone whose corresponding DNC flag is not 'Y'.
    If all are DNC, returns (first_phone, True).
    """
    phones = [p.strip() for p in (phones_str or "").split(",") if p.strip()]
    dncs   = [d.strip().upper() for d in (dnc_str or "").split(",")]

    for i, phone in enumerate(phones):
        is_dnc = (i < len(dncs) and dncs[i] == "Y")
        if not is_dnc:
            return phone, False

    return (phones[0] if phones else ""), bool(phones)


def _detect_format(headers: list[str]) -> str:
    """Return 'skiptrace' or 'native' based on header names."""
    upper_set = {h.upper() for h in headers}
    skiptrace_keys = {"FIRST_NAME", "BUSINESS_EMAIL", "COMPANY_DOMAIN"}
    if skiptrace_keys.issubset(upper_set):
        return "skiptrace"
    return "native"


# ── Skiptrace row parser ──────────────────────────────────────────────────────

def _parse_skiptrace_row(row: dict, row_num: int) -> dict | None:
    """Map a skiptrace CSV row to the pipeline's lead dict. Returns None to skip."""

    # ── Required field extraction ─────────────────────────────────────────────
    first_name = row.get("FIRST_NAME", "").strip()
    last_name  = row.get("LAST_NAME", "").strip()
    if not first_name:
        log.warning("Row %d: missing FIRST_NAME — skipping", row_num)
        return None

    # Email — may be comma-separated; take the first verified business email
    raw_email = row.get("BUSINESS_EMAIL", "").strip()
    if not raw_email:
        raw_email = row.get("BUSINESS_VERIFIED_EMAILS", "").strip()
    email = _first_value(raw_email).lower()
    if not email or "@" not in email:
        log.warning("Row %d (%s %s): no valid business email — skipping", row_num, first_name, last_name)
        return None

    company = row.get("COMPANY_NAME", "").strip()
    if not company:
        log.warning("Row %d (email=%s): missing COMPANY_NAME — skipping", row_num, email)
        return None

    domain  = row.get("COMPANY_DOMAIN", "").strip()
    website = _normalize_url(domain) if domain else ""
    if not website:
        log.warning("Row %d (email=%s): missing COMPANY_DOMAIN — skipping", row_num, email)
        return None

    role = row.get("JOB_TITLE", "").strip()
    if not role:
        log.warning("Row %d (email=%s): missing JOB_TITLE — skipping", row_num, email)
        return None

    linkedin_url = row.get("LINKEDIN_URL", "").strip()
    # LinkedIn not strictly required for skiptrace format — leave blank if absent

    # ── lead_id: prefer UUID if present ──────────────────────────────────────
    uuid_raw = row.get("UUID", "").strip()
    lead_id  = _lead_id(uuid_raw if uuid_raw else email)

    # ── Optional standard fields ──────────────────────────────────────────────
    industry     = row.get("COMPANY_INDUSTRY", "").strip()
    company_size = row.get("COMPANY_EMPLOYEE_COUNT", "").strip()

    # ── Market pre-detection from industry ────────────────────────────────────
    market = INDUSTRY_TO_MARKET.get(industry.lower(), "")

    # ── Phone + DNC ───────────────────────────────────────────────────────────
    mobile_phone, mobile_dnc = _pick_phone(
        row.get("MOBILE_PHONE", ""),
        row.get("MOBILE_PHONE_DNC", ""),
    )
    direct_number, direct_dnc = _pick_phone(
        row.get("DIRECT_NUMBER", ""),
        row.get("DIRECT_NUMBER_DNC", ""),
    )

    # ── Pre-enrichment fields ─────────────────────────────────────────────────
    company_desc = row.get("COMPANY_DESCRIPTION", "").strip()
    headline     = row.get("HEADLINE", "").strip()
    skills       = row.get("SKILLS", "").strip()
    interests    = row.get("INTERESTS", "").strip()
    job_history  = row.get("JOB_TITLE_HISTORY", "").strip()
    co_history   = row.get("COMPANY_NAME_HISTORY", "").strip()

    lead: dict = {
        # Core pipeline fields
        "lead_id":      lead_id,
        "email":        email,
        "first_name":   first_name,
        "last_name":    last_name,
        "company":      company,
        "website":      website,
        "linkedin_url": linkedin_url,
        "role":         role,
        # Optional standard
        "industry":     industry,
        "company_size": company_size,
        "market":       market,          # pre-detected — confirmed/refined by analysis
        # Contact + DNC
        "mobile_phone":     mobile_phone,
        "mobile_phone_dnc": mobile_dnc,
        "direct_number":    direct_number,
        "direct_number_dnc": direct_dnc,
        # Seniority / qualification
        "seniority_level":  row.get("SENIORITY_LEVEL", "").strip(),
        "company_revenue":  row.get("COMPANY_REVENUE", "").strip(),
        "company_city":     row.get("COMPANY_CITY", "").strip(),
        "company_state":    row.get("COMPANY_STATE", "").strip(),
        "net_worth":        row.get("NET_WORTH", "").strip(),
        "income_range":     row.get("INCOME_RANGE", "").strip(),
        # Pre-enrichment data — used by pipeline to skip web scrape + Apify
        "pre_enrichment_company_description": company_desc,
        "pre_enrichment_linkedin_headline":   headline,
        "pre_enrichment_skills":              skills,
        "pre_enrichment_interests":           interests,
        "pre_enrichment_job_history":         job_history,
        "pre_enrichment_company_history":     co_history,
    }

    return lead


# ── Native row parser ─────────────────────────────────────────────────────────

def _parse_native_row(row: dict, headers: set[str], row_num: int) -> dict | None:
    """Parse a native-format row. Returns None to skip."""
    email_raw = row.get("email", "").strip().lower()
    if not email_raw:
        log.warning("Row %d: missing email — skipping", row_num)
        return None

    for col in REQUIRED_COLS - {"email"}:
        if not row.get(col, "").strip():
            log.warning(
                "Row %d (email=%s): missing required field '%s' — skipping",
                row_num, email_raw, col,
            )
            return None

    lead: dict = {
        "lead_id":      _lead_id(email_raw),
        "email":        email_raw,
        "first_name":   row["first_name"].strip(),
        "last_name":    row["last_name"].strip(),
        "company":      row["company"].strip(),
        "website":      _normalize_url(row["website"]),
        "linkedin_url": row["linkedin_url"].strip(),
        "role":         row["role"].strip(),
        "market":       "",   # will be detected by analysis
    }
    for col in OPTIONAL_COLS:
        if col in headers:
            lead[col] = row[col].strip()

    return lead


# ── Public API ────────────────────────────────────────────────────────────────

def read_leads(csv_path: Path) -> list[dict]:
    """Parse a leads CSV (native or skiptrace format). Returns valid lead dicts.

    Auto-detects the CSV format from the header row and applies the
    appropriate parser. Skipped rows are logged as warnings.
    """
    leads: list[dict] = []
    csv_path = Path(csv_path)

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
        reader  = csv.DictReader(fh)
        headers = list(reader.fieldnames or [])
        fmt     = _detect_format(headers)

        log.info("CSV format detected: %s  (%s)", fmt, csv_path.name)

        if fmt == "native":
            headers_set = set(headers)
            missing = REQUIRED_COLS - headers_set
            if missing:
                log.warning("CSV missing required columns: %s — skipping file", missing)
                return []
            for i, row in enumerate(reader, start=2):
                lead = _parse_native_row(row, headers_set, i)
                if lead:
                    leads.append(lead)

        else:  # skiptrace
            for i, row in enumerate(reader, start=2):
                lead = _parse_skiptrace_row(row, i)
                if lead:
                    leads.append(lead)

    log.info(
        "Ingested %d leads from %s (format=%s)",
        len(leads), csv_path.name, fmt,
    )
    return leads
