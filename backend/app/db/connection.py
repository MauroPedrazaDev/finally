"""SQLite connection handling: path resolution, pragmas, transactions, timestamps."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_USER = "default"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# backend/app/db/connection.py -> parents[3] is the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_db_path() -> Path:
    """Return the SQLite file path (DB_PATH env, read at call time) and ensure its directory exists."""
    raw = os.environ.get("DB_PATH", "").strip()
    path = Path(raw) if raw else _PROJECT_ROOT / "db" / "finally.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    """Current UTC time as YYYY-MM-DDTHH:MM:SSZ."""
    return format_ts(datetime.now(UTC))


def format_ts(dt: datetime) -> str:
    """Format an aware datetime as a UTC timestamp string."""
    return dt.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def connect() -> sqlite3.Connection:
    """Open a new connection in autocommit mode with the project pragmas.

    Autocommit (isolation_level=None) means single statements commit immediately;
    multi-statement atomicity goes through transaction().
    """
    conn = sqlite3.connect(get_db_path(), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE; commit on success, rollback on exception, always close."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
    finally:
        conn.close()


@contextmanager
def use_conn(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    """Yield the caller's connection, or open (and close) a short-lived one."""
    if conn is not None:
        yield conn
        return
    own = connect()
    try:
        yield own
    finally:
        own.close()
