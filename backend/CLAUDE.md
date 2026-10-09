# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Running Locally

```bash
DB_PATH=/tmp/finally.db LLM_MOCK=true uv run uvicorn app.main:app --port 8010
```

`app.main` loads the project-root `.env` (real env vars win). Port 8000 is reserved for the Docker container. Set `DEV_CORS=true` to allow `http://localhost:3000` (`next dev`). The static frontend is mounted from `STATIC_DIR` (default `backend/static`) only if that directory exists.

## Layout

| Path | Purpose |
|------|---------|
| `app/main.py` | `create_app()` factory + `app`; lifespan (PLAN §3): `init_db` → tracked tickers + last trade prices → `start_market_data_source` → startup snapshot → 30s snapshot task. Maps `ActionError` → `{"detail"}` JSON |
| `app/market/` | Market data (below) |
| `app/db/` | SQLite layer (contract in `planning/TEAM.md`) |
| `app/services/` | Single execution path for manual and LLM actions (PLAN §8) |
| `app/routes/` | `health`, `portfolio`, `watchlist`, `chat` (LLM-owned) routers |
| `app/llm/` | Chat flow (LLM-owned) |

## Services API

```python
from app.services import MarketContext, ActionError   # ctx lives on app.state.market
from app.services.trading import execute_trade        # async (ctx, ticker, side, quantity) -> dict
from app.services.watchlist import add_ticker, remove_ticker, list_items
from app.services.portfolio import portfolio_summary, portfolio_value, record_snapshot  # sync
```

- Services normalize tickers (uppercase, `^[A-Z]{1,5}$`) and quantities (4 dp); errors are `ActionError(status_code, detail)` with the exact PLAN messages.
- `validate_ticker()` runs only for untracked tickers and always before the DB transaction. Rate limit → 503.
- A trade (validation, cash, position, trade row, post-trade snapshot) is one `BEGIN IMMEDIATE` transaction.
- Tracked tickers = watchlist ∪ positions: buying an untracked ticker adds it to the source and the watchlist; removing from the watchlist or selling to zero calls `source.remove_ticker()` only when the ticker is neither held nor watched.

## Market Data API

```python
from app.market import (
    PriceCache, PriceUpdate, MarketDataSource,
    MarketDataError, MarketDataRateLimitError, MarketDataAuthError,
    create_market_data_source, start_market_data_source, create_stream_router,
)
```

- **`PriceUpdate`** — frozen dataclass: `ticker`, `price`, `previous_price`, `timestamp`, `session_open`; properties `change`, `change_percent`, `direction`, `session_change_percent`; `to_dict()` for JSON.
- **`PriceCache`** — thread-safe store: `update(ticker, price, timestamp=None, session_open=None)` (session open set on first write only), `get`, `get_price`, `get_all`, `remove` (bumps `version`), `version`.
- **`MarketDataSource`** — `start(tickers, initial_prices=None)`, `stop()`, `add_ticker()`, `remove_ticker()`, `validate_ticker()`, `get_tickers()`. Implemented by `SimulatorDataSource` and `MassiveDataSource`.
- **`create_market_data_source(cache)`** — Massive if `MASSIVE_API_KEY` is set (poll interval `MASSIVE_POLL_INTERVAL`, default 5s), else the simulator.
- **`start_market_data_source(cache, tickers, initial_prices)`** — creates and starts a source; on `MarketDataAuthError` (Massive 401/403) logs an error and starts the simulator instead.
- **`create_stream_router(cache)`** — new `APIRouter` per call with `GET /api/stream/prices` (SSE: `retry: 1000`, then one all-tickers event per cache version change).

Seed prices and GBM params are in `app/market/seed_prices.py`; unknown tickers get a deterministic SHA-256-derived price in $50–300 (`seed_price_for`).

## Running Tests

```bash
uv run --extra dev pytest -v              # All tests
uv run --extra dev pytest --cov=app       # With coverage
uv run --extra dev ruff check app/ tests/ # Lint
```

Tests: `tests/market`, `tests/services` (fake market source + temp DB), `tests/routes` (TestClient over `create_app()` with the simulator and a temp `DB_PATH`), `tests/db`, `tests/llm`.

## Demo

```bash
uv run --extra dev market_data_demo.py   # Live terminal dashboard (rich is a dev dependency)
```
