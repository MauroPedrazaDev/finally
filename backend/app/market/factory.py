"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataAuthError, MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)

DEFAULT_MASSIVE_POLL_INTERVAL = 5.0


def _poll_interval_from_env() -> float:
    raw = os.environ.get("MASSIVE_POLL_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_MASSIVE_POLL_INTERVAL
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid MASSIVE_POLL_INTERVAL=%r; using %.0fs", raw, DEFAULT_MASSIVE_POLL_INTERVAL)
        return DEFAULT_MASSIVE_POLL_INTERVAL
    if value <= 0:
        logger.warning("MASSIVE_POLL_INTERVAL must be > 0; using %.0fs", DEFAULT_MASSIVE_POLL_INTERVAL)
        return DEFAULT_MASSIVE_POLL_INTERVAL
    return value


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """Create the appropriate market data source based on environment variables.

    - MASSIVE_API_KEY set and non-empty → MassiveDataSource (real market data),
      polling every MASSIVE_POLL_INTERVAL seconds (default 5)
    - Otherwise → SimulatorDataSource (GBM simulation)

    Returns an unstarted source. Caller must await source.start(tickers), or use
    start_market_data_source() to get the simulator fallback on auth failures.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(
            api_key=api_key,
            price_cache=price_cache,
            poll_interval=_poll_interval_from_env(),
        )
    else:
        logger.info("Market data source: GBM Simulator")
        return SimulatorDataSource(price_cache=price_cache)


async def start_market_data_source(
    price_cache: PriceCache,
    tickers: list[str],
    initial_prices: dict[str, float] | None = None,
    source: MarketDataSource | None = None,
) -> MarketDataSource:
    """Create (unless given) and start a source, falling back to the simulator.

    If the source raises MarketDataAuthError on start (Massive 401/403: bad key or
    a plan without snapshot access), an error is logged and a SimulatorDataSource
    is started instead so the app still works. Returns the running source.
    """
    if source is None:
        source = create_market_data_source(price_cache)
    try:
        await source.start(tickers, initial_prices=initial_prices)
        return source
    except MarketDataAuthError as e:
        logger.error(
            "Massive market data unavailable (%s). A PAID Massive Stocks plan is required "
            "for snapshot data. Falling back to the built-in simulator.",
            e,
        )
        await source.stop()
    fallback = SimulatorDataSource(price_cache=price_cache)
    await fallback.start(tickers, initial_prices=initial_prices)
    return fallback
