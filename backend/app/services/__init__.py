"""Business logic shared by the REST routes and the LLM chat flow (PLAN §8).

Every manual and LLM action goes through these functions, so the trading and
watchlist rules live in exactly one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.market import (
    MarketDataError,
    MarketDataRateLimitError,
    MarketDataSource,
    PriceCache,
)

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")

RATE_LIMIT_DETAIL = "Market data rate limit reached — try again in a minute"
MARKET_DATA_UNAVAILABLE_DETAIL = "Market data unavailable — try again shortly"


@dataclass
class MarketContext:
    """Live market state shared by the app; stored on app.state.market."""

    cache: PriceCache
    source: MarketDataSource


class ActionError(Exception):
    """A business-rule failure carrying the HTTP status and the user-facing detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def normalize_ticker(raw: str) -> str:
    """Uppercase and validate the format ^[A-Z]{1,5}$ (raises ActionError 400)."""
    ticker = (raw or "").strip().upper()
    if not TICKER_PATTERN.match(ticker):
        raise ActionError(400, f"Invalid ticker: {raw}")
    return ticker


def is_tracked(ctx: MarketContext, ticker: str) -> bool:
    """True if the market data source already prices this ticker."""
    return ticker in ctx.source.get_tickers()


async def ensure_ticker_exists(ctx: MarketContext, ticker: str) -> None:
    """Validate an untracked ticker with the data source. Never call inside a transaction."""
    if is_tracked(ctx, ticker):
        return
    try:
        valid = await ctx.source.validate_ticker(ticker)
    except MarketDataRateLimitError as e:
        raise ActionError(503, RATE_LIMIT_DETAIL) from e
    except MarketDataError as e:
        raise ActionError(503, MARKET_DATA_UNAVAILABLE_DETAIL) from e
    if not valid:
        raise ActionError(400, f"Unknown ticker: {ticker}")


def format_quantity(quantity: float) -> str:
    """Human-friendly quantity: up to 4 decimals, no trailing zeros."""
    text = f"{round(quantity, 4):.4f}".rstrip("0").rstrip(".")
    return text or "0"


__all__ = [
    "ActionError",
    "MarketContext",
    "ensure_ticker_exists",
    "format_quantity",
    "is_tracked",
    "normalize_ticker",
]
