"""
AudienceLedger — SQLite-backed storage for AudienceLab CSV imports.

Stores raw contact data downloaded from AudienceLab.io.
Global deduplication key: business_email (or personal_email fallback, or name+company).

Usage:
    from src.audience.ledger import AudienceLedger, map_csv_row
    db = AudienceLedger()
    import_id = db.create_import("Ascentir Technologies", "audience_export.csv")
    for row in csv_rows:
        mapped = map_csv_row(row)
        if mapped:
            db.ingest(import_id, [mapped])
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

# ── Column aliases ────────────────────────────────────────────────────────────
# Map possible AudienceLab column names → internal field name.
# Comparison is done after normalising the CSV header (lowercase, strip,
# replace spaces/dashes/underscores with a single space).

_ALIAS: dict[str, str] = {
    # First name
    "first name": "first_name",
    "firstname": "first_name",
    "first": "first_name",
    # Last name
    "last name": "last_name",
    "lastname": "last_name",
    "last": "last_name",
    # Business email
    "business email": "business_email",
    "work email": "business_email",
    "email": "business_email",
    "email address": "business_email",
    "work email address": "business_email",
    # Business phone
    "business phone": "business_phone",
    "work phone": "business_phone",
    "phone": "business_phone",
    "phone number": "business_phone",
    "work phone number": "business_phone",
    # Company
    "company": "company",
    "organization": "company",
    "company name": "company",
    "employer": "company",
    # Company domain
    "company domain": "company_domain",
    "domain": "company_domain",
    "website": "company_domain",
    "company website": "company_domain",
    # Job title
    "job title": "job_title",
    "title": "job_title",
    "position": "job_title",
    "role": "job_title",
    # Personal phone
    "personal phone": "personal_phone",
    "mobile phone": "personal_phone",
    "cell phone": "personal_phone",
    "mobile": "personal_phone",
    "cell": "personal_phone",
    # Skiptrace wireless (used for wireless flag)
    "skip traced wireless phone number": "wireless_phone",
    "skiptrace wireless": "wireless_phone",
    "wireless phone": "wireless_phone",
    "wireless": "wireless_phone",
    # Personal email
    "personal email": "personal_email",
    "personal email address": "personal_email",
    # LinkedIn
    "linkedin url": "linkedin_url",
    "linkedin": "linkedin_url",
    # Location fields
    "city": "city",
    "state": "state",
    "country": "country",
    "location": "location",
    # Industry
    "industry": "industry",
    "vertical": "industry",
    # Seniority / level
    "seniority": "seniority",
    "job seniority": "seniority",
    "level": "seniority",
    "management level": "seniority",
    # Department
    "department": "department",
    "function": "department",
    "job function": "department",
    # Employee count
    "employee count": "employee_count",
    "number of employees": "employee_count",
    "employees": "employee_count",
    # Revenue
    "annual revenue": "revenue",
    "revenue": "revenue",
}


def _norm_header(h: str) -> str:
    """Lowercase, strip, collapse whitespace/punctuation for fuzzy matching."""
    return re.sub(r"[\s\-_]+", " ", h.strip().lower())


def map_csv_row(raw_row: dict[str, str]) -> Optional[dict[str, Any]]:
    """
    Map a raw CSV row (arbitrary column names) to our internal field names.

    Returns None only if the row has no usable dedup key (no email, no name,
    no company).  All other rows are returned — even sparsely populated ones.
    """
    mapped: dict[str, Any] = {}

    for raw_col, value in raw_row.items():
        key = _ALIAS.get(_norm_header(raw_col))
        if key and value and value.strip():
            mapped[key] = value.strip()

    # Ensure we have at least something to deduplicate on
    has_email   = bool(mapped.get("business_email") or mapped.get("personal_email"))
    has_name    = bool(mapped.get("first_name") or mapped.get("last_name"))
    has_company = bool(mapped.get("company"))
    if not (has_email or (has_name and has_company)):
        return None

    # Store all raw columns too (for the raw_data JSON)
    mapped["_raw"] = {k: v for k, v in raw_row.items() if v and v.strip()}

    return mapped


def _make_dedup_key(row: dict[str, Any]) -> str:
    """
    Stable, case-insensitive dedup key for a mapped row.
    Priority: business_email > personal_email > name+company slug.
    """
    email = (
        row.get("business_email")
        or row.get("personal_email")
        or ""
    ).strip().lower()
    if email:
        return email

    fn = (row.get("first_name") or "").strip().lower()
    ln = (row.get("last_name")  or "").strip().lower()
    co = (row.get("company")    or "").strip().lower()
    slug = re.sub(r"\s+", "-", f"{fn}.{ln}@{co}")
    return slug


# ── Ledger ────────────────────────────────────────────────────────────────────

class AudienceLedger:
    """
    Manages two SQLite tables:
      audience_imports  — one row per uploaded CSV file
      audience_leads    — globally deduplicated contacts
    """

    def __init__(self, path: str = "data/audience.sqlite"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── connection ─────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── schema ─────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS audience_imports (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    name           TEXT    NOT NULL,
                    filename       TEXT,
                    created_at     REAL    DEFAULT (unixepoch()),
                    last_refreshed REAL    DEFAULT (unixepoch()),
                    refresh_count  INTEGER DEFAULT 0,
                    row_count      INTEGER DEFAULT 0,
                    new_count      INTEGER DEFAULT 0,
                    dup_count      INTEGER DEFAULT 0,
                    webhook_url    TEXT
                );

                CREATE TABLE IF NOT EXISTS audience_leads (
                    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedup_key                   TEXT    NOT NULL UNIQUE,
                    first_name                  TEXT,
                    last_name                   TEXT,
                    business_email              TEXT,
                    business_phone              TEXT,
                    company                     TEXT,
                    company_domain              TEXT,
                    job_title                   TEXT,
                    seniority                   TEXT,
                    department                  TEXT,
                    personal_phone              TEXT,
                    wireless_phone              TEXT,
                    personal_email              TEXT,
                    linkedin_url                TEXT,
                    city                        TEXT,
                    state                       TEXT,
                    country                     TEXT,
                    industry                    TEXT,
                    employee_count              TEXT,
                    revenue                     TEXT,
                    has_verified_business_email INTEGER DEFAULT 0,
                    has_verified_personal_email INTEGER DEFAULT 0,
                    has_valid_phone             INTEGER DEFAULT 0,
                    has_wireless_phone          INTEGER DEFAULT 0,
                    import_ids                  TEXT    DEFAULT '[]',
                    raw_data                    TEXT    DEFAULT '{}',
                    created_at                  REAL    DEFAULT (unixepoch()),
                    updated_at                  REAL    DEFAULT (unixepoch())
                );

                CREATE INDEX IF NOT EXISTS idx_al_dedup   ON audience_leads(dedup_key);
                CREATE INDEX IF NOT EXISTS idx_al_company ON audience_leads(company);
                CREATE INDEX IF NOT EXISTS idx_al_email   ON audience_leads(business_email);
                CREATE INDEX IF NOT EXISTS idx_al_job     ON audience_leads(job_title);
            """)

            # Migrations: add new columns if they don't exist
            existing_cols_imports = {
                row[1] for row in conn.execute("PRAGMA table_info(audience_imports)").fetchall()
            }
            for col, defn in [
                ("new_count",   "INTEGER DEFAULT 0"),
                ("dup_count",   "INTEGER DEFAULT 0"),
                ("webhook_url", "TEXT"),
            ]:
                if col not in existing_cols_imports:
                    conn.execute(f"ALTER TABLE audience_imports ADD COLUMN {col} {defn}")

            existing_cols_leads = {
                row[1] for row in conn.execute("PRAGMA table_info(audience_leads)").fetchall()
            }
            for col, defn in [
                ("seniority",  "TEXT"),
                ("department", "TEXT"),
            ]:
                if col not in existing_cols_leads:
                    conn.execute(f"ALTER TABLE audience_leads ADD COLUMN {col} {defn}")

            # Indexes for newly-added columns (safe to re-run: IF NOT EXISTS)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_al_seniority ON audience_leads(seniority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_al_industry  ON audience_leads(industry)")

    # ── imports CRUD ───────────────────────────────────────────────────────

    def create_import(self, name: str, filename: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO audience_imports (name, filename) VALUES (?, ?)",
                (name, filename),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def list_imports(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audience_imports ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_import(self, import_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM audience_imports WHERE id = ?", (import_id,)
            ).fetchone()
            return dict(row) if row else None

    def delete_import(self, import_id: int) -> None:
        """Delete the import record.  Leads that came from other imports survive."""
        with self._conn() as conn:
            conn.execute("DELETE FROM audience_imports WHERE id = ?", (import_id,))
            # Remove this import_id from all leads' import_ids arrays
            conn.execute(
                "UPDATE audience_leads SET import_ids = '[]' WHERE import_ids = ?",
                (json.dumps([import_id]),),
            )
            # Remove leads now orphaned (came only from this import)
            conn.execute(
                "DELETE FROM audience_leads WHERE import_ids = '[]'"
            )

    def rename_import(self, import_id: int, name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE audience_imports SET name = ? WHERE id = ?", (name, import_id)
            )

    # ── ingestion ──────────────────────────────────────────────────────────

    def ingest(self, import_id: int, rows: list[dict]) -> tuple[int, int]:
        """
        Upsert a batch of mapped rows.
        Returns (inserted, updated/duplicate) counts.
        """
        inserted = updated = 0

        with self._conn() as conn:
            for row in rows:
                key = _make_dedup_key(row)
                if not key:
                    continue

                raw = row.pop("_raw", {})

                existing = conn.execute(
                    "SELECT id, import_ids FROM audience_leads WHERE dedup_key = ?", (key,)
                ).fetchone()

                import_ids_list: list[int] = json.loads(existing["import_ids"]) if existing else []
                if import_id not in import_ids_list:
                    import_ids_list.append(import_id)

                if existing:
                    # Update import_ids so we know it belongs here too
                    conn.execute(
                        "UPDATE audience_leads SET import_ids = ?, updated_at = unixepoch() WHERE dedup_key = ?",
                        (json.dumps(import_ids_list), key),
                    )
                    updated += 1
                else:
                    conn.execute("""
                        INSERT INTO audience_leads
                            (dedup_key, first_name, last_name, business_email, business_phone,
                             company, company_domain, job_title, seniority, department,
                             personal_phone, wireless_phone, personal_email, linkedin_url,
                             city, state, country, industry, employee_count, revenue,
                             has_verified_business_email, has_verified_personal_email,
                             has_valid_phone, has_wireless_phone,
                             import_ids, raw_data)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        key,
                        row.get("first_name"),
                        row.get("last_name"),
                        row.get("business_email"),
                        row.get("business_phone"),
                        row.get("company"),
                        row.get("company_domain"),
                        row.get("job_title"),
                        row.get("seniority"),
                        row.get("department"),
                        row.get("personal_phone"),
                        row.get("wireless_phone"),
                        row.get("personal_email"),
                        row.get("linkedin_url"),
                        row.get("city"),
                        row.get("state"),
                        row.get("country"),
                        row.get("industry"),
                        row.get("employee_count"),
                        row.get("revenue"),
                        1 if row.get("business_email") else 0,
                        1 if row.get("personal_email") else 0,
                        1 if (row.get("business_phone") or row.get("personal_phone")) else 0,
                        1 if row.get("wireless_phone") else 0,
                        json.dumps(import_ids_list),
                        json.dumps(raw),
                    ))
                    inserted += 1

            # Update import metadata
            conn.execute("""
                UPDATE audience_imports
                SET row_count      = row_count + ?,
                    new_count      = new_count  + ?,
                    dup_count      = dup_count  + ?,
                    last_refreshed = unixepoch(),
                    refresh_count  = refresh_count + 1
                WHERE id = ?
            """, (inserted + updated, inserted, updated, import_id))

        return inserted, updated

    # ── queries ────────────────────────────────────────────────────────────

    # Keyword patterns used to infer seniority from job_title when no seniority
    # column is present in the CSV.
    _SENIORITY_PATTERNS: dict[str, list[str]] = {
        "cxo":       ["ceo", "cto", "cfo", "coo", "cmo", "cro", "ciso", "chief "],
        "vp":        ["vice president", " vp ", "vp of", "vp,"],
        "director":  ["director"],
        "manager":   ["manager"],
        "owner":     ["owner"],
        "partner":   ["partner"],
        "president": ["president"],
        "founder":   ["founder", "co-founder"],
        "head":      ["head of"],
    }

    def _seniority_clause(self, seniority_list: list[str], params: list[Any]) -> str:
        """Build an OR clause that matches seniority col or derives from job_title."""
        sub_clauses: list[str] = []
        for s in seniority_list:
            s_lower = s.lower()
            # Exact match on seniority column
            sub_clauses.append("LOWER(seniority) LIKE ?")
            params.append(f"%{s_lower}%")
            # Fall back to job_title keyword scan
            for kw in self._SENIORITY_PATTERNS.get(s_lower, [s_lower]):
                sub_clauses.append("LOWER(job_title) LIKE ?")
                params.append(f"%{kw}%")
        return f"({' OR '.join(sub_clauses)})" if sub_clauses else "1=1"

    def list_leads(
        self,
        offset: int = 0,
        limit: int = 100,
        search: str = "",
        has_phone: bool = False,
        has_email: bool = False,
        has_wireless: bool = False,
        has_personal_email: bool = False,
        import_id: Optional[int] = None,
        # Business filters
        job_titles: Optional[list[str]] = None,
        seniority: Optional[list[str]] = None,
        departments: Optional[list[str]] = None,
        company_names: Optional[list[str]] = None,
        company_domains: Optional[list[str]] = None,
        industries: Optional[list[str]] = None,
    ) -> tuple[list[dict], int]:
        clauses: list[str] = ["1=1"]
        params: list[Any] = []

        if search:
            clauses.append("""
                (first_name LIKE ? OR last_name LIKE ? OR company LIKE ?
                 OR business_email LIKE ? OR job_title LIKE ? OR company_domain LIKE ?)
            """)
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s])

        if has_email:
            clauses.append("has_verified_business_email = 1")
        if has_personal_email:
            clauses.append("has_verified_personal_email = 1")
        if has_phone:
            clauses.append("has_valid_phone = 1")
        if has_wireless:
            clauses.append("has_wireless_phone = 1")
        if import_id is not None:
            clauses.append("import_ids LIKE ?")
            params.append(f"%\"{import_id}\"%")

        def _or_like(field: str, values: list[str]) -> str:
            sub: list[str] = []
            for v in values:
                sub.append(f"LOWER({field}) LIKE ?")
                params.append(f"%{v.lower()}%")
            return f"({' OR '.join(sub)})"

        if job_titles:
            clauses.append(_or_like("job_title", job_titles))
        if seniority:
            clauses.append(self._seniority_clause(seniority, params))
        if departments:
            clauses.append(_or_like("department", departments))
        if company_names:
            clauses.append(_or_like("company", company_names))
        if company_domains:
            clauses.append(_or_like("company_domain", company_domains))
        if industries:
            clauses.append(_or_like("industry", industries))

        where = " AND ".join(clauses)
        with self._conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM audience_leads WHERE {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT id, first_name, last_name, business_email, business_phone,
                           company, company_domain, job_title, seniority, department,
                           personal_phone, wireless_phone, personal_email, linkedin_url,
                           city, state, country, industry, employee_count, revenue,
                           has_verified_business_email, has_verified_personal_email,
                           has_valid_phone, has_wireless_phone, created_at
                    FROM audience_leads WHERE {where}
                    ORDER BY company, last_name, first_name
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], total

    def update_webhook(self, import_id: int, url: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE audience_imports SET webhook_url = ? WHERE id = ?", (url, import_id)
            )

    def total_leads(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM audience_leads").fetchone()[0]

    def stats(self) -> dict:
        with self._conn() as conn:
            total  = conn.execute("SELECT COUNT(*) FROM audience_leads").fetchone()[0]
            imports = conn.execute("SELECT COUNT(*) FROM audience_imports").fetchone()[0]
            with_phone = conn.execute(
                "SELECT COUNT(*) FROM audience_leads WHERE has_valid_phone = 1"
            ).fetchone()[0]
            with_email = conn.execute(
                "SELECT COUNT(*) FROM audience_leads WHERE has_verified_business_email = 1"
            ).fetchone()[0]
            with_wireless = conn.execute(
                "SELECT COUNT(*) FROM audience_leads WHERE has_wireless_phone = 1"
            ).fetchone()[0]
        return {
            "total_leads":   total,
            "total_imports": imports,
            "with_phone":    with_phone,
            "with_email":    with_email,
            "with_wireless": with_wireless,
        }
