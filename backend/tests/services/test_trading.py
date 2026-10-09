"""Tests for trade execution (PLAN §8) and tracked-ticker bookkeeping (§6)."""

import sqlite3

import pytest

from app import db
from app.services import ActionError
from app.services.trading import execute_trade


def _count(table: str) -> int:
    conn = sqlite3.connect(db.get_db_path())
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


async def _expect_error(coro, status: int, detail: str) -> None:
    with pytest.raises(ActionError) as exc:
        await coro
    assert exc.value.status_code == status
    assert exc.value.detail == detail


@pytest.mark.asyncio
class TestBuy:
    async def test_buy_updates_cash_position_trade_snapshot(self, ctx):
        snapshots = _count("portfolio_snapshots")
        result = await execute_trade(ctx, "aapl", "buy", 10)

        assert result["ticker"] == "AAPL"
        assert result["side"] == "buy"
        assert result["quantity"] == 10
        assert result["price"] == 190.0
        assert result["cash_balance"] == 8100.0
        assert result["executed_at"].endswith("Z")
        assert db.get_cash() == 8100.0
        pos = db.get_position("AAPL")
        assert pos.quantity == 10 and pos.avg_cost == 190.0
        assert _count("trades") == 1
        assert _count("portfolio_snapshots") == snapshots + 1

    async def test_post_trade_snapshot_values_at_market(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        assert db.get_history()[-1]["total_value"] == 10000.0

    async def test_weighted_avg_cost(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.update("AAPL", 200.0)
        await execute_trade(ctx, "AAPL", "buy", 30)
        pos = db.get_position("AAPL")
        assert pos.quantity == 40
        assert pos.avg_cost == pytest.approx((10 * 190 + 30 * 200) / 40)

    async def test_fractional_quantity_rounded_to_4dp(self, ctx):
        result = await execute_trade(ctx, "AAPL", "buy", 0.123456)
        assert result["quantity"] == 0.1235
        assert db.get_position("AAPL").quantity == 0.1235

    async def test_cash_rounded_to_cents(self, ctx):
        ctx.cache.update("AAPL", 190.333)  # cache rounds to 190.33
        result = await execute_trade(ctx, "AAPL", "buy", 0.3333)
        assert result["cash_balance"] == round(10000 - 0.3333 * 190.33, 2)

    async def test_insufficient_cash(self, ctx):
        await _expect_error(
            execute_trade(ctx, "AAPL", "buy", 100),
            400,
            "Insufficient cash: need $19000.00, have $10000.00",
        )
        assert db.get_cash() == 10000.0
        assert db.get_position("AAPL") is None
        assert _count("trades") == 0

    async def test_buy_unwatched_ticker_adds_to_watchlist_and_tracks(self, ctx):
        ctx.source.prices["PYPL"] = 65.0
        await execute_trade(ctx, "PYPL", "buy", 2)
        assert ctx.source.validated == ["PYPL"]
        assert "PYPL" in ctx.source.get_tickers()
        assert db.is_on_watchlist("PYPL")
        assert db.list_watchlist()[-1] == "PYPL"

    async def test_tracked_ticker_not_validated(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 1)
        assert ctx.source.validated == []

    async def test_unknown_ticker(self, ctx):
        ctx.source.valid = set()
        await _expect_error(execute_trade(ctx, "ZZZZ", "buy", 1), 400, "Unknown ticker: ZZZZ")
        assert "ZZZZ" not in ctx.source.get_tickers()

    async def test_rate_limited_validation(self, ctx):
        ctx.source.rate_limited = True
        await _expect_error(
            execute_trade(ctx, "PYPL", "buy", 1),
            503,
            "Market data rate limit reached — try again in a minute",
        )

    async def test_no_price_available(self, ctx):
        ctx.cache.remove("AAPL")
        await _expect_error(
            execute_trade(ctx, "AAPL", "buy", 1), 400, "No price available yet for AAPL"
        )

    async def test_failed_buy_of_new_ticker_untracks_it(self, ctx):
        ctx.source.prices["PYPL"] = 65.0
        with pytest.raises(ActionError):
            await execute_trade(ctx, "PYPL", "buy", 1000)  # insufficient cash
        assert "PYPL" not in ctx.source.get_tickers()
        assert not db.is_on_watchlist("PYPL")


@pytest.mark.asyncio
class TestSell:
    async def test_sell_partial_keeps_avg_cost(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.update("AAPL", 200.0)
        result = await execute_trade(ctx, "AAPL", "sell", 4)
        assert result["cash_balance"] == 8100.0 + 800.0
        pos = db.get_position("AAPL")
        assert pos.quantity == 6 and pos.avg_cost == 190.0

    async def test_sell_at_loss(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.update("AAPL", 150.0)
        result = await execute_trade(ctx, "AAPL", "sell", 10)
        assert result["cash_balance"] == 8100.0 + 1500.0
        assert db.get_cash() == 9600.0

    async def test_sell_more_than_owned(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 2.5)
        await _expect_error(
            execute_trade(ctx, "AAPL", "sell", 3), 400, "Insufficient shares: have 2.5 AAPL"
        )

    async def test_sell_without_position(self, ctx):
        await _expect_error(
            execute_trade(ctx, "AAPL", "sell", 1), 400, "Insufficient shares: have 0 AAPL"
        )

    async def test_sell_full_deletes_row(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 0.3)
        await execute_trade(ctx, "AAPL", "buy", 0.1)
        await execute_trade(ctx, "AAPL", "sell", 0.4)
        assert db.get_position("AAPL") is None

    async def test_sell_clamped_within_epsilon(self, ctx):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 9.9999995, 190.0)
        result = await execute_trade(ctx, "AAPL", "sell", 10)
        assert result["quantity"] == pytest.approx(9.9999995)
        assert db.get_position("AAPL") is None
        assert result["cash_balance"] == round(10000 + 9.9999995 * 190.0, 2)

    async def test_selling_to_zero_untracks_unwatched_ticker(self, ctx):
        ctx.source.prices["PYPL"] = 65.0
        await execute_trade(ctx, "PYPL", "buy", 1)
        db.remove_from_watchlist("PYPL")
        await execute_trade(ctx, "PYPL", "sell", 1)
        assert "PYPL" not in ctx.source.get_tickers()

    async def test_selling_to_zero_keeps_watched_ticker(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 1)
        await execute_trade(ctx, "AAPL", "sell", 1)
        assert "AAPL" in ctx.source.get_tickers()
        assert ctx.source.removed == []


@pytest.mark.asyncio
class TestInputValidation:
    async def test_quantity_rounds_to_zero(self, ctx):
        await _expect_error(execute_trade(ctx, "AAPL", "buy", 0.00004), 400, "Quantity too small")

    @pytest.mark.parametrize("qty", [0, -1, float("nan"), float("inf")])
    async def test_non_positive_or_invalid_quantity(self, ctx, qty):
        with pytest.raises(ActionError) as exc:
            await execute_trade(ctx, "AAPL", "buy", qty)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("ticker", ["BRK.B", "TOOLONG", "", "A1"])
    async def test_invalid_ticker_format(self, ctx, ticker):
        with pytest.raises(ActionError) as exc:
            await execute_trade(ctx, ticker, "buy", 1)
        assert exc.value.status_code == 400
        assert exc.value.detail.startswith("Invalid ticker")
        assert ctx.source.validated == []

    async def test_invalid_side(self, ctx):
        with pytest.raises(ActionError) as exc:
            await execute_trade(ctx, "AAPL", "short", 1)
        assert exc.value.status_code == 400
