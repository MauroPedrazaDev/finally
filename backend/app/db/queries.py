"""Data access functions for all tables (single user: "default").

Functions taking ``conn`` run inside the caller's transaction when given one;
otherwise they open a short-lived connection (autocommit).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .connection import DEFAULT_USER, format_ts, now_iso, use_conn


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_cost: float
    updated_at: str


def _new_id() -> str:
    return str(uuid.uuid4())


# --- profile -----------------------------------------------------------------


def get_cash(conn: sqlite3.Connection | None = None) -> float:
    with use_conn(conn) as c:
        row = c.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER,)
        ).fetchone()
    if row is None:
        raise RuntimeError("User profile missing; call init_db() first")
    return float(row["cash_balance"])


def set_cash(conn: sqlite3.Connection, value: float) -> None:
    conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (float(value), DEFAULT_USER)
    )


# --- watchlist ---------------------------------------------------------------


def list_watchlist(conn: sqlite3.Connection | None = None) -> list[str]:
    """Watchlist tickers ordered by added_at (rowid breaks same-second ties)."""
    with use_conn(conn) as c:
        rows = c.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (DEFAULT_USER,),
        ).fetchall()
    return [r["ticker"] for r in rows]


def is_on_watchlist(ticker: str, conn: sqlite3.Connection | None = None) -> bool:
    with use_conn(conn) as c:
        row = c.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker)
        ).fetchone()
    return row is not None


def add_to_watchlist(ticker: str, conn: sqlite3.Connection | None = None) -> bool:
    """Insert the ticker; returns False if it was already present."""
    with use_conn(conn) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (_new_id(), DEFAULT_USER, ticker, now_iso()),
        )
    return cur.rowcount == 1


def remove_from_watchlist(ticker: str, conn: sqlite3.Connection | None = None) -> bool:
    """Delete the ticker; returns False if it was not present."""
    with use_conn(conn) as c:
        cur = c.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker)
        )
    return cur.rowcount > 0


# --- positions ---------------------------------------------------------------


def _position(row: sqlite3.Row) -> Position:
    return Position(
        ticker=row["ticker"],
        quantity=float(row["quantity"]),
        avg_cost=float(row["avg_cost"]),
        updated_at=row["updated_at"],
    )


def list_positions(conn: sqlite3.Connection | None = None) -> list[Position]:
    with use_conn(conn) as c:
        rows = c.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id = ? ORDER BY ticker",
            (DEFAULT_USER,),
        ).fetchall()
    return [_position(r) for r in rows]


def get_position(ticker: str, conn: sqlite3.Connection | None = None) -> Position | None:
    with use_conn(conn) as c:
        row = c.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER, ticker),
        ).fetchone()
    return _position(row) if row else None


def upsert_position(
    conn: sqlite3.Connection, ticker: str, quantity: float, avg_cost: float
) -> None:
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, ticker) DO UPDATE SET "
        "quantity = excluded.quantity, avg_cost = excluded.avg_cost, "
        "updated_at = excluded.updated_at",
        (_new_id(), DEFAULT_USER, ticker, float(quantity), float(avg_cost), now_iso()),
    )


def delete_position(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (DEFAULT_USER, ticker))


# --- trades ------------------------------------------------------------------


def insert_trade(
    conn: sqlite3.Connection, ticker: str, side: str, quantity: float, price: float
) -> str:
    """Append a trade; returns its executed_at timestamp."""
    executed_at = now_iso()
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_new_id(), DEFAULT_USER, ticker, side, float(quantity), float(price), executed_at),
    )
    return executed_at


def last_trade_prices(tickers: list[str] | None = None) -> dict[str, float]:
    """Most recent trade price per ticker (optionally restricted to ``tickers``)."""
    with use_conn(None) as c:
        rows = c.execute(
            "SELECT ticker, price FROM trades WHERE user_id = ? ORDER BY executed_at, rowid",
            (DEFAULT_USER,),
        ).fetchall()
    wanted = set(tickers) if tickers is not None else None
    # Ascending order: later rows overwrite earlier ones, leaving the latest price.
    return {
        r["ticker"]: float(r["price"]) for r in rows if wanted is None or r["ticker"] in wanted
    }


# --- tracked tickers ---------------------------------------------------------


def tracked_tickers() -> list[str]:
    """Watchlist ∪ open positions: watchlist order first, then extra held tickers."""
    with use_conn(None) as c:
        watch = list_watchlist(c)
        held = [p.ticker for p in list_positions(c)]
    seen = set(watch)
    return watch + [t for t in held if t not in seen]


# --- snapshots ---------------------------------------------------------------


def insert_snapshot(total_value: float, conn: sqlite3.Connection | None = None) -> None:
    with use_conn(conn) as c:
        c.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (_new_id(), DEFAULT_USER, float(total_value), now_iso()),
        )


def downsample(items: list, max_points: int) -> list:
    """Evenly spaced (by index) subset of at most max_points, keeping first and last."""
    n = len(items)
    if n <= max_points:
        return list(items)
    if max_points <= 1:
        return [items[-1]] if max_points == 1 else []
    # Step > 1 because n > max_points, so the rounded indices are strictly increasing.
    step = (n - 1) / (max_points - 1)
    return [items[round(i * step)] for i in range(max_points)]


def get_history(hours: float = 24, max_points: int = 500) -> list[dict]:
    """Snapshots from the last ``hours``, oldest first, downsampled to ``max_points``."""
    cutoff = format_ts(datetime.now(UTC) - timedelta(hours=hours))
    with use_conn(None) as c:
        rows = c.execute(
            "SELECT recorded_at, total_value FROM portfolio_snapshots "
            "WHERE user_id = ? AND recorded_at >= ? ORDER BY recorded_at, rowid",
            (DEFAULT_USER, cutoff),
        ).fetchall()
    points = [{"recorded_at": r["recorded_at"], "total_value": float(r["total_value"])} for r in rows]
    return downsample(points, max_points)


# --- chat --------------------------------------------------------------------


def insert_chat_message(
    role: str,
    content: str,
    actions: list[dict] | None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Store a chat message; actions is None for user messages, a list for assistant ones."""
    encoded = None if actions is None else json.dumps(actions)
    with use_conn(conn) as c:
        c.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_new_id(), DEFAULT_USER, role, content, encoded, now_iso()),
        )


def recent_chat_messages(limit: int = 50) -> list[dict]:
    """The last ``limit`` messages, oldest first, with actions decoded from JSON."""
    with use_conn(None) as c:
        rows = c.execute(
            "SELECT role, content, actions, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (DEFAULT_USER, limit),
        ).fetchall()
    return [
        {
            "role": r["role"],
            "message": r["content"],
            "actions": None if r["actions"] is None else json.loads(r["actions"]),
            "created_at": r["created_at"],
        }
        for r in reversed(rows)
    ]
