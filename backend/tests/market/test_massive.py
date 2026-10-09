"""Tests for MassiveDataSource (mocked)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from massive.rest.models import TickerSnapshot

from app.market.cache import PriceCache
from app.market.interface import (
    MarketDataAuthError,
    MarketDataError,
    MarketDataRateLimitError,
)
from app.market.massive_client import MassiveDataSource, MassiveHTTPError

TS_NS = 1707580800_000_000_000  # REST timestamps are Unix nanoseconds


def _make_snapshot(
    ticker: str, price: float, timestamp_ns: int = TS_NS, prev_close: float | None = None
) -> TickerSnapshot:
    """Build a real TickerSnapshot from REST-shaped JSON."""
    data = {"ticker": ticker, "lastTrade": {"T": ticker, "p": price, "t": timestamp_ns}}
    if prev_close is not None:
        data["prevDay"] = {"c": prev_close}
    return TickerSnapshot.from_dict(data)


def _source(cache: PriceCache, tickers: list[str] | None = None) -> MassiveDataSource:
    source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
    source._tickers = list(tickers or [])
    source._client = MagicMock()  # Satisfy the _poll_once guard
    source._client.BASE = "https://api.massive.com"
    return source


def _http_response(status: int, body: str) -> SimpleNamespace:
    return SimpleNamespace(status=status, data=body.encode())


@pytest.mark.asyncio
class TestMassivePolling:
    async def test_poll_updates_cache(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL", "GOOGL"])
        snaps = [_make_snapshot("AAPL", 190.50), _make_snapshot("GOOGL", 175.25)]

        with patch.object(source, "_fetch_snapshots", return_value=snaps):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25

    async def test_malformed_snapshot_skipped(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL", "BAD"])
        bad_snap = TickerSnapshot.from_dict({"ticker": "BAD"})  # no lastTrade

        with patch.object(
            source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.50), bad_snap]
        ):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("BAD") is None

    async def test_api_error_does_not_crash(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
            await source._poll_once()  # Should not raise

        assert cache.get_price("AAPL") is None

    async def test_auth_error_during_loop_does_not_raise(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", side_effect=MassiveHTTPError(403)):
            await source._poll_once()  # Only start() propagates auth errors

    async def test_timestamp_nanoseconds_to_seconds(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.5)]):
            await source._poll_once()

        assert cache.get("AAPL").timestamp == pytest.approx(1707580800.0)

    async def test_prev_day_close_is_session_open(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])
        snaps = [_make_snapshot("AAPL", 190.0, prev_close=200.0)]

        with patch.object(source, "_fetch_snapshots", return_value=snaps):
            await source._poll_once()

        update = cache.get("AAPL")
        assert update.session_open == 200.0
        assert update.session_change_percent == pytest.approx(-5.0)

    async def test_session_open_falls_back_to_price_without_prev_day(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.0)]):
            await source._poll_once()

        assert cache.get("AAPL").session_open == 190.0

    async def test_empty_tickers_skips_poll(self):
        cache = PriceCache()
        source = _source(cache, [])

        with patch.object(source, "_fetch_snapshots") as mock_fetch:
            await source._poll_once()
            mock_fetch.assert_not_called()

    async def test_fetch_snapshots_parses_rest_json(self):
        cache = PriceCache()
        source = _source(cache, ["AAPL"])
        body = (
            '{"status":"OK","tickers":[{"ticker":"AAPL","lastTrade":{"p":191.2,"t":%d},'
            '"prevDay":{"c":189.0}}]}' % TS_NS
        )
        source._client.client.request.return_value = _http_response(200, body)

        await source._poll_once()

        update = cache.get("AAPL")
        assert update.price == 191.2
        assert update.session_open == 189.0
        kwargs = source._client.client.request.call_args.kwargs
        assert kwargs["fields"] == {"tickers": "AAPL"}
        assert kwargs["retries"] is False


@pytest.mark.asyncio
class TestMassiveLifecycle:
    async def test_add_ticker(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        await source.add_ticker("AAPL")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_normalizes(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        await source.add_ticker("  aapl  ")
        assert source.get_tickers() == ["AAPL"]

    async def test_remove_ticker(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]
        cache.update("AAPL", 190.00)

        await source.remove_ticker("AAPL")
        assert "AAPL" not in source.get_tickers()
        assert cache.get("AAPL") is None

    async def test_default_poll_interval_is_5s(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        assert source._interval == 5.0

    async def test_stop_is_idempotent(self):
        source = MassiveDataSource(api_key="test-key", price_cache=PriceCache())
        await source.stop()
        await source.stop()

    async def test_start_immediate_poll_and_stop(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(
                source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.50)]
            ):
                await source.start(["AAPL"], initial_prices={"AAPL": 1.0})

        assert cache.get_price("AAPL") == 190.50  # initial_prices ignored for real data
        assert source._task is not None and not source._task.done()
        await source.stop()
        assert source._task is None

    @pytest.mark.parametrize("status", [401, 403])
    async def test_start_raises_on_auth_error(self, status):
        source = MassiveDataSource(api_key="bad", price_cache=PriceCache())

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", side_effect=MassiveHTTPError(status)):
                with pytest.raises(MarketDataAuthError):
                    await source.start(["AAPL"])

        assert source._task is None

    async def test_start_survives_other_errors(self):
        source = MassiveDataSource(api_key="k", price_cache=PriceCache(), poll_interval=60.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", side_effect=MassiveHTTPError(500)):
                await source.start(["AAPL"])

        assert source._task is not None
        await source.stop()


@pytest.mark.asyncio
class TestMassiveValidateTicker:
    async def test_found_writes_price_with_session_open(self):
        cache = PriceCache()
        source = _source(cache)
        snap = _make_snapshot("PYPL", 65.0, prev_close=64.0)

        with patch.object(source, "_fetch_snapshot_ticker", return_value=snap):
            assert await source.validate_ticker("pypl") is True

        assert cache.get_price("PYPL") == 65.0
        assert cache.get("PYPL").session_open == 64.0

    async def test_not_found_404(self):
        source = _source(PriceCache())
        with patch.object(source, "_fetch_snapshot_ticker", side_effect=MassiveHTTPError(404)):
            assert await source.validate_ticker("ZZZZ") is False

    async def test_no_data(self):
        source = _source(PriceCache())
        with patch.object(source, "_fetch_snapshot_ticker", return_value=None):
            assert await source.validate_ticker("ZZZZ") is False

    async def test_rate_limited(self):
        source = _source(PriceCache())
        with patch.object(source, "_fetch_snapshot_ticker", side_effect=MassiveHTTPError(429)):
            with pytest.raises(MarketDataRateLimitError):
                await source.validate_ticker("PYPL")

    async def test_other_error_raises_market_data_error(self):
        source = _source(PriceCache())
        with patch.object(source, "_fetch_snapshot_ticker", side_effect=MassiveHTTPError(500)):
            with pytest.raises(MarketDataError):
                await source.validate_ticker("PYPL")

    async def test_http_layer_404_and_200(self):
        cache = PriceCache()
        source = _source(cache)
        request = source._client.client.request

        request.return_value = _http_response(404, '{"status":"NOT_FOUND"}')
        assert await source.validate_ticker("ZZZZ") is False

        request.return_value = _http_response(
            200, '{"status":"OK","ticker":{"ticker":"PYPL","lastTrade":{"p":65.5,"t":%d}}}' % TS_NS
        )
        assert await source.validate_ticker("PYPL") is True
        assert cache.get_price("PYPL") == 65.5
        assert request.call_args.args[1].endswith("/v2/snapshot/locale/us/markets/stocks/tickers/PYPL")
