"""Histórico de cotações em SQLite."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .models import FlightOffer

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  retrieved_at TEXT NOT NULL,
  provider TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  outbound_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  price_per_person REAL NOT NULL,
  total_price REAL NOT NULL,
  currency TEXT NOT NULL,
  total_stops INTEGER,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_quotes_dates ON quotes(outbound_date, return_date);
CREATE INDEX IF NOT EXISTS ix_quotes_fp ON quotes(fingerprint);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sent_at TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  price_per_person REAL NOT NULL,
  reason TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def save_offers(self, offers: list[FlightOffer]) -> None:
        self.db.executemany(
            "INSERT INTO quotes(retrieved_at,provider,fingerprint,outbound_date,return_date,"
            "price_per_person,total_price,currency,total_stops,payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(o.retrieved_at, o.provider, o.fingerprint, str(o.outbound_date), str(o.return_date),
              o.price_per_person, o.total_price, o.currency, o.total_stops, json.dumps(o.to_dict()))
             for o in offers])
        self.db.commit()

    def min_price_before(self, outbound: str, ret: str, before: str, currency: str) -> Optional[float]:
        """Menor preço/pessoa já visto para o par de datas, antes desta execução."""
        row = self.db.execute(
            "SELECT MIN(price_per_person) FROM quotes WHERE outbound_date=? AND return_date=? "
            "AND retrieved_at<? AND currency=?", (outbound, ret, before, currency)).fetchone()
        return row[0]

    def last_alert_price(self, fingerprint: str) -> Optional[float]:
        row = self.db.execute("SELECT MIN(price_per_person) FROM alerts WHERE fingerprint=?",
                              (fingerprint,)).fetchone()
        return row[0]

    def record_alert(self, fingerprint: str, price: float, reason: str, sent_at: str) -> None:
        self.db.execute("INSERT INTO alerts(sent_at,fingerprint,price_per_person,reason) VALUES (?,?,?,?)",
                        (sent_at, fingerprint, price, reason))
        self.db.commit()

    def history(self, outbound: str, ret: str) -> list[tuple]:
        """(dia, menor preço/pessoa) por dia para o par de datas."""
        return self.db.execute(
            "SELECT substr(retrieved_at,1,10) d, MIN(price_per_person), COUNT(*) FROM quotes "
            "WHERE outbound_date=? AND return_date=? GROUP BY d ORDER BY d", (outbound, ret)).fetchall()
