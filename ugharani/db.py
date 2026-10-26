"""SQLite ledger: one row per credit given or payment received."""

import sqlite3
from datetime import date

from ugharani.config import ledger_db_path
from ugharani.extract import ParsedEntry
from ugharani.names import match

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (kind IN ('credit', 'payment')),
    buyer      TEXT NOT NULL,
    amount     INTEGER NOT NULL,  -- rupees
    entry_date TEXT NOT NULL,     -- ISO date
    due_date   TEXT,              -- credits only
    transcript TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or ledger_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def known_buyers(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT buyer FROM entries GROUP BY buyer ORDER BY MIN(id)")]


def resolve_buyer(conn: sqlite3.Connection, name: str) -> str:
    """Use the existing spelling if this buyer is already in the ledger."""
    return match(name, known_buyers(conn)) or name


def add_entry(conn: sqlite3.Connection, entry: ParsedEntry, transcript: str, today: date | None = None) -> int:
    if not entry.complete:
        raise ValueError(f"entry is missing {entry.missing}")
    cur = conn.execute(
        "INSERT INTO entries (kind, buyer, amount, entry_date, due_date, transcript) VALUES (?, ?, ?, ?, ?, ?)",
        (
            entry.kind,
            resolve_buyer(conn, entry.buyer),
            entry.amount,
            (today or date.today()).isoformat(),
            entry.due_date.isoformat() if entry.due_date else None,
            transcript,
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM entries ORDER BY id").fetchall()


def balances(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Outstanding amount per buyer: credits given minus payments received."""
    return conn.execute(
        """
        SELECT buyer,
               SUM(CASE kind WHEN 'credit' THEN amount ELSE -amount END) AS balance,
               MIN(CASE WHEN kind = 'credit' THEN due_date END) AS earliest_due
        FROM entries GROUP BY buyer ORDER BY balance DESC
        """
    ).fetchall()
