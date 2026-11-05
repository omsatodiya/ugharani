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
);

-- The owner's follow-up rules, one row per setting (see followup.DEFAULTS).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Contact details for buyers in the ledger; matched to entries.buyer by name.
CREATE TABLE IF NOT EXISTS customers (
    name       TEXT PRIMARY KEY,       -- the person, as the trader says it ('રમેશભાઈ')
    firm       TEXT,                   -- their shop ('શ્રીજી હાર્ડવેર')
    city       TEXT,
    phone      TEXT,
    deals_with TEXT,                       -- who at the business they deal with
    auto_call  INTEGER NOT NULL DEFAULT 1  -- 0: the owner handles this one personally
);

-- Every follow-up call the agent placed, and what came of it.
CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY,
    customer        TEXT NOT NULL,
    trigger         TEXT NOT NULL CHECK (trigger IN ('auto', 'manual')),
    status          TEXT NOT NULL DEFAULT 'ringing'
                    CHECK (status IN ('ringing', 'in_progress', 'completed', 'missed', 'declined', 'failed')),
    amount_due      INTEGER NOT NULL,  -- what was pending when the call was placed
    outcome         TEXT CHECK (outcome IN ('promised', 'paid', 'dispute', 'callback', 'handover', 'refused', 'unclear')),
    promised_amount INTEGER,
    promised_date   TEXT,
    summary         TEXT,
    transcript      TEXT,              -- JSON list of {"who": "agent"|"customer", "text": ...}
    recording       TEXT,              -- file name in the recordings dir
    flags           TEXT,              -- JSON list: what the agent's checker stopped her saying, for the owner
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at        TEXT
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or ledger_db_path())
    conn.row_factory = sqlite3.Row
    # WAL + NORMAL: commits don't wait on a full disk sync (still safe against app crashes).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.executescript(SCHEMA)
    if "flags" not in {r["name"] for r in conn.execute("PRAGMA table_info(calls)")}:  # (older databases)
        conn.execute("ALTER TABLE calls ADD COLUMN flags TEXT")
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
