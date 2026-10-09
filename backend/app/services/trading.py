"""Market-order execution: the single trade path for manual and LLM trades (PLAN §8)."""

from __future__ import annotations

import asyncio
import math

from app import db

from . import (
    ActionError,
    MarketContext,
    ensure_ticker_exists,
    format_quantity,
    is_tracked,
    normalize_ticker,
)
from .portfolio import portfolio_value

QUANTITY_DECIMALS = 4
EPSILON = 1e-6


def _execute_in_transaction(
    ctx: MarketContext, ticker: str, side: str, quantity: float
) -> tuple[dict, bool]:
    """Validate and apply the trade atomically. Returns (response, still_needed).

    `still_needed` is False when the ticker is neither held nor watched afterwards.
    """
    with db.transaction() as conn:
        cash = db.get_cash(conn)
        position = db.get_position(ticker, conn)
        held = position.quantity if position else 0.0
        price = ctx.cache.get_price(ticker)

        if side == "buy":
            if price is None:
                raise ActionError(400, f"No price available yet for {ticker}")
            cost = quantity * price
            if cost > cash:
                raise ActionError(400, f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}")
            old_avg = position.avg_cost if position else 0.0
            avg_cost = (held * old_avg + quantity * price) / (held + quantity)
            db.upsert_position(conn, ticker, round(held + quantity, QUANTITY_DECIMALS), avg_cost)
            cash = round(cash - cost, 2)
            db.add_to_watchlist(ticker, conn)
        else:
            if quantity > held + EPSILON:
                raise ActionError(
                    400, f"Insufficient shares: have {format_quantity(held)} {ticker}"
                )
            if price is None:
                raise ActionError(400, f"No price available yet for {ticker}")
            quantity = min(quantity, held)
            remaining = round(held - quantity, QUANTITY_DECIMALS)
            if remaining < EPSILON:
                db.delete_position(conn, ticker)
            else:
                db.upsert_position(conn, ticker, remaining, position.avg_cost)
            cash = round(cash + quantity * price, 2)

        db.set_cash(conn, cash)
        executed_at = db.insert_trade(conn, ticker, side, quantity, price)
        db.insert_snapshot(portfolio_value(ctx, conn), conn)
        still_needed = db.get_position(ticker, conn) is not None or db.is_on_watchlist(
            ticker, conn
        )

    response = {
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "cash_balance": cash,
        "executed_at": executed_at,
    }
    return response, still_needed


def _is_needed(ticker: str) -> bool:
    return db.get_position(ticker) is not None or db.is_on_watchlist(ticker)


async def execute_trade(ctx: MarketContext, ticker: str, side: str, quantity: float) -> dict:
    """Execute a market order at the cached price. Raises ActionError on rule violations.

    Returns the PLAN §9 POST /api/portfolio/trade response. Validation, cash and
    position updates, the trade row and the post-trade snapshot are one
    BEGIN IMMEDIATE transaction; ticker validation happens before it.
    """
    ticker = normalize_ticker(ticker)
    if side not in ("buy", "sell"):
        raise ActionError(400, f"Invalid side: {side}")
    try:
        quantity = float(quantity)
    except (TypeError, ValueError) as e:
        raise ActionError(400, f"Invalid quantity: {quantity}") from e
    if not math.isfinite(quantity) or quantity <= 0:
        raise ActionError(400, "Quantity must be greater than 0")
    quantity = round(quantity, QUANTITY_DECIMALS)
    if quantity <= 0:
        raise ActionError(400, "Quantity too small")

    was_tracked = is_tracked(ctx, ticker)
    if not was_tracked:
        await ensure_ticker_exists(ctx, ticker)
        if side == "buy":
            # Start pricing it now; the simulator writes a price immediately.
            await ctx.source.add_ticker(ticker)

    try:
        response, still_needed = await asyncio.to_thread(
            _execute_in_transaction, ctx, ticker, side, quantity
        )
    except ActionError:
        if not was_tracked and is_tracked(ctx, ticker):
            if not await asyncio.to_thread(_is_needed, ticker):
                await ctx.source.remove_ticker(ticker)
        raise

    if not still_needed:
        await ctx.source.remove_ticker(ticker)
    return response
