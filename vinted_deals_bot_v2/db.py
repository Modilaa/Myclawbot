"""
Couche base de données — SQLite avec métriques intégrées.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


@dataclass
class DealRecord:
    item_id: str
    title: str
    vinted_price: float
    market_price: float
    margin: float
    url: str
    keyword: str
    seen_at: str
    alerted: bool = False


class Database:
    def __init__(self, path: str = "deals.db"):
        self.path = path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS seen_items (
                    item_id       TEXT PRIMARY KEY,
                    title         TEXT NOT NULL,
                    vinted_price  REAL,
                    market_price  REAL,
                    margin        REAL,
                    url           TEXT,
                    keyword       TEXT,
                    seen_at       TEXT NOT NULL,
                    alerted       INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    item_id   TEXT PRIMARY KEY,
                    sent_at   TEXT NOT NULL,
                    channel   TEXT DEFAULT 'telegram'
                );

                CREATE TABLE IF NOT EXISTS cycle_stats (
                    cycle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at    TEXT NOT NULL,
                    finished_at   TEXT,
                    keywords_used TEXT,
                    items_scraped INTEGER DEFAULT 0,
                    items_scored  INTEGER DEFAULT 0,
                    deals_found   INTEGER DEFAULT 0,
                    alerts_sent   INTEGER DEFAULT 0,
                    errors        INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_seen_at ON seen_items(seen_at);
                CREATE INDEX IF NOT EXISTS idx_keyword ON seen_items(keyword);
            """)

    # --- Items ---

    def was_seen(self, item_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,)
            ).fetchone()
            return row is not None

    def mark_seen(self, record: DealRecord):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO seen_items
                    (item_id, title, vinted_price, market_price, margin, url, keyword, seen_at, alerted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.item_id, record.title, record.vinted_price,
                record.market_price, record.margin, record.url,
                record.keyword, record.seen_at, int(record.alerted)
            ))

    # --- Alerts ---

    def can_alert(self, item_id: str, cooldown_min: int = 120) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sent_at FROM alerts WHERE item_id = ?", (item_id,)
            ).fetchone()
            if not row:
                return True
            sent_at = datetime.fromisoformat(row["sent_at"])
            return (datetime.now(timezone.utc) - sent_at) > timedelta(minutes=cooldown_min)

    def mark_alerted(self, item_id: str, channel: str = "telegram"):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO alerts (item_id, sent_at, channel) VALUES (?, ?, ?)",
                (item_id, datetime.now(timezone.utc).isoformat(), channel)
            )

    # --- Cycle stats ---

    def start_cycle(self, keywords: list[str]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO cycle_stats (started_at, keywords_used) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(), ",".join(keywords))
            )
            return cur.lastrowid

    def end_cycle(self, cycle_id: int, items_scraped: int = 0,
                  items_scored: int = 0, deals_found: int = 0,
                  alerts_sent: int = 0, errors: int = 0):
        with self._conn() as conn:
            conn.execute("""
                UPDATE cycle_stats SET
                    finished_at = ?, items_scraped = ?, items_scored = ?,
                    deals_found = ?, alerts_sent = ?, errors = ?
                WHERE cycle_id = ?
            """, (
                datetime.now(timezone.utc).isoformat(),
                items_scraped, items_scored, deals_found, alerts_sent, errors,
                cycle_id
            ))

    # --- Métriques ---

    def stats_last_24h(self) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with self._conn() as conn:
            cycles = conn.execute(
                "SELECT COUNT(*), SUM(items_scraped), SUM(deals_found), SUM(alerts_sent), SUM(errors) "
                "FROM cycle_stats WHERE started_at > ?", (cutoff,)
            ).fetchone()
            items = conn.execute(
                "SELECT COUNT(*) FROM seen_items WHERE seen_at > ?", (cutoff,)
            ).fetchone()
            return {
                "cycles": cycles[0] or 0,
                "items_scraped": cycles[1] or 0,
                "deals_found": cycles[2] or 0,
                "alerts_sent": cycles[3] or 0,
                "errors": cycles[4] or 0,
                "unique_items_seen": items[0] or 0,
            }
