"""Tests for app.db: init/seed, CRUD, transactions, history, chat."""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.db.connection import format_ts

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _execute(sql: str, params: tuple = ()) -> None:
    conn = db.connect()
    try:
        conn.execute(sql, params)
    finally:
        conn.close()


def _insert_snapshot_at(when: datetime, value: float) -> None:
    _execute(
        "INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES (?, ?, ?)",
        (str(uuid.uuid4()), value, format_ts(when)),
    )


class TestPathAndInit:
    def test_db_path_from_env_creates_parent(self, tmp_path, monkeypatch):
        target = tmp_path / "nested" / "dir" / "x.db"
        monkeypatch.setenv("DB_PATH", str(target))
        assert db.get_db_path() == target
        assert target.parent.is_dir()

    def test_default_path_is_project_db(self, monkeypatch):
        monkeypatch.delenv("DB_PATH", raising=False)
        path = db.get_db_path()
        assert path.name == "finally.db"
        assert path.parent.name == "db"
        assert (path.parent.parent / "planning").is_dir()

    def test_seed_on_fresh_db(self, fresh_db):
        assert db.get_cash() == 10000.0
        assert db.list_watchlist() == db.DEFAULT_WATCHLIST

    def test_pragmas(self, fresh_db):
        conn = db.connect()
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()

    def test_reinit_does_not_reseed_empty_watchlist(self, fresh_db):
        for t in db.list_watchlist():
            db.remove_from_watchlist(t)
        with db.transaction() as conn:
            db.set_cash(conn, 1234.5)
        db.init_db()
        assert db.list_watchlist() == []
        assert db.get_cash() == 1234.5

    def test_seed_when_profile_missing(self, fresh_db):
        _execute("DELETE FROM users_profile")
        db.remove_from_watchlist("AAPL")
        db.init_db()
        assert db.get_cash() == 10000.0
        assert set(db.list_watchlist()) == set(db.DEFAULT_WATCHLIST)

    def test_get_cash_without_profile_raises(self, fresh_db):
        _execute("DELETE FROM users_profile")
        with pytest.raises(RuntimeError):
            db.get_cash()


class TestTimestamps:
    def test_now_iso_format(self):
        assert TS_RE.match(db.now_iso())

    def test_stored_timestamps_format(self, fresh_db):
        with db.transaction() as conn:
            executed_at = db.insert_trade(conn, "AAPL", "buy", 1, 100)
            db.upsert_position(conn, "AAPL", 1, 100)
        db.insert_snapshot(100.0)
        db.insert_chat_message("user", "hi", None)
        assert TS_RE.match(executed_at)
        assert TS_RE.match(db.get_position("AAPL").updated_at)
        assert TS_RE.match(db.get_history()[0]["recorded_at"])
        assert TS_RE.match(db.recent_chat_messages()[0]["created_at"])


class TestWatchlist:
    def test_add_remove(self, fresh_db):
        assert db.add_to_watchlist("PYPL") is True
        assert db.add_to_watchlist("PYPL") is False
        assert db.is_on_watchlist("PYPL")
        assert db.list_watchlist()[-1] == "PYPL"
        assert db.remove_from_watchlist("PYPL") is True
        assert db.remove_from_watchlist("PYPL") is False
        assert not db.is_on_watchlist("PYPL")

    def test_same_second_order_is_insertion_order(self, fresh_db):
        added = ["ZZZ", "AAA", "MMM", "BBB"]
        for t in added:
            db.add_to_watchlist(t)
        assert db.list_watchlist()[-4:] == added

    def test_add_inside_transaction(self, fresh_db):
        with db.transaction() as conn:
            assert db.add_to_watchlist("PYPL", conn) is True
            assert db.is_on_watchlist("PYPL", conn)
        assert db.is_on_watchlist("PYPL")


