import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    simulated INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'indexed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    context_header TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    root_cause TEXT,
    component TEXT,
    alarm_code TEXT,
    status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    source TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_incidents_alarm ON incidents(alarm_code);
CREATE INDEX IF NOT EXISTS idx_incidents_component ON incidents(component);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    machine_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    component TEXT,
    signal TEXT,
    value TEXT,
    technician_action TEXT,
    outcome TEXT,
    source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_incident_ts ON events(incident_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_component_ts ON events(component, ts);

CREATE TABLE IF NOT EXISTS statements (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    machine_id TEXT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    statement TEXT NOT NULL,
    temporal_type TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    t_created TEXT NOT NULL,
    t_valid TEXT,
    t_invalid TEXT,
    t_expired TEXT,
    invalidated_by TEXT,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_statements_subject ON statements(subject, predicate);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    scenario_id TEXT,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_events (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    verification TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    incident_id TEXT,
    title TEXT NOT NULL,
    priority TEXT NOT NULL,
    component TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    config TEXT NOT NULL,
    summary TEXT
);
"""

_lock = threading.RLock()
_connection: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        settings = get_settings()
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(settings.db_path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


def init_db() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with _lock:
        rows = _connect().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with transaction() as conn:
        cursor = conn.execute(sql, tuple(params))
        return cursor.lastrowid or 0


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)
