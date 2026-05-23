"""
SMS-only SQLite ledger — completely separate from the email pipeline ledger.

File: data/sms_ledger.sqlite
Tables: sms_leads, sms_messages

Design principles:
- Zero coupling to the email ledger (different file, different schema)
- Thread-safe for concurrent reads from the dashboard
- Simple upsert pattern, same style as src/utils/ledger.py
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sms_leads (
    lead_id         TEXT PRIMARY KEY,
    first_name      TEXT,
    last_name       TEXT,
    phone           TEXT NOT NULL,
    company         TEXT,
    role            TEXT,
    vertical        TEXT,
    motion          TEXT,
    assigned_number TEXT,
    variant_id      TEXT,
    test_id         TEXT,
    framework       TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      REAL,
    updated_at      REAL
);

CREATE TABLE IF NOT EXISTS sms_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     TEXT    NOT NULL,
    direction   TEXT    NOT NULL,  -- 'outbound' | 'inbound'
    from_number TEXT,
    to_number   TEXT,
    body        TEXT    NOT NULL,
    twilio_sid  TEXT    UNIQUE,
    variant_id  TEXT,
    sent_at     REAL    NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES sms_leads(lead_id)
);

CREATE INDEX IF NOT EXISTS idx_sms_msg_lead      ON sms_messages(lead_id);
CREATE INDEX IF NOT EXISTS idx_sms_msg_sent_at   ON sms_messages(sent_at);
CREATE INDEX IF NOT EXISTS idx_sms_leads_phone   ON sms_leads(phone);
CREATE INDEX IF NOT EXISTS idx_sms_leads_number  ON sms_leads(assigned_number);
CREATE INDEX IF NOT EXISTS idx_sms_leads_status  ON sms_leads(status);
"""

_VALID_STATUSES = frozenset(
    {"pending", "sent", "replied", "booked", "opted_out", "failed"}
)


class SMSLedger:
    """Thread-safe SQLite ledger for the SMS pipeline."""

    def __init__(self, path: str = "data/sms_ledger.sqlite") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lead management
    # ------------------------------------------------------------------

    def upsert_lead(self, lead_id: str, **fields: Any) -> None:
        """Insert or update a lead record."""
        allowed = {
            "first_name", "last_name", "phone", "company", "role",
            "vertical", "motion", "assigned_number", "variant_id",
            "test_id", "framework", "status",
        }
        valid = {k: v for k, v in fields.items() if k in allowed}
        now = time.time()

        cols = ", ".join(["lead_id", "created_at", "updated_at"] + list(valid.keys()))
        placeholders = ", ".join(["?", "?", "?"] + ["?" for _ in valid])
        updates = ", ".join(
            [f"{k}=excluded.{k}" for k in valid] + ["updated_at=excluded.updated_at"]
        )
        values = [lead_id, now, now] + list(valid.values())

        self._conn.execute(
            f"""
            INSERT INTO sms_leads ({cols})
            VALUES ({placeholders})
            ON CONFLICT(lead_id) DO UPDATE SET {updates}
            """,
            values,
        )
        self._conn.commit()

    def update_status(self, lead_id: str, status: str) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid SMS lead status: {status!r}")
        self._conn.execute(
            "UPDATE sms_leads SET status=?, updated_at=? WHERE lead_id=?",
            (status, time.time(), lead_id),
        )
        self._conn.commit()

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sms_leads WHERE lead_id=?", (lead_id,)
        ).fetchone()
        return dict(row) if row else None

    def lead_id_for_phone(self, phone: str) -> str | None:
        """Look up a lead by their phone number — used for inbound reply matching."""
        row = self._conn.execute(
            "SELECT lead_id FROM sms_leads WHERE phone=? LIMIT 1", (phone,)
        ).fetchone()
        return row["lead_id"] if row else None

    def list_leads(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM sms_leads WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM sms_leads ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_leads(self, status: str | None = None) -> int:
        if status:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM sms_leads WHERE status=?", (status,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM sms_leads"
            ).fetchone()
        return row["n"]

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    def record_message(
        self,
        lead_id: str,
        direction: str,
        from_number: str,
        to_number: str,
        body: str,
        twilio_sid: str | None = None,
        variant_id: str | None = None,
    ) -> int:
        """Insert a message record and return its row id."""
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO sms_messages
                (lead_id, direction, from_number, to_number, body, twilio_sid, variant_id, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (lead_id, direction, from_number, to_number, body, twilio_sid, variant_id, time.time()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_conversation(self, lead_id: str) -> list[dict[str, Any]]:
        """Return all messages for a lead, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM sms_messages WHERE lead_id=? ORDER BY sent_at ASC",
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def last_inbound(self, lead_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sms_messages WHERE lead_id=? AND direction='inbound' ORDER BY sent_at DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Analytics aggregates
    # ------------------------------------------------------------------

    def variant_stats(self, test_id: str | None = None) -> list[dict[str, Any]]:
        """Per-variant sent/replied/booked counts."""
        where = "WHERE l.test_id = ?" if test_id else ""
        params = (test_id,) if test_id else ()
        rows = self._conn.execute(
            f"""
            SELECT
                l.variant_id,
                l.framework,
                COUNT(DISTINCT l.lead_id)                                          AS sent,
                SUM(CASE WHEN l.status IN ('replied','booked') THEN 1 ELSE 0 END) AS replied,
                SUM(CASE WHEN l.status = 'booked' THEN 1 ELSE 0 END)              AS booked,
                SUM(CASE WHEN l.status = 'opted_out' THEN 1 ELSE 0 END)           AS opted_out
            FROM sms_leads l
            {where}
            GROUP BY l.variant_id, l.framework
            ORDER BY replied DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def number_stats(self) -> list[dict[str, Any]]:
        """Per-phone-number sent/replied counts."""
        rows = self._conn.execute(
            """
            SELECT
                assigned_number,
                COUNT(*)                                                           AS total_leads,
                SUM(CASE WHEN status NOT IN ('pending','failed') THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN status IN ('replied','booked') THEN 1 ELSE 0 END)   AS replied,
                SUM(CASE WHEN status = 'booked' THEN 1 ELSE 0 END)               AS booked,
                SUM(CASE WHEN status = 'opted_out' THEN 1 ELSE 0 END)            AS opted_out
            FROM sms_leads
            WHERE assigned_number IS NOT NULL
            GROUP BY assigned_number
            ORDER BY assigned_number
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def kpi_summary(self) -> dict[str, Any]:
        """Top-level KPI numbers for the dashboard header."""
        row = self._conn.execute(
            """
            SELECT
                COUNT(*)                                                           AS total,
                SUM(CASE WHEN status NOT IN ('pending','failed') THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN status IN ('replied','booked') THEN 1 ELSE 0 END)   AS replied,
                SUM(CASE WHEN status = 'booked' THEN 1 ELSE 0 END)               AS booked,
                SUM(CASE WHEN status = 'opted_out' THEN 1 ELSE 0 END)            AS opted_out
            FROM sms_leads
            """
        ).fetchone()
        d = dict(row)
        sent = d["sent"] or 0
        replied = d["replied"] or 0
        booked = d["booked"] or 0
        d["reply_rate"] = round(replied / sent * 100, 2) if sent else 0.0
        d["book_rate"]  = round(booked  / sent * 100, 2) if sent else 0.0
        return d

    # ------------------------------------------------------------------
    # Opt-out
    # ------------------------------------------------------------------

    def is_opted_out(self, phone: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sms_leads WHERE phone=? AND status='opted_out' LIMIT 1",
            (phone,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()
