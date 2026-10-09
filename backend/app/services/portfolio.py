"""Portfolio valuation: summary for GET /api/portfolio and total value for snapshots."""

from __future__ import annotations

import sqlite3

from app import db

from . import MarketContext


def portfolio_value(ctx: MarketContext, conn: sqlite3.Connection | None = None) -> float:
    """Cash plus positions valued at the cached price (avg_cost if no price yet)."""
    total = db.get_cash(conn)
    for pos in db.list_positions(conn):
        price = ctx.cache.get_price(pos.ticker)
        total += pos.quantity * (price if price is not None else pos.avg_cost)
    return round(total, 2)


def record_snapshot(ctx: MarketContext) -> float:
    """Insert a portfolio snapshot at current prices. Sync; returns the value."""
    value = portfolio_value(ctx)
    db.insert_snapshot(value)
    return value


def portfolio_summary(ctx: MarketContext) -> dict:
    """PLAN §9 GET /api/portfolio response. Sync; call via asyncio.to_thread from async code."""
    with db.transaction() as conn:  # consistent read of cash + positions
        cash = db.get_cash(conn)
        positions = db.list_positions(conn)

    items = []
    total = cash
    total_pnl = 0.0
    for pos in positions:
        current = ctx.cache.get_price(pos.ticker)
        price = current if current is not None else pos.avg_cost
        market_value = pos.quantity * price
        pnl = market_value - pos.quantity * pos.avg_cost
        pnl_pct = (price - pos.avg_cost) / pos.avg_cost * 100 if pos.avg_cost else 0.0
        total += market_value
        total_pnl += pnl
        items.append(
            {
                "ticker": pos.ticker,
                "quantity": pos.quantity,
                "avg_cost": round(pos.avg_cost, 4),
                "current_price": current,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_percent": round(pnl_pct, 2),
            }
        )

    return {
        "cash_balance": round(cash, 2),
        "total_value": round(total, 2),
        "unrealized_pnl": round(total_pnl, 2),
        "positions": items,
    }
