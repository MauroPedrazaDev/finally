"""Watchlist add/remove with tracked-ticker bookkeeping (PLAN §6, §8, §9)."""

from __future__ import annotations

import asyncio

from app import db

from . import ActionError, MarketContext, ensure_ticker_exists, is_tracked, normalize_ticker


def watchlist_item(ctx: MarketContext, ticker: str) -> dict:
    """PLAN §9 watchlist item; price fields are null when nothing is cached yet."""
    update = ctx.cache.get(ticker)
    if update is None:
        return {
            "ticker": ticker,
            "price": None,
            "previous_price": None,
            "direction": None,
            "session_open": None,
            "session_change_percent": None,
        }
    return {
        "ticker": ticker,
        "price": update.price,
        "previous_price": update.previous_price,
        "direction": update.direction,
        "session_open": update.session_open,
        "session_change_percent": update.session_change_percent,
    }


def list_items(ctx: MarketContext) -> list[dict]:
    """All watchlist items ordered by added_at. Sync."""
    return [watchlist_item(ctx, t) for t in db.list_watchlist()]


async def add_ticker(ctx: MarketContext, ticker: str) -> tuple[dict, bool]:
    """Add a ticker to the watchlist. Returns (item, created); existing → created=False."""
    ticker = normalize_ticker(ticker)
    if await asyncio.to_thread(db.is_on_watchlist, ticker):
        return watchlist_item(ctx, ticker), False

    await ensure_ticker_exists(ctx, ticker)  # before any DB write
    created = await asyncio.to_thread(db.add_to_watchlist, ticker)
    if not is_tracked(ctx, ticker):
        await ctx.source.add_ticker(ticker)
    return watchlist_item(ctx, ticker), created


async def remove_ticker(ctx: MarketContext, ticker: str) -> None:
    """Remove a ticker from the watchlist (404 if absent).

    The data source keeps pricing it while a position is open.
    """
    normalized = (ticker or "").strip().upper()
    removed = await asyncio.to_thread(db.remove_from_watchlist, normalized)
    if not removed:
        raise ActionError(404, f"{normalized or ticker} is not on the watchlist")
    if await asyncio.to_thread(db.get_position, normalized) is None:
        await ctx.source.remove_ticker(normalized)
