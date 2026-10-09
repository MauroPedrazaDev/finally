"""Fixtures for service tests: a fresh DB and a deterministic fake market source."""

from __future__ import annotations

import pytest

from app import db
from app.market import MarketDataRateLimitError, MarketDataSource, PriceCache
from app.services import MarketContext


class FakeSource(MarketDataSource):
    """Records calls; add_ticker writes a fixed price (like the simulator does)."""

    def __init__(self, cache: PriceCache, tickers: list[str]) -> None:
        self.cache = cache
        self.tickers = list(tickers)
        self.prices: dict[str, float] = {}  # price written by add_ticker
        self.valid: set[str] | None = None  # None → every ticker is valid
        self.rate_limited = False
        self.validated: list[str] = []
        self.removed: list[str] = []

    async def start(self, tickers, initial_prices=None):  # pragma: no cover - unused
        self.tickers = list(tickers)

    async def stop(self):  # pragma: no cover - unused
        pass

    async def add_ticker(self, ticker):
        if ticker not in self.tickers:
            self.tickers.append(ticker)
            if ticker in self.prices:
                self.cache.update(ticker, self.prices[ticker])

    async def remove_ticker(self, ticker):
        self.removed.append(ticker)
        self.tickers = [t for t in self.tickers if t != ticker]
        self.cache.remove(ticker)

    async def validate_ticker(self, ticker):
        self.validated.append(ticker)
        if self.rate_limited:
            raise MarketDataRateLimitError("429")
        return self.valid is None or ticker in self.valid

    def get_tickers(self):
        return list(self.tickers)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


@pytest.fixture
def ctx(fresh_db) -> MarketContext:
    cache = PriceCache()
    tickers = db.tracked_tickers()
    for i, t in enumerate(tickers):
        cache.update(t, 100.0 + i)
    cache.update("AAPL", 190.0)
    return MarketContext(cache=cache, source=FakeSource(cache, tickers))
