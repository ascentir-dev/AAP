"""
SQLite-backed lead state tracker. Tracks stages, events, and completion status.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    company TEXT,
    website TEXT,
    role TEXT,
    vertical TEXT,
    motion TEXT,
    intent_confidence INTEGER,
    variant_id TEXT,
    test_id TEXT,
    framework TEXT,
    recommended_angle TEXT,
    email_type TEXT DEFAULT 'video',
    subject_line TEXT DEFAULT '',
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT
);

CREATE TABLE IF NOT EXISTS stages (
    lead_id TEXT,
    stage_name TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lead_id, stage_name)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    smartlead_payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_lead ON events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, occurred_at);

CREATE TABLE IF NOT EXISTS csv_uploads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL,
    csv_path        TEXT    NOT NULL,
    uploaded_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    lead_count      INTEGER DEFAULT 0,
    new_leads       INTEGER DEFAULT 0,
    duplicate_leads INTEGER DEFAULT 0
);
"""


class Ledger:
    def __init__(self, path: str = "ledger.sqlite") -> None:
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL mode: concurrent readers + writers don't block each other.
        # NORMAL sync: safe on power-loss (journal survives fsync), ~3× faster writes.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        # Migration: add email_type to existing databases that predate this column.
        try:
            self._conn.execute("ALTER TABLE leads ADD COLUMN email_type TEXT DEFAULT 'video'")
            self._conn.commit()
        except Exception:
            pass
        # Migration: add subject_line for per-lead subject tracking + analytics.
        try:
            self._conn.execute("ALTER TABLE leads ADD COLUMN subject_line TEXT DEFAULT ''")
            self._conn.commit()
        except Exception:
            pass

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    # ------------------------------------------------------------------
    # Stage operations
    # ------------------------------------------------------------------
    def has_stage(self, lead_id: str, stage_name: str) -> bool:
        row = self._execute(
            "SELECT 1 FROM stages WHERE lead_id=? AND stage_name=?",
            (lead_id, stage_name),
        ).fetchone()
        return row is not None

    def save_stage(self, lead_id: str, stage_name: str, data: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO stages (lead_id, stage_name, data_json)
            VALUES (?, ?, ?)
            ON CONFLICT(lead_id, stage_name) DO UPDATE SET
                data_json=excluded.data_json,
                created_at=CURRENT_TIMESTAMP
            """,
            (lead_id, stage_name, json.dumps(data)),
        )
        self._conn.commit()

    def get_stage(self, lead_id: str, stage_name: str) -> dict[str, Any] | None:
        row = self._execute(
            "SELECT data_json FROM stages WHERE lead_id=? AND stage_name=?",
            (lead_id, stage_name),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError) as e:
            log.error("Corrupt stage data for lead=%s stage=%s — returning None. Error: %s",
                      lead_id, stage_name, e)
            return None

    # ------------------------------------------------------------------
    # Lead lifecycle
    # ------------------------------------------------------------------
    def is_complete(self, lead_id: str) -> bool:
        row = self._execute(
            "SELECT status FROM leads WHERE lead_id=?", (lead_id,)
        ).fetchone()
        if row is None:
            return False
        return row["status"] in ("sent", "dry_run", "skipped", "success")

    def mark_complete(self, lead_id: str, status: str = "success") -> None:
        self._execute(
            """
            INSERT INTO leads (lead_id, email, status, completed_at)
            VALUES (?, '', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lead_id) DO UPDATE SET
                status=excluded.status,
                completed_at=excluded.completed_at
            """,
            (lead_id, status),
        )
        self._conn.commit()

    def mark_failed(self, lead_id: str, error: str) -> None:
        self._execute(
            """
            INSERT INTO leads (lead_id, email, status, error, completed_at)
            VALUES (?, '', 'failed', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lead_id) DO UPDATE SET
                status='failed',
                error=excluded.error,
                completed_at=excluded.completed_at
            """,
            (lead_id, error),
        )
        self._conn.commit()

    def save_lead_metadata(self, lead_id: str, **fields: Any) -> None:
        """Upsert arbitrary fields into the leads table."""
        allowed = {
            "email", "first_name", "last_name", "company", "website", "role",
            "vertical", "motion", "intent_confidence", "variant_id", "test_id",
            "framework", "recommended_angle", "email_type", "subject_line", "status",
        }
        valid = {k: v for k, v in fields.items() if k in allowed}
        # Ensure email is always present (required NOT NULL column)
        if "email" not in valid:
            valid["email"] = ""

        cols = ", ".join(valid.keys())
        placeholders = ", ".join("?" for _ in valid)
        updates = ", ".join(f"{k}=excluded.{k}" for k in valid)
        values = list(valid.values())

        self._execute(
            f"""
            INSERT INTO leads (lead_id, {cols})
            VALUES (?, {placeholders})
            ON CONFLICT(lead_id) DO UPDATE SET {updates}
            """,
            (lead_id, *values),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Events (webhook callbacks)
    # ------------------------------------------------------------------
    def record_event(
        self,
        lead_id: str,
        event_type: str,
        occurred_at: datetime,
        smartlead_payload: dict[str, Any],
    ) -> None:
        self._execute(
            """
            INSERT INTO events (lead_id, event_type, occurred_at, smartlead_payload)
            VALUES (?, ?, ?, ?)
            """,
            (lead_id, event_type, occurred_at.isoformat(), json.dumps(smartlead_payload)),
        )
        self._conn.commit()

    def lead_id_for_email(self, email: str) -> str | None:
        row = self._execute(
            "SELECT lead_id FROM leads WHERE email=? LIMIT 1", (email,)
        ).fetchone()
        return row["lead_id"] if row else None

    # ------------------------------------------------------------------
    # CSV upload history
    # ------------------------------------------------------------------
    def record_csv_upload(
        self,
        filename: str,
        csv_path: str,
        lead_count: int,
        new_leads: int,
        duplicate_leads: int,
    ) -> int:
        """Insert a row into csv_uploads and return the new row id."""
        cur = self._execute(
            """
            INSERT INTO csv_uploads (filename, csv_path, lead_count, new_leads, duplicate_leads)
            VALUES (?, ?, ?, ?, ?)
            """,
            (filename, csv_path, lead_count, new_leads, duplicate_leads),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def close(self) -> None:
        self._conn.close()
