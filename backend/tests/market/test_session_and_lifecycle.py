"""Tests for the PLAN §6 additions: session open, remove() versioning, initial and
deterministic seed prices, validate_ticker, poll interval, auth fallback, SSE router."""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.market import (
    MarketDataAuthError,
    PriceCache,
    create_stream_router,
    start_market_data_source,
)
from app.market.factory import create_market_data_source
from app.market.massive_client import MassiveDataSource
from app.market.models import PriceUpdate
from app.market.simulator import GBMSimulator, SimulatorDataSource, seed_price_for
from app.market.stream import _generate_events


class TestSessionOpen:
    def test_to_dict_includes_session_fields(self):
        update = PriceUpdate("AAPL", 190.5, 190.0, 1.0, session_open=190.0)
        d = update.to_dict()
        assert d["session_open"] == 190.0
        assert d["session_change_percent"] == pytest.approx(0.2632)

    def test_session_change_zero_when_open_unknown(self):
        assert PriceUpdate("AAPL", 190.5, 190.0, 1.0).session_change_percent == 0.0

    def test_first_write_defaults_to_price(self):
        cache = PriceCache()
        assert cache.update("AAPL", 190.0).session_open == 190.0

    def test_first_write_uses_explicit_value(self):
        cache = PriceCache()
        assert cache.update("AAPL", 190.0, session_open=185.0).session_open == 185.0

    def test_non_positive_explicit_value_ignored(self):
        cache = PriceCache()
        assert cache.update("AAPL", 190.0, session_open=0).session_open == 190.0

    def test_carried_forward_and_argument_ignored(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0, session_open=185.0)
        later = cache.update("AAPL", 195.0, session_open=999.0)
        assert later.session_open == 185.0
        assert later.session_change_percent == pytest.approx(5.4054, rel=1e-3)

    def test_remove_clears_session_open(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.remove("AAPL")
        assert cache.update("AAPL", 200.0).session_open == 200.0

    def test_remove_bumps_version(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        v = cache.version
        cache.remove("AAPL")
        assert cache.version == v + 1

    def test_remove_missing_does_not_bump_version(self):
        cache = PriceCache()
        v = cache.version
        cache.remove("NOPE")
        assert cache.version == v


class TestSeedPrices:
    def test_known_ticker_uses_seed(self):
        assert seed_price_for("AAPL") == 190.0

    def test_unknown_ticker_is_deterministic_and_in_range(self):
        price = seed_price_for("PYPL")
        assert price == seed_price_for("PYPL")
        assert 50.0 <= price <= 300.0
        assert GBMSimulator(["PYPL"]).get_price("PYPL") == price

    def test_unknown_tickers_differ(self):
        assert seed_price_for("PYPL") != seed_price_for("UBER")

    def test_initial_prices_honored(self):
        sim = GBMSimulator(["AAPL", "PYPL"], initial_prices={"AAPL": 210.0})
        assert sim.get_price("AAPL") == 210.0
        assert sim.get_price("PYPL") == seed_price_for("PYPL")

    def test_invalid_initial_price_ignored(self):
        sim = GBMSimulator(["AAPL"], initial_prices={"AAPL": 0})
        assert sim.get_price("AAPL") == 190.0


@pytest.mark.asyncio
class TestSimulatorSource:
    async def test_start_with_initial_prices_sets_session_open(self):
        cache = PriceCache()
        source = SimulatorDataSource(cache, update_interval=60)
        await source.start(["AAPL"], initial_prices={"AAPL": 210.0})
        try:
            assert cache.get_price("AAPL") == 210.0
            assert cache.get("AAPL").session_open == 210.0
        finally:
            await source.stop()

    async def test_validate_ticker_always_true(self):
        source = SimulatorDataSource(PriceCache())
        assert await source.validate_ticker("ANYT") is True


class TestFactoryPollInterval:
    def _make(self, env):
        with patch.dict(os.environ, env, clear=True):
            return create_market_data_source(PriceCache())

    def test_default_interval(self):
        assert self._make({"MASSIVE_API_KEY": "k"})._interval == 5.0

    def test_interval_from_env(self):
        source = self._make({"MASSIVE_API_KEY": "k", "MASSIVE_POLL_INTERVAL": "12"})
        assert isinstance(source, MassiveDataSource)
        assert source._interval == 12.0

    @pytest.mark.parametrize("raw", ["abc", "0", "-3"])
    def test_invalid_interval_falls_back(self, raw):
        assert self._make({"MASSIVE_API_KEY": "k", "MASSIVE_POLL_INTERVAL": raw})._interval == 5.0


@pytest.mark.asyncio
class TestStartWithFallback:
    async def test_auth_error_falls_back_to_simulator(self):
        cache = PriceCache()
        massive = MassiveDataSource(api_key="bad", price_cache=cache)
        massive.start = AsyncMock(side_effect=MarketDataAuthError("403"))
        massive.stop = AsyncMock()

        source = await start_market_data_source(
            cache, ["AAPL"], {"AAPL": 222.0}, source=massive
        )
        try:
            assert isinstance(source, SimulatorDataSource)
            massive.stop.assert_awaited_once()
            assert cache.get_price("AAPL") == 222.0
        finally:
            await source.stop()

    async def test_auth_error_from_real_start_falls_back(self):
        from app.market.massive_client import MassiveHTTPError

        cache = PriceCache()
        with patch.dict(os.environ, {"MASSIVE_API_KEY": "bad"}, clear=True):
            with patch("app.market.massive_client.RESTClient"):
                with patch.object(
                    MassiveDataSource, "_fetch_snapshots", side_effect=MassiveHTTPError(401)
                ):
                    source = await start_market_data_source(cache, ["AAPL"])
        try:
            assert isinstance(source, SimulatorDataSource)
            assert cache.get_price("AAPL") == 190.0
        finally:
            await source.stop()

    async def test_simulator_by_default(self):
        cache = PriceCache()
        with patch.dict(os.environ, {}, clear=True):
            source = await start_market_data_source(cache, ["AAPL"])
        try:
            assert isinstance(source, SimulatorDataSource)
        finally:
            await source.stop()


class TestStreamRouter:
    def test_router_created_per_call(self):
        cache = PriceCache()
        r1, r2 = create_stream_router(cache), create_stream_router(cache)
        assert r1 is not r2
        assert len(r1.routes) == 1 and len(r2.routes) == 1

    def test_two_apps_each_register_prices_once(self):
        cache = PriceCache()
        for _ in range(2):
            app = FastAPI()
            app.include_router(create_stream_router(cache))
            paths = [r.path for r in app.routes if r.path == "/api/stream/prices"]
            assert paths == ["/api/stream/prices"]


@pytest.mark.asyncio
class TestStreamEvents:
    async def test_retry_first_then_full_snapshot(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("GOOGL", 175.0)
        request = MagicMock()
        request.client.host = "test"
        request.is_disconnected = AsyncMock(return_value=False)

        gen = _generate_events(cache, request, interval=0.01)
        assert await gen.__anext__() == "retry: 1000\n\n"
        event = await gen.__anext__()
        payload = json.loads(event.removeprefix("data: ").strip())
        assert set(payload) == {"AAPL", "GOOGL"}
        assert payload["AAPL"]["session_open"] == 190.0
        assert "session_change_percent" in payload["AAPL"]

        # Removal bumps the version → a new event without the removed ticker
        cache.remove("GOOGL")
        event = await asyncio.wait_for(gen.__anext__(), timeout=1)
        assert set(json.loads(event.removeprefix("data: "))) == {"AAPL"}
        await gen.aclose()
