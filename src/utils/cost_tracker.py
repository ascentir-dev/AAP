"""
SQLite-backed cost ledger. Tracks per-lead, per-vendor API spend.
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT,
    vendor TEXT NOT NULL,
    operation TEXT,
    cost_usd REAL NOT NULL,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_costs_lead ON costs(lead_id);
CREATE INDEX IF NOT EXISTS idx_costs_date ON costs(occurred_at);
"""


class CostTracker:
    def __init__(
        self,
        path: str = "ledger.sqlite",
        daily_budget_usd: float = 50.0,
    ) -> None:
        self._daily_budget = daily_budget_usd
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log(
        self,
        lead_id: str | None,
        vendor: str,
        operation: str,
        cost_usd: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO costs (lead_id, vendor, operation, cost_usd) VALUES (?,?,?,?)",
            (lead_id, vendor, operation, cost_usd),
        )
        self._conn.commit()

    def lead_cost(self, lead_id: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs WHERE lead_id=?",
            (lead_id,),
        ).fetchone()
        return float(row[0])

    def daily_total(self) -> float:
        today = date.today().isoformat()
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs WHERE DATE(occurred_at)=?",
            (today,),
        ).fetchone()
        return float(row[0])

    def total(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM costs"
        ).fetchone()
        return float(row[0])

    def check_budget(self) -> bool:
        """Return True if today's spend is below the daily budget cap."""
        return self.daily_total() < self._daily_budget

    def close(self) -> None:
        self._conn.close()
