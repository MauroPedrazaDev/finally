"""Massive (Polygon.io) API client for real market data."""

from __future__ import annotations

import asyncio
import json
import logging

from massive import RESTClient
from massive.rest.models import TickerSnapshot

from .cache import PriceCache
from .interface import (
    MarketDataAuthError,
    MarketDataError,
    MarketDataRateLimitError,
    MarketDataSource,
)

logger = logging.getLogger(__name__)

SNAPSHOT_ALL_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
SNAPSHOT_TICKER_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"


class MassiveHTTPError(MarketDataError):
    """Non-200 response from the Massive REST API."""

    def __init__(self, status: int, body: str = "") -> None:
        super().__init__(f"Massive API returned HTTP {status}: {body[:200]}")
        self.status = status


def _raise_for_status(error: MassiveHTTPError) -> None:
    """Translate an HTTP error into the interface's typed exceptions."""
    if error.status in (401, 403):
        raise MarketDataAuthError(str(error)) from error
    if error.status == 429:
        raise MarketDataRateLimitError(str(error)) from error
    raise error


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Polls GET /v2/snapshot/locale/us/markets/stocks/tickers for all tracked
    tickers in a single API call, then writes results to the PriceCache.

    Requires a paid Stocks plan: snapshot endpoints return 403 on the free tier.
    start() raises MarketDataAuthError on 401/403 so the caller can fall back
    to the simulator.

    Requests go through the RESTClient's connection pool directly (retries
    disabled) so we see real HTTP status codes; the library's helpers collapse
    them into a status-less BadResponse and silently retry 429s.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 5.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(
        self, tickers: list[str], initial_prices: dict[str, float] | None = None
    ) -> None:
        # initial_prices is ignored: real data always comes from the API.
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)

        # Do an immediate first poll so the cache has data right away.
        # Auth failures (bad key / plan without snapshot access) propagate.
        try:
            await self._poll_once(raise_auth_errors=True)
        except MarketDataAuthError:
            self._client = None
            raise

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            logger.info("Massive: added ticker %s (will appear on next poll)", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    async def validate_ticker(self, ticker: str) -> bool:
        """One-off snapshot lookup. On success the price is written to the cache.

        Returns False for unknown tickers (404 / no data). Raises
        MarketDataRateLimitError on 429 and MarketDataError on other failures.
        """
        ticker = ticker.upper().strip()
        try:
            snap = await asyncio.to_thread(self._fetch_snapshot_ticker, ticker)
        except MassiveHTTPError as e:
            if e.status == 404:
                return False
            _raise_for_status(e)
        if snap is None:
            return False
        return self._write_snapshot(snap, ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Internal ---

    async def _poll_loop(self) -> None:
        """Poll on interval. First poll already happened in start()."""
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self, raise_auth_errors: bool = False) -> None:
        """Execute one poll cycle: fetch snapshots, update cache."""
        if not self._tickers or not self._client:
            return

        try:
            # The HTTP client is synchronous — run in a thread to
            # avoid blocking the event loop.
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
        except MassiveHTTPError as e:
            if e.status in (401, 403):
                logger.error(
                    "Massive API rejected the request (HTTP %d). Snapshot data requires a "
                    "PAID Massive Stocks plan (Starter or above); check MASSIVE_API_KEY.",
                    e.status,
                )
                if raise_auth_errors:
                    raise MarketDataAuthError(str(e)) from e
            else:
                logger.error("Massive poll failed: %s", e)
            return
        except Exception as e:
            # Don't re-raise — the loop will retry on the next interval.
            logger.error("Massive poll failed: %s", e)
            return

        processed = 0
        for snap in snapshots:
            if self._write_snapshot(snap, getattr(snap, "ticker", None)):
                processed += 1
        logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))

    def _write_snapshot(self, snap, ticker: str | None) -> bool:
        """Write one snapshot to the cache. Returns False if it is malformed."""
        try:
            price = snap.last_trade.price
            if not ticker or price is None or price <= 0:
                raise ValueError("missing ticker or price")
            # REST timestamps are Unix nanoseconds → convert to seconds
            ts_ns = snap.last_trade.sip_timestamp or snap.last_trade.participant_timestamp
            timestamp = ts_ns / 1e9 if ts_ns else None
            prev_day = snap.prev_day
            session_open = prev_day.close if prev_day is not None else None
            self._cache.update(
                ticker=ticker,
                price=price,
                timestamp=timestamp,
                session_open=session_open,
            )
            return True
        except (AttributeError, TypeError, ValueError) as e:
            logger.warning("Skipping snapshot for %s: %s", ticker or "???", e)
            return False

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        """Synchronous GET through the RESTClient's pool. Raises MassiveHTTPError."""
        client = self._client
        if client is None:
            raise MarketDataError("Massive client not started")
        resp = client.client.request(
            "GET",
            client.BASE + path,
            fields=params,
            headers=client.headers,
            retries=False,
            timeout=client.timeout,
        )
        body = resp.data.decode("utf-8", errors="replace")
        if resp.status != 200:
            raise MassiveHTTPError(resp.status, body)
        try:
            return json.loads(body)
        except ValueError as e:
            raise MarketDataError(f"Invalid JSON from Massive: {e}") from e

    def _fetch_snapshots(self) -> list[TickerSnapshot]:
        """Synchronous snapshot of all tracked tickers. Runs in a thread."""
        data = self._get_json(SNAPSHOT_ALL_PATH, {"tickers": ",".join(self._tickers)})
        return [TickerSnapshot.from_dict(d) for d in data.get("tickers") or []]

    def _fetch_snapshot_ticker(self, ticker: str) -> TickerSnapshot | None:
        """Synchronous single-ticker snapshot. Runs in a thread."""
        if self._client is None:
            # validate_ticker may be called before start() (or after a stop)
            self._client = RESTClient(api_key=self._api_key)
        data = self._get_json(SNAPSHOT_TICKER_PATH.format(ticker=ticker))
        raw = data.get("ticker")
        return TickerSnapshot.from_dict(raw) if raw else None
