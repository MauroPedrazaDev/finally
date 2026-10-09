"""Tests for watchlist services, tracked tickers and portfolio valuation."""

import pytest

from app import db
from app.services import ActionError
from app.services.portfolio import portfolio_summary, portfolio_value, record_snapshot
from app.services.trading import execute_trade
from app.services.watchlist import add_ticker, list_items, remove_ticker


@pytest.mark.asyncio
class TestWatchlist:
    async def test_add_new_ticker(self, ctx):
        ctx.source.prices["PYPL"] = 65.0
        item, created = await add_ticker(ctx, "pypl")
        assert created is True
        assert item["ticker"] == "PYPL"
        assert item["price"] == 65.0
        assert item["session_open"] == 65.0
        assert item["session_change_percent"] == 0.0
        assert "PYPL" in ctx.source.get_tickers()
        assert db.list_watchlist()[-1] == "PYPL"

    async def test_add_existing_is_noop(self, ctx):
        item, created = await add_ticker(ctx, "AAPL")
        assert created is False
        assert item["price"] == 190.0
        assert ctx.source.validated == []

    async def test_add_unknown(self, ctx):
        ctx.source.valid = set()
        with pytest.raises(ActionError) as exc:
            await add_ticker(ctx, "ZZZZ")
        assert (exc.value.status_code, exc.value.detail) == (400, "Unknown ticker: ZZZZ")
        assert not db.is_on_watchlist("ZZZZ")

    async def test_add_rate_limited(self, ctx):
        ctx.source.rate_limited = True
        with pytest.raises(ActionError) as exc:
            await add_ticker(ctx, "PYPL")
        assert exc.value.status_code == 503

    async def test_add_held_but_unwatched_ticker_skips_validation(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 1)
        await remove_ticker(ctx, "AAPL")
        _, created = await add_ticker(ctx, "AAPL")
        assert created is True
        assert ctx.source.validated == []

    async def test_item_without_price_has_nulls(self, ctx):
        item, _ = await add_ticker(ctx, "PYPL")  # FakeSource has no price for it
        assert item == {
            "ticker": "PYPL",
            "price": None,
            "previous_price": None,
            "direction": None,
            "session_open": None,
            "session_change_percent": None,
        }

    async def test_remove_unheld_untracks(self, ctx):
        await remove_ticker(ctx, "googl")
        assert not db.is_on_watchlist("GOOGL")
        assert "GOOGL" not in ctx.source.get_tickers()
        assert ctx.cache.get("GOOGL") is None

    async def test_remove_held_keeps_it_priced(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 1)
        await remove_ticker(ctx, "AAPL")
        assert not db.is_on_watchlist("AAPL")
        assert "AAPL" in ctx.source.get_tickers()
        assert ctx.cache.get_price("AAPL") == 190.0

    async def test_remove_absent_404(self, ctx):
        with pytest.raises(ActionError) as exc:
            await remove_ticker(ctx, "PYPL")
        assert exc.value.status_code == 404

    async def test_list_items_ordered_by_added_at(self, ctx):
        tickers = [i["ticker"] for i in list_items(ctx)]
        assert tickers == db.list_watchlist()
        assert tickers[0] == "AAPL"


@pytest.mark.asyncio
class TestPortfolio:
    async def test_empty_portfolio(self, ctx):
        assert portfolio_summary(ctx) == {
            "cash_balance": 10000.0,
            "total_value": 10000.0,
            "unrealized_pnl": 0.0,
            "positions": [],
        }

    async def test_summary_pnl(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.update("AAPL", 191.74)
        summary = portfolio_summary(ctx)
        assert summary["cash_balance"] == 8100.0
        assert summary["total_value"] == pytest.approx(8100 + 1917.4)
        assert summary["unrealized_pnl"] == pytest.approx(17.4)
        (pos,) = summary["positions"]
        assert pos == {
            "ticker": "AAPL",
            "quantity": 10,
            "avg_cost": 190.0,
            "current_price": 191.74,
            "market_value": 1917.4,
            "unrealized_pnl": 17.4,
            "unrealized_pnl_percent": 0.92,
        }

    async def test_positions_ordered_by_ticker(self, ctx):
        await execute_trade(ctx, "MSFT", "buy", 1)
        await execute_trade(ctx, "AAPL", "buy", 1)
        assert [p["ticker"] for p in portfolio_summary(ctx)["positions"]] == ["AAPL", "MSFT"]

    async def test_no_cached_price_values_at_avg_cost(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.remove("AAPL")
        (pos,) = portfolio_summary(ctx)["positions"]
        assert pos["current_price"] is None
        assert pos["market_value"] == 1900.0
        assert pos["unrealized_pnl"] == 0.0
        assert portfolio_value(ctx) == 10000.0

    async def test_record_snapshot(self, ctx):
        await execute_trade(ctx, "AAPL", "buy", 10)
        ctx.cache.update("AAPL", 200.0)
        assert record_snapshot(ctx) == 10100.0
        assert db.get_history()[-1]["total_value"] == 10100.0
