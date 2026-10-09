"""Execute the actions of a `ChatReply` through the shared service layer (PLAN §8, §10)."""

from __future__ import annotations

import logging
from typing import Any

from app.services import ActionError, MarketContext
from app.services.trading import execute_trade
from app.services.watchlist import add_ticker, remove_ticker

from .schema import ChatReply, TradeInstruction, WatchlistChange

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR = "Unexpected error while executing this action"


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ActionError):
        return exc.detail
    logger.exception("Unexpected error executing chat action")
    return UNEXPECTED_ERROR


async def _run_watchlist_change(ctx: MarketContext, change: WatchlistChange) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "watchlist",
        "ticker": change.ticker.strip().upper(),
        "action": change.action,
        "status": "executed",
        "error": None,
    }
    try:
        if change.action == "add":
            item, _created = await add_ticker(ctx, change.ticker)
            result["ticker"] = item["ticker"]
        else:
            await remove_ticker(ctx, change.ticker)
    except Exception as exc:
        result.update(status="failed", error=_error_text(exc))
    return result


async def _run_trade(ctx: MarketContext, trade: TradeInstruction) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "trade",
        "ticker": trade.ticker.strip().upper(),
        "side": trade.side,
        "quantity": trade.quantity,
        "price": None,
        "status": "executed",
        "error": None,
    }
    try:
        executed = await execute_trade(ctx, trade.ticker, trade.side, trade.quantity)
        result.update(
            ticker=executed["ticker"], quantity=executed["quantity"], price=executed["price"]
        )
    except Exception as exc:
        result.update(status="failed", error=_error_text(exc))
    return result


async def execute_actions(ctx: MarketContext, reply: ChatReply) -> list[dict[str, Any]]:
    """Watchlist changes first, then trades, each in array order."""
    results = [await _run_watchlist_change(ctx, c) for c in reply.watchlist_changes]
    results += [await _run_trade(ctx, t) for t in reply.trades]
    return results
