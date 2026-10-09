# Market Data Backend — Summary

**Status:** Complete, tested, reviewed. PLAN §6 "Required changes" implemented (see below).

## What Was Built

A complete market data subsystem in `backend/app/market/` (8 modules, ~500 lines) providing live price simulation and real market data via a unified interface.

### Architecture

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key needed)
└── MassiveDataSource    →  Polygon.io REST poller (when MASSIVE_API_KEY set)
        │
        ▼
   PriceCache (thread-safe, in-memory)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

### Modules

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate` — immutable frozen dataclass (ticker, price, previous_price, timestamp, session_open; change, direction, session_change_percent) |
| `interface.py` | `MarketDataSource` — ABC: `start(tickers, initial_prices=None)/stop/add_ticker/remove_ticker/validate_ticker/get_tickers`; errors `MarketDataError` > `MarketDataRateLimitError`, `MarketDataAuthError` |
| `cache.py` | `PriceCache` — thread-safe price store with version counter for SSE change detection |
| `seed_prices.py` | Realistic seed prices, per-ticker GBM params (drift/volatility), correlation groups |
| `simulator.py` | `GBMSimulator` (Geometric Brownian Motion with Cholesky-correlated moves) + `SimulatorDataSource` |
| `massive_client.py` | `MassiveDataSource` — REST polling client for Polygon.io via the `massive` package |
| `factory.py` | `create_market_data_source()` — simulator or Massive (`MASSIVE_API_KEY`, `MASSIVE_POLL_INTERVAL` default 5s); `start_market_data_source()` — create + start, falls back to the simulator on 401/403 |
| `stream.py` | `create_stream_router()` — FastAPI SSE endpoint factory using version-based change detection |

### Key Design Decisions

- **Strategy pattern** — both data sources implement the same ABC; downstream code is source-agnostic
- **PriceCache as single point of truth** — producers write, consumers read; no direct coupling
- **GBM with correlated moves** — Cholesky decomposition of sector-based correlation matrix; tech stocks correlate at 0.6, finance at 0.5, cross-sector at 0.3
- **Random shock events** — ~0.1% chance per tick per ticker of a 2-5% move for visual drama
- **SSE over WebSockets** — simpler, one-way push, universal browser support

## PLAN §6 Required Changes (done)

- `PriceUpdate.session_open` field; `to_dict()` adds `session_open` and `session_change_percent`
- `PriceCache.update(..., session_open=None)`: first write uses the explicit value if > 0, else the price; later writes carry it forward. `remove()` drops the ticker and bumps `version`
- `validate_ticker()`: simulator always `True`; Massive does a one-off single-ticker snapshot in a thread — found → writes price (with `prev_day.close` as session open) and returns `True`; 404/no data → `False`; 429 → `MarketDataRateLimitError`; other failures → `MarketDataError`
- Simulator start prices: `initial_prices` → `SEED_PRICES` → `seed_price_for()` (SHA-256 of the ticker mapped into $50–300, stable across restarts)
- Massive: timestamps are nanoseconds (`last_trade.sip_timestamp / 1e9` — the library's `LastTrade` has no `timestamp` attribute, which the old code relied on); `prev_day.close` is the session open; first poll in `start()` raises `MarketDataAuthError` on 401/403. Requests go through the `RESTClient` connection pool directly with retries disabled, because the library's helpers hide HTTP status codes (`BadResponse`) and auto-retry 429s
- `create_stream_router()` builds a new `APIRouter` per call; the stream sends `retry: 1000` first, then a full snapshot whenever the cache version changes

## Test Suite

6 original test modules in `backend/tests/market/` (Massive mocks now use real `TickerSnapshot` objects with nanosecond timestamps) plus `test_session_and_lifecycle.py` for the §6 additions. Run `uv run --extra dev pytest tests/market`.

Original coverage at completion (73 tests):

| Module | Tests | Coverage |
|--------|-------|----------|
| test_models.py | 11 | models.py: 100% |
| test_cache.py | 13 | cache.py: 100% |
| test_simulator.py | 17 | simulator.py: 98% |
| test_simulator_source.py | 10 | (integration tests) |
| test_factory.py | 7 | factory.py: 100% |
| test_massive.py | 13 | massive_client.py: 56% (expected — API methods mocked) |

Overall coverage: 84%.

## Code Review & Fixes Applied

A comprehensive code review identified 7 issues. All were resolved:

1. **pyproject.toml build config** — added `[tool.hatch.build.targets.wheel] packages = ["app"]`
2. **Lazy imports removed** — `massive` is a core dependency; imports moved to top level
3. **SSE return type fixed** — `_generate_events` annotated as `AsyncGenerator[str, None]`
4. **Public `get_tickers()`** — added to `GBMSimulator` to avoid private attribute access
5. **Correlation constants cleaned up** — removed unused `DEFAULT_CORR`, consolidated into `CROSS_GROUP_CORR`
6. **Unused test imports removed** — `pytest`, `math`, `asyncio` cleaned from 4 test files
7. **Massive test mocks fixed** — `source._client` set in tests, patches target correct names

## Demo

A Rich terminal demo is available at `backend/market_data_demo.py`:

```bash
cd backend
uv run --extra dev market_data_demo.py   # rich is a dev dependency
```

Displays a live-updating dashboard with all 10 tickers, sparklines, color-coded direction arrows, and an event log for notable price moves. Runs 60 seconds or until Ctrl+C.

## Usage for Downstream Code

```python
from app.market import PriceCache, start_market_data_source

# Startup
cache = PriceCache()
source = await start_market_data_source(
    cache, ["AAPL", "GOOGL", "MSFT", ...], initial_prices={"AAPL": 191.2}
)  # Reads MASSIVE_API_KEY; falls back to the simulator on 401/403

# Read prices
update = cache.get("AAPL")          # PriceUpdate or None
price = cache.get_price("AAPL")     # float or None
all_prices = cache.get_all()        # dict[str, PriceUpdate]

# Dynamic tracked set (watchlist ∪ positions — managed by app.services)
if not await source.validate_ticker("PYPL"):  # only for untracked tickers
    ...
await source.add_ticker("TSLA")
await source.remove_ticker("GOOGL")

# Shutdown
await source.stop()
```
