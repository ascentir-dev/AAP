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
CREATE TABLE IF NOT EXISTS sms_sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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
    error           TEXT,
    -- timestamp columns ---------------------------------------------------------
    sent_at         REAL,   -- actual Twilio send time (NULL until Phase 2 confirms)
    created_at      REAL,
    updated_at      REAL,
    -- cost columns ---------------------------------------------------------------
    ai_cost_usd     REAL DEFAULT 0.0,   -- Claude API spend for this lead's body
    twilio_cost_usd REAL DEFAULT 0.0    -- actual Twilio charge (filled via reconcile)
);

CREATE TABLE IF NOT EXISTS sms_messages (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id           TEXT    NOT NULL,
    direction         TEXT    NOT NULL,  -- 'outbound' | 'inbound'
    from_number       TEXT,
    to_number         TEXT,
    body              TEXT    NOT NULL,
    twilio_sid        TEXT    UNIQUE,
    variant_id        TEXT,
    sent_at           REAL    NOT NULL,
    -- Twilio billing (often null at creation; populated via status callback / reconcile)
    twilio_price      REAL,
    twilio_price_unit TEXT,
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
        # Migrate: add any columns that may be missing from older DBs.
        # Each ALTER is safe to run multiple times — errors mean "already exists".
        _lead_migrations = [
            "ALTER TABLE sms_leads ADD COLUMN error TEXT",
            "ALTER TABLE sms_leads ADD COLUMN sent_at REAL",
            "ALTER TABLE sms_leads ADD COLUMN ai_cost_usd REAL DEFAULT 0.0",
            "ALTER TABLE sms_leads ADD COLUMN twilio_cost_usd REAL DEFAULT 0.0",
        ]
        _msg_migrations = [
            "ALTER TABLE sms_messages ADD COLUMN twilio_price REAL",
            "ALTER TABLE sms_messages ADD COLUMN twilio_price_unit TEXT",
        ]
        for stmt in _lead_migrations + _msg_migrations:
            try:
                self._conn.execute(stmt)
                self._conn.commit()
            except Exception:
                pass  # column already exists

    # ------------------------------------------------------------------
    # Lead management
    # ------------------------------------------------------------------

    def upsert_lead(self, lead_id: str, **fields: Any) -> None:
        """Insert or update a lead record."""
        allowed = {
            "first_name", "last_name", "phone", "company", "role",
            "vertical", "motion", "assigned_number", "variant_id",
            "test_id", "framework", "status", "error",
            "sent_at", "ai_cost_usd", "twilio_cost_usd",
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
        """Return all sent/received messages for a lead, oldest first.

        Excludes 'outbound_pending' direction — those are pre-generated bodies
        stored before Twilio sends them.  Only 'outbound' (confirmed sent, has
        a twilio_sid) and 'inbound' (replies from the lead) are shown.
        """
        rows = self._conn.execute(
            """
            SELECT * FROM sms_messages
            WHERE lead_id=? AND direction IN ('outbound', 'inbound')
            ORDER BY sent_at ASC
            """,
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
        """Per-variant sent/replied/booked counts.

        'sent' = leads actually delivered via Twilio (status IN sent/replied/booked/opted_out).
        'generated' = all records that have a body (ready + above), for reference.
        """
        where = "WHERE l.test_id = ?" if test_id else ""
        params = (test_id,) if test_id else ()
        rows = self._conn.execute(
            f"""
            SELECT
                l.variant_id,
                l.framework,
                -- only count rows that Twilio actually sent
                SUM(CASE WHEN l.status IN ('sent','replied','booked','opted_out') THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN l.status IN ('replied','booked')                    THEN 1 ELSE 0 END) AS replied,
                SUM(CASE WHEN l.status = 'booked'                                 THEN 1 ELSE 0 END) AS booked,
                SUM(CASE WHEN l.status = 'opted_out'                              THEN 1 ELSE 0 END) AS opted_out,
                -- generation count (includes ready leads not yet sent)
                SUM(CASE WHEN l.status IN ('ready','sent','replied','booked','opted_out') THEN 1 ELSE 0 END) AS generated
            FROM sms_leads l
            {where}
            GROUP BY l.variant_id, l.framework
            ORDER BY replied DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def number_stats(self) -> list[dict[str, Any]]:
        """Per-phone-number sent/replied counts.

        'sent' counts only messages Twilio actually delivered, NOT generated-but-unsent.
        """
        rows = self._conn.execute(
            """
            SELECT
                assigned_number,
                COUNT(*)                                                                              AS total_leads,
                SUM(CASE WHEN status IN ('sent','replied','booked','opted_out') THEN 1 ELSE 0 END)   AS sent,
                SUM(CASE WHEN status IN ('replied','booked')                    THEN 1 ELSE 0 END)   AS replied,
                SUM(CASE WHEN status = 'booked'                                 THEN 1 ELSE 0 END)   AS booked,
                SUM(CASE WHEN status = 'opted_out'                              THEN 1 ELSE 0 END)   AS opted_out
            FROM sms_leads
            WHERE assigned_number IS NOT NULL
            GROUP BY assigned_number
            ORDER BY assigned_number
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def kpi_summary(self) -> dict[str, Any]:
        """Top-level KPI numbers for the dashboard header.

        'sent'      = messages Twilio actually delivered (status IN sent/replied/booked/opted_out).
        'generated' = bodies written and stored (ready + above) — useful for pipeline progress.
        """
        row = self._conn.execute(
            """
            SELECT
                COUNT(*)                                                                            AS total,
                -- actually sent via Twilio
                SUM(CASE WHEN status IN ('sent','replied','booked','opted_out') THEN 1 ELSE 0 END) AS sent,
                -- generated/ready (bodies written, may not be sent yet)
                SUM(CASE WHEN status IN ('ready','sent','replied','booked','opted_out') THEN 1 ELSE 0 END) AS generated,
                SUM(CASE WHEN status IN ('replied','booked')  THEN 1 ELSE 0 END) AS replied,
                SUM(CASE WHEN status = 'booked'               THEN 1 ELSE 0 END) AS booked,
                SUM(CASE WHEN status = 'opted_out'            THEN 1 ELSE 0 END) AS opted_out,
                SUM(CASE WHEN status = 'failed'               THEN 1 ELSE 0 END) AS failed,
                -- cost aggregates
                COALESCE(SUM(ai_cost_usd),     0.0) AS total_ai_cost_usd,
                COALESCE(SUM(twilio_cost_usd), 0.0) AS total_twilio_cost_usd
            FROM sms_leads
            """
        ).fetchone()
        d = dict(row)
        sent    = d["sent"]    or 0
        replied = d["replied"] or 0
        booked  = d["booked"]  or 0
        d["reply_rate"] = round(replied / sent * 100, 2) if sent else 0.0
        d["book_rate"]  = round(booked  / sent * 100, 2) if sent else 0.0
        return d

    def mark_sent(self, lead_id: str, sent_at: float | None = None) -> None:
        """Mark a lead as sent-via-Twilio with an accurate timestamp.

        Using a dedicated method (rather than update_status) ensures sent_at
        is only ever populated after Twilio confirms the send, not at generation
        time.
        """
        now = time.time()
        self._conn.execute(
            "UPDATE sms_leads SET status='sent', updated_at=?, sent_at=? WHERE lead_id=?",
            (now, sent_at or now, lead_id),
        )
        self._conn.commit()

    def set_message_price(
        self,
        twilio_sid: str,
        price: float | None,
        price_unit: str | None = "USD",
    ) -> None:
        """Record the Twilio price for a sent message.

        Called either at send time (price is usually null then) or via the
        reconcile endpoint once the message reaches a final Twilio status.
        Also rolls the price into the parent lead's twilio_cost_usd.
        """
        if price is None:
            return
        price_abs = abs(float(price))   # Twilio returns negative values
        self._conn.execute(
            "UPDATE sms_messages SET twilio_price=?, twilio_price_unit=? WHERE twilio_sid=?",
            (price_abs, price_unit or "USD", twilio_sid),
        )
        # Roll cost into the lead record
        self._conn.execute(
            """
            UPDATE sms_leads
               SET twilio_cost_usd = COALESCE(twilio_cost_usd, 0.0) + ?
             WHERE lead_id = (
                SELECT lead_id FROM sms_messages WHERE twilio_sid = ? LIMIT 1
             )
            """,
            (price_abs, twilio_sid),
        )
        self._conn.commit()

    def cost_summary(self) -> dict[str, float]:
        """Aggregate AI + Twilio costs across all leads."""
        row = self._conn.execute(
            """
            SELECT
                COALESCE(SUM(ai_cost_usd),     0.0) AS ai_cost,
                COALESCE(SUM(twilio_cost_usd), 0.0) AS twilio_cost
            FROM sms_leads
            """
        ).fetchone()
        d = dict(row)
        d["total_cost"] = d["ai_cost"] + d["twilio_cost"]
        return d

    def fetch_unsettled_sids(self, limit: int = 100) -> list[str]:
        """Return SIDs of outbound messages whose Twilio price is still null.

        Used by the /api/sms/reconcile-costs endpoint to fetch prices in bulk.
        """
        rows = self._conn.execute(
            """
            SELECT twilio_sid FROM sms_messages
             WHERE direction = 'outbound'
               AND twilio_sid IS NOT NULL
               AND twilio_price IS NULL
             ORDER BY sent_at DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [r["twilio_sid"] for r in rows]

    # ------------------------------------------------------------------
    # Opt-out
    # ------------------------------------------------------------------

    def is_opted_out(self, phone: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sms_leads WHERE phone=? AND status='opted_out' LIMIT 1",
            (phone,),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Sync state — used by the Twilio polling worker
    # ------------------------------------------------------------------

    def get_sync_state(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM sms_sync_state WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_sync_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO sms_sync_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    def sid_exists(self, twilio_sid: str) -> bool:
        """Fast check — has this Twilio SID already been recorded?"""
        row = self._conn.execute(
            "SELECT 1 FROM sms_messages WHERE twilio_sid=? LIMIT 1", (twilio_sid,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()
