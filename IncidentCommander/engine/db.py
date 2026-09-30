"""SQLite event store. Later phases add their tables to SCHEMA."""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .config import DB_PATH
from .models import Candidate, Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
    job_id TEXT, task_id TEXT, session_id TEXT,
    major_type TEXT, minor_type TEXT, raw_type_keyword TEXT,
    raw_fields TEXT, severity TEXT, raw_text TEXT, source TEXT, line_no INTEGER
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(timestamp);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY, source TEXT, type TEXT,
    trigger_event_id TEXT, trigger_ts TEXT, window_start TEXT, window_end TEXT,
    hit_count INTEGER, keywords TEXT, demo INTEGER, description TEXT
);
CREATE TABLE IF NOT EXISTS correlation_runs (
    incident_id TEXT PRIMARY KEY, created TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS rca_results (
    incident_id TEXT PRIMARY KEY, created TEXT, result TEXT
);
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_events(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    rows = [e.as_row() for e in events]
    conn.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def load_events(conn: sqlite3.Connection, start: Optional[datetime] = None,
                end: Optional[datetime] = None) -> list:
    q, args = "SELECT * FROM events WHERE 1=1", []
    if start:
        q += " AND timestamp >= ?"; args.append(start.isoformat(timespec="microseconds"))
    if end:
        q += " AND timestamp <= ?"; args.append(end.isoformat(timespec="microseconds"))
    return [Event.from_row(r) for r in conn.execute(q + " ORDER BY timestamp, line_no", args)]


def save_incidents(conn: sqlite3.Connection, cands: Iterable[Candidate]) -> None:
    import json
    conn.executemany(
        "INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(c.incident_id, c.source, c.type, c.trigger_event_id,
          c.trigger_ts.isoformat(), c.window_start.isoformat(), c.window_end.isoformat(),
          len(c.hits), json.dumps(c.keywords), int(c.demo), c.description) for c in cands],
    )
    conn.commit()