class TestPositionsAndTrades:
    def test_upsert_get_list_delete(self, fresh_db):
        with db.transaction() as conn:
            db.upsert_position(conn, "MSFT", 2, 400)
            db.upsert_position(conn, "AAPL", 1.5, 190)
        assert [p.ticker for p in db.list_positions()] == ["AAPL", "MSFT"]
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 3.5, 195)
        pos = db.get_position("AAPL")
        assert (pos.quantity, pos.avg_cost) == (3.5, 195)
        assert len(db.list_positions()) == 2
        with db.transaction() as conn:
            db.delete_position(conn, "AAPL")
        assert db.get_position("AAPL") is None

    def test_last_trade_prices_most_recent(self, fresh_db):
        with db.transaction() as conn:
            db.insert_trade(conn, "AAPL", "buy", 1, 100)
            db.insert_trade(conn, "MSFT", "buy", 1, 400)
            db.insert_trade(conn, "AAPL", "sell", 1, 110)
        assert db.last_trade_prices() == {"AAPL": 110.0, "MSFT": 400.0}
        assert db.last_trade_prices(["AAPL"]) == {"AAPL": 110.0}
        assert db.last_trade_prices([]) == {}

    def test_last_trade_prices_uses_executed_at(self, fresh_db):
        sql = (
            "INSERT INTO trades (id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, 'AAPL', 'buy', 1, ?, ?)"
        )
        _execute(sql, ("b", 200.0, "2026-01-02T00:00:00Z"))
        _execute(sql, ("a", 100.0, "2026-01-01T00:00:00Z"))
        assert db.last_trade_prices() == {"AAPL": 200.0}

    def test_tracked_tickers_union(self, fresh_db):
        db.remove_from_watchlist("AAPL")
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 1, 190)
            db.upsert_position(conn, "MSFT", 1, 400)
        tracked = db.tracked_tickers()
        assert len(tracked) == len(set(tracked))
        assert set(tracked) == set(db.DEFAULT_WATCHLIST)
        assert tracked[-1] == "AAPL"


class TestTransaction:
    def test_rollback_on_exception(self, fresh_db):
        with pytest.raises(ValueError):
            with db.transaction() as conn:
                db.set_cash(conn, 1.0)
                db.upsert_position(conn, "AAPL", 1, 1)
                db.insert_trade(conn, "AAPL", "buy", 1, 1)
                raise ValueError("boom")
        assert db.get_cash() == 10000.0
        assert db.list_positions() == []
        assert db.last_trade_prices() == {}

    def test_commit(self, fresh_db):
        with db.transaction() as conn:
            db.set_cash(conn, 500.0)
            db.insert_snapshot(500.0, conn)
        assert db.get_cash() == 500.0
        assert len(db.get_history()) == 1


class TestHistory:
    def test_last_24h_oldest_first(self, fresh_db):
        now = datetime.now(UTC)
        _insert_snapshot_at(now - timedelta(hours=25), 1.0)
        _insert_snapshot_at(now - timedelta(hours=1), 3.0)
        _insert_snapshot_at(now - timedelta(hours=2), 2.0)
        assert [p["total_value"] for p in db.get_history()] == [2.0, 3.0]

    def test_no_downsampling_at_limit(self, fresh_db):
        start = datetime.now(UTC) - timedelta(hours=10)
        for i in range(500):
            _insert_snapshot_at(start + timedelta(seconds=30 * i), float(i))
        values = [p["total_value"] for p in db.get_history()]
        assert values == [float(i) for i in range(500)]

    def test_downsampling_keeps_first_and_last(self, fresh_db):
        start = datetime.now(UTC) - timedelta(hours=20)
        for i in range(1337):
            _insert_snapshot_at(start + timedelta(seconds=30 * i), float(i))
        values = [p["total_value"] for p in db.get_history()]
        assert len(values) == 500
        assert values[0] == 0.0
        assert values[-1] == 1336.0
        assert values == sorted(set(values))

    @pytest.mark.parametrize("n,m", [(501, 500), (1000, 500), (10, 3), (5, 2), (5, 1)])
    def test_downsample_helper(self, n, m):
        out = db.downsample(list(range(n)), m)
        assert len(out) == m
        assert out[-1] == n - 1
        if m > 1:
            assert out[0] == 0
        assert out == sorted(set(out))

    def test_downsample_short_list_unchanged(self):
        assert db.downsample([1, 2, 3], 500) == [1, 2, 3]


class TestChat:
    def test_round_trip(self, fresh_db):
        actions = [
            {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10,
             "price": 190.5, "status": "executed", "error": None},
        ]
        db.insert_chat_message("user", "buy 10 AAPL", None)
        db.insert_chat_message("assistant", "Buying 10 AAPL.", actions)
        db.insert_chat_message("assistant", "Hello", [])
        msgs = db.recent_chat_messages()
        assert [m["role"] for m in msgs] == ["user", "assistant", "assistant"]
        assert msgs[0]["actions"] is None
        assert msgs[0]["message"] == "buy 10 AAPL"
        assert msgs[1]["actions"] == actions
        assert msgs[2]["actions"] == []
        assert set(msgs[0]) == {"role", "message", "actions", "created_at"}

    def test_limit_returns_latest_oldest_first(self, fresh_db):
        for i in range(60):
            db.insert_chat_message("user", f"m{i}", None)
        msgs = db.recent_chat_messages(limit=50)
        assert [m["message"] for m in msgs] == [f"m{i}" for i in range(10, 60)]
        assert db.recent_chat_messages(limit=20)[0]["message"] == "m40"
