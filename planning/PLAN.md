# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a provided start script (which wraps a single `docker run`). The start script opens a browser at `http://localhost:8000`. No login, no signup, and no `.env` is required. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger chart in the main chart area (same since-page-load data as the sparkline; no historical prices)
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog. Any valid ticker can be traded; buying a ticker not on the watchlist adds it automatically
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L %, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, unrealized P&L %
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language. Chat history survives a page reload
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot in the header (green = connected, yellow = reconnecting, red = disconnected; exact mapping in §11)
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Desktop-only**: optimized for wide screens (minimum supported width 1280px). No tablet/mobile layout

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving        │
│                      (Next.js export)           │
│                                                 │
│  SQLite database (named Docker volume)          │
│  Background tasks: market data sim/poller,      │
│                    portfolio snapshots (30s)    │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project. Entrypoint: `app.main:app`
- **Database**: SQLite, single file (path from `DB_PATH`), persisted in a named Docker volume
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if a key for a paid plan is provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues in production, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

### Startup Sequence (FastAPI `lifespan`)

Both background tasks (the market data source and the 30-second snapshot task) start and stop in the `lifespan` handler. They are independent: market data code never touches the database. Startup runs in this order:

1. Initialize the database (create tables, seed if needed — §7)
2. Read the tracked tickers (watchlist ∪ open positions) and, for each held ticker, its most recent trade price
3. `await source.start(tickers, initial_prices=last_trade_prices)` — the simulator writes prices immediately; Massive does its first poll
4. Record the startup portfolio snapshot (prices are now in the cache, so positions are valued at market, not cost)
5. Start the 30-second snapshot task

On shutdown: cancel the snapshot task, then `await source.stop()`.

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── app/
│       ├── main.py           # FastAPI app + lifespan (entrypoint app.main:app)
│       ├── market/           # Market data (complete — needs the §6 "Required changes")
│       └── db/               # Schema definitions, seed data, lazy init
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Local-dev location of finally.db (outside Docker)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── .env                      # Environment variables (gitignored)
├── .env.example              # Committed template; copied to .env by start scripts if missing
└── .gitignore
```

`db/.gitkeep` and `.env.example` don't exist yet and must be created.

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration.
- **`backend/app/market/`** is owned by the **Market Data agent**, including the follow-up changes listed in §6. Other backend code uses only its public interface (`MarketDataSource`, `PriceCache`, `create_market_data_source`, `create_stream_router`).
- **`backend/app/db/`** contains schema SQL definitions and seed logic.
- **`db/`** at the top level holds `finally.db` when the backend runs locally (outside Docker). Inside the container the database lives at `/app/db/finally.db` on a named volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

### Backend Dependencies

`pyproject.toml` must add `litellm` and `python-dotenv` to the runtime dependencies. Move `rich` (used only by `market_data_demo.py`) to the `dev` extra.

---

## 5. Environment Variables

```bash
# OpenRouter API key for LLM chat. Optional: without it the app still runs;
# chat returns a friendly "AI not configured" message (unless LLM_MOCK=true).
OPENROUTER_API_KEY=

# Optional: Massive (Polygon.io) API key for real market data.
# Requires a PAID Stocks plan (Starter or above) — the snapshot endpoints are
# not available on the free tier. If not set, the built-in simulator is used.
MASSIVE_API_KEY=

# Optional: Massive poll interval in seconds (default 5)
MASSIVE_POLL_INTERVAL=5

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false

# Optional (dev only): set to "true" to enable CORS for http://localhost:3000
DEV_CORS=false

# Optional: SQLite file path (default: <project root>/db/finally.db; Docker sets /app/db/finally.db)
DB_PATH=

# Optional: directory of the built frontend (default: backend/static; Docker sets /app/static)
STATIC_DIR=
```

`.env.example` contains exactly this block.

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses the Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If Massive's first poll fails with **401/403** (bad key or a plan without snapshot access) → log an error explaining that a paid plan is required, and **fall back to the simulator** so the app still works
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (see §10)
- If `OPENROUTER_API_KEY` is missing and `LLM_MOCK` is not `true` → the app starts normally; `POST /api/chat` returns an assistant message explaining that the AI is not configured
- If `STATIC_DIR` doesn't exist (e.g. local dev with `next dev`) → the backend skips the static mount instead of failing
- `.env` loading:
  - **In Docker**: variables are passed with `docker run --env-file .env`
  - **Locally**: the backend loads `../.env` relative to `backend/` (i.e. the project root `.env`) via `python-dotenv`; real environment variables take precedence

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- **Starting prices**, in priority order:
  1. `initial_prices` passed to `start()` — the backend passes the last trade price of every held ticker, so positions resume where they were after a restart
  2. the realistic seed price for known tickers (e.g., AAPL ~$190, GOOGL ~$175)
  3. for unknown tickers, a **deterministic** price derived from the ticker (a stable hash, such as SHA-256 — not Python's salted `hash()` — mapped into $50–300), so it is the same every restart
- Simulator prices are otherwise not persisted: unheld tickers restart from their seed price
- Runs as an in-process background task — no external dependencies

### Massive API (Optional, paid plan required)

- REST API polling (not WebSocket) of `GET /v2/snapshot/locale/us/markets/stocks/tickers` for all tracked tickers in one call
- **Requires a paid Massive Stocks plan.** Snapshot endpoints are not available on the free tier (see §5 for the fallback)
- Poll interval from `MASSIVE_POLL_INTERVAL` (default 5s), passed through `create_market_data_source()`
- **Timestamps are nanoseconds** in the REST API: `last_trade.timestamp / 1e9` → Unix seconds. The current code divides by 1000 (wrong), and its tests mock milliseconds; both must be fixed
- Parses REST response into the same format as the simulator

### Tracked Tickers

The market data source tracks **watchlist ∪ tickers with open positions**:

- Adding to the watchlist or buying a new ticker → `source.add_ticker()`
- Removing a ticker from the watchlist → `source.remove_ticker()` **only if** there is no open position in it
- Selling a position to zero → `source.remove_ticker()` **only if** the ticker is not on the watchlist
- On startup the source is started with the union of both sets

This keeps every held position priced even after it is removed from the watchlist.

### Ticker Validation (`validate_ticker`)

A new abstract method on `MarketDataSource`:

```python
async def validate_ticker(self, ticker: str) -> bool
```

- **Simulator**: always `True` (format is checked upstream, §8)
- **Massive**:
  - one-off `get_snapshot_ticker` call, run via `asyncio.to_thread` because the REST client blocks
  - data found → writes the price (with `session_open`) into the cache and returns `True`, so the ticker can be traded immediately
  - no data / 404 → returns `False`
  - 429 → raises `MarketDataRateLimitError`
- The backend calls it only for tickers that are **not already tracked**, and always **before** opening a database transaction (§8)

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, timestamp and session open for each ticker
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### Session Open Price

- `session_open` is a **field of `PriceUpdate`** (the frozen dataclass), so `to_dict()` can emit it
- `PriceCache.update(ticker, price, timestamp=None, session_open=None)`:
  - on the **first** write for a ticker, `session_open` = the explicit value if given and > 0, otherwise the price
  - on later writes, the stored `session_open` is carried forward and the argument is ignored
- **Simulator**: no explicit value, so the session open is the starting price
- **Massive**: passes `snap.prev_day.close` (previous day's close) when present and > 0
- `PriceCache.remove()` drops the ticker entirely, so a re-added ticker gets a new session open
- `PriceUpdate.to_dict()` adds `session_open` and `session_change_percent` = `(price − session_open) / session_open × 100` (0 if `session_open` is 0)

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- The server sends `retry: 1000` first, so the browser reconnects 1 second after a drop
- The server checks the cache version every ~500ms and, **whenever it changed**, sends **one event containing all tracked tickers** as a dict keyed by ticker:

```
data: {"AAPL": {"ticker": "AAPL", "price": 190.5, "previous_price": 190.42, "timestamp": 1760000000.123,
                "change": 0.08, "change_percent": 0.042, "direction": "up",
                "session_open": 190.0, "session_change_percent": 0.263},
       "GOOGL": {...}, ...}
```

- The **first event with data after every (re)connect is the full current snapshot**, so the frontend can render immediately on page load and after a reconnect
- With the simulator an event arrives about every 500ms. With Massive, every poll bumps the version even if prices are unchanged, so **events with identical prices are normal**
- `change` / `change_percent` / `direction` are relative to the **previous cache tick**, not the previous event the client saw. The frontend should not use them for flashing (§11)
- `session_open` / `session_change_percent` drive the watchlist **Chg %** column. Because they are server-side, Chg % survives page reloads
- **Timestamps**: SSE uses Unix seconds (float); REST endpoints use ISO 8601 UTC strings (§9)

### Required Changes to `backend/app/market/` (Market Data agent)

- [ ] `PriceUpdate`: add the `session_open` field; extend `to_dict()` with `session_open` and `session_change_percent`
- [ ] `PriceCache.update()`: add the `session_open=None` parameter with first-write semantics
- [ ] `PriceCache.remove()`: bump `version` so removed tickers disappear from the stream promptly
- [ ] `MarketDataSource`: add `validate_ticker()`. Change `start(tickers)` to `start(tickers, initial_prices: dict[str, float] | None = None)`
- [ ] Simulator: implement `initial_prices` and deterministic seed prices for unknown tickers
- [ ] Massive:
  - nanosecond timestamps
  - pass `prev_day.close` as the session open
  - implement `validate_ticker()` with 429 → `MarketDataRateLimitError`
  - raise on 401/403 at startup so the factory/lifespan can fall back to the simulator
- [ ] `create_market_data_source()`: read `MASSIVE_POLL_INTERVAL`
- [ ] `stream.py`: create the `APIRouter` **inside** `create_stream_router()`, so building the app twice (e.g. in tests) doesn't register `/prices` twice
- [ ] Update the existing tests (Massive mocks to nanoseconds) and `planning/MARKET_DATA_SUMMARY.md`

---

## 7. Database

### SQLite Access & Lazy Initialization

- **Driver**: stdlib `sqlite3`, one short-lived connection per operation. Route handlers that touch the DB are plain `def` (FastAPI runs them in its threadpool). Async code (lifespan, snapshot task, chat flow) wraps DB calls in `asyncio.to_thread`
- **Connection settings**: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON`
- **Path**: `DB_PATH` (default `<project root>/db/finally.db`); parent directory is created if missing
- **Initialization at startup**: `CREATE TABLE IF NOT EXISTS` for all tables. **Seed only if the `users_profile` row for `"default"` is missing**, so a user who empties their watchlist doesn't get it refilled on restart
- No separate migration step, no manual setup; fresh Docker volumes start with a clean, seeded database automatically

### Schema

Every table except `users_profile` has a `user_id` column defaulting to `"default"`; in `users_profile` the `id` column *is* the user key. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

All timestamps are stored as ISO 8601 UTC strings formatted `YYYY-MM-DDTHH:MM:SSZ` (format explicitly; don't use `isoformat()`, which emits `+00:00`).

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log). Not exposed by any endpoint or shown in the UI. It's used at startup for the last trade price of held tickers (§3), and kept for audit.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded:
- once on every app startup (on first launch this is the initial $10,000 point),
- every 30 seconds by a background task,
- and immediately after each trade execution.

Not pruned: growth is about 1M rows/year, which SQLite handles fine.

Columns:
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT (exposed as `message` in the API; for assistant replies it includes any system-appended failure note)
- `actions` TEXT (JSON list of action results — see §9; `null` for user messages, `[]` for assistant replies without actions)
- `created_at` TEXT

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. Trading Rules

These rules apply identically to manual trades (`POST /api/portfolio/trade`) and LLM trades.

- **Ticker format**: normalized to uppercase; must match `^[A-Z]{1,5}$`. This deliberately excludes share-class tickers like `BRK.B`. Don't "fix" this ad hoc
- **Ticker existence**: if the ticker isn't already tracked, call `source.validate_ticker()` (§6) **before** opening the transaction:
  - `False` → 400 `"Unknown ticker: {ticker}"`
  - `MarketDataRateLimitError` → 503 `"Market data rate limit reached — try again in a minute"`
  - the same applies to watchlist adds
- **Quantity**:
  - must be > 0 (enforced by the request model → 422 if not)
  - rounded to 4 decimal places; if it rounds to 0 → 400 `"Quantity too small"`
- **Price**: the current price from the price cache. If there's no price yet → 400 `"No price available yet for {ticker}"`
- **Buy**: rejected if `quantity × price > cash` → 400 `"Insufficient cash: need $X, have $Y"`. On success:
  - `avg_cost = (old_qty × old_avg + qty × price) / (old_qty + qty)`
  - cash decreases by `quantity × price`
  - if the ticker isn't on the watchlist, it is added automatically
- **Sell**: rejected if `quantity > held + 1e-6` → 400 `"Insufficient shares: have X {ticker}"`. If `quantity` exceeds `held` by less than 1e-6, it is clamped to `held`. On success:
  - `avg_cost` is unchanged
  - cash increases by `quantity × price`
  - the position row is deleted when the remaining quantity is < 1e-6
- **Cash** is rounded to 2 decimal places after every trade
- **Atomicity**: validation, cash update, position update, trade insert and post-trade snapshot run in a **single SQLite transaction** (`BEGIN IMMEDIATE`). No network calls happen inside the transaction

---

## 9. API Endpoints

All errors use FastAPI's default shape `{"detail": "human-readable message"}`:
- business-rule failures (insufficient cash, unknown ticker, no price, etc.) → **400**
- removing a ticker that isn't on the watchlist → **404**
- malformed request bodies → **422** (FastAPI default)
- market data rate limit on ticker validation → **503**

All REST timestamps are ISO 8601 UTC (`2026-10-07T14:03:11Z`).

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates (format in §6) |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |

`GET /api/portfolio` (positions ordered by ticker ascending):
```json
{
  "cash_balance": 8095.0,
  "total_value": 10012.4,
  "unrealized_pnl": 12.4,
  "positions": [
    {"ticker": "AAPL", "quantity": 10, "avg_cost": 190.5, "current_price": 191.74,
     "market_value": 1917.4, "unrealized_pnl": 12.4, "unrealized_pnl_percent": 0.65}
  ]
}
```
`current_price` is `null` (and the position is valued at `avg_cost`) if the cache has no price yet.

`POST /api/portfolio/trade` body `{"ticker": "AAPL", "quantity": 10, "side": "buy"}` → **200**:
```json
{"ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5,
 "cash_balance": 8095.0, "executed_at": "2026-10-07T14:03:11Z"}
```
Error example → **400** `{"detail": "Insufficient cash: need $1905.00, have $500.00"}`

`GET /api/portfolio/history` returns snapshots from the **last 24 hours**, oldest first. If there are more than 500, they are downsampled to 500 **evenly spaced by index, always keeping the first and last point**:
```json
[{"recorded_at": "2026-10-07T14:00:00Z", "total_value": 10000.0}, ...]
```

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

`GET /api/watchlist` (ordered by `added_at` ascending):
```json
[{"ticker": "AAPL", "price": 190.5, "previous_price": 190.42, "direction": "up",
  "session_open": 190.0, "session_change_percent": 0.263}, ...]
```
The price fields are `null` if no price is cached yet.

`POST /api/watchlist` → **201** with the new item in the same shape. Adding a ticker that is already present is a no-op returning **200**. `DELETE` → **204**.

### Chat
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat` | Recent chat history (last 50 messages, oldest first), for restoring the panel on page load |
| POST | `/api/chat` | Send a message: `{message}`. Returns the assistant reply plus action results |

`POST /api/chat` response:
```json
{
  "message": "Buying 10 AAPL and adding PYPL to your watchlist.\n\n⚠ 1 action failed — see details below.",
  "actions": [
    {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5,
     "status": "executed", "error": null},
    {"type": "watchlist", "ticker": "PYPL", "action": "add",
     "status": "failed", "error": "Unknown ticker: PYPL"}
  ]
}
```
`actions` is `[]` when the reply has no actions.

`GET /api/chat` items:
```json
[
  {"role": "user", "message": "buy 10 AAPL and watch PYPL", "actions": null, "created_at": "2026-10-07T14:03:10Z"},
  {"role": "assistant", "message": "Buying 10 AAPL and ...", "actions": [...], "created_at": "2026-10-07T14:03:11Z"}
]
```

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment): `{"status": "ok"}` |

---

## 10. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

`OPENROUTER_API_KEY` is read from the project-root `.env` if present (it is optional — §5).

**Fallback**: first confirm that the skill supports structured output (`response_format` with a JSON schema) for `gpt-oss-120b`. If it doesn't, request JSON mode and validate the reply with the same Pydantic model. On a parse failure, retry once. If the retry also fails, return the assistant message `"Sorry, I couldn't process that — please try again."` with no actions.

**Transport errors** (timeout, 401, 429, 5xx from OpenRouter):
- LLM call timeout is **30 seconds**; transport errors are not retried
- `POST /api/chat` still returns **200** with the assistant message `"The AI service is unavailable right now — please try again shortly."` and `actions: []`
- the turn is persisted like any other, so the frontend only ever handles one response shape

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the **last 20 messages** from the `chat_messages` table. Assistant messages include a compact summary of their action results (e.g. `[buy 10 AAPL: executed @190.50; add PYPL: failed — Unknown ticker]`), so the LLM knows what actually happened
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes **watchlist changes first, then trades**, each in array order, using the same rules as manual actions (§8). Each produces an action result with `status: "executed" | "failed"` and an `error` string
7. If any action failed, appends a system-generated note to the message (`"\n\n⚠ N action(s) failed — see details below."`). There is **no second LLM call**
8. Stores the user message, and the assistant message (including the note) with its action results, in `chat_messages`
9. Returns the response (shape in §9) to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema. Strict JSON-schema mode needs every property to be required and `additionalProperties: false`, so **both arrays are always present** (empty when unused):

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (string): the conversational text shown to the user
- `trades` (array): `side` is an enum `"buy" | "sell"`, `quantity` is a number > 0; validated per §8
- `watchlist_changes` (array): `action` is an enum `"add" | "remove"`
- One Pydantic model defines this schema. It's used for the `response_format`, for validating replies, and by mock mode

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

Failed actions are reported through their action result (`status: "failed"` plus `error`), which the frontend shows inline.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Phrase trade confirmations as intentions ("Buying 10 AAPL…"), since execution results are reported separately
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend skips OpenRouter and builds the response deterministically from the user message. Patterns are case-insensitive, and **all matches are processed in order of appearance**:

| Pattern | Resulting action |
|---|---|
| `buy <qty> <TICKER>` | trade buy (`qty` may be fractional, e.g. `0.5`) |
| `sell <qty> <TICKER>` | trade sell |
| `add <TICKER>` | watchlist add |
| `remove <TICKER>` | watchlist remove |
| anything else | no actions |

- The message is fixed text: `"Mock response: <summary of actions>"`, or `"Mock response: how can I help?"` when there are no actions
- Actions still run through the real execution path (same order rule as step 6), and messages are persisted to `chat_messages` as usual

This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

---

## 11. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. It has **one page only** — no dynamic routes, since a static export can't serve them. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers. **Rows come from `GET /api/watchlist`**; SSE only supplies their prices. The SSE ticker set (watchlist ∪ held) is *not* the watchlist, so a ticker disappearing from the stream is not a removal signal. Columns:
  - ticker symbol
  - current price (flashing green/red on change)
  - **Chg %**: `session_change_percent` from the SSE payload (change vs. the server-side session open, so it survives page reloads)
  - a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, using the same in-memory since-page-load price buffer as the sparklines (starts empty at page load; no history endpoint). Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by unrealized P&L **%** (green = profit, red = loss, color scale clamped to ±10%). With no positions, show a muted empty state ("No positions yet").
- **P&L chart** — line chart showing total portfolio value over time, using `GET /api/portfolio/history`
- **Positions table** — ticker, quantity, avg cost, current price, unrealized P&L, unrealized P&L %
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill. Errors (`detail`) are shown inline.
- **AI chat panel** — docked/collapsible sidebar:
  - message input and scrolling conversation history, loaded from `GET /api/chat` on page load
  - loading indicator while waiting for the LLM response
  - messages rendered as plain text (no markdown, no streaming, no editing)
  - each action shown inline as a chip: green when executed, red with the error when failed
- **Header** — portfolio total value, cash balance, connection status indicator

### Live Portfolio Valuation

The **header total, positions table and heatmap** all compute values client-side from the same data, so they never disagree:
- positions and cash come from `/api/portfolio`
- the price for each position is the latest SSE price; if there's none yet, use `current_price` from `/api/portfolio`, then `avg_cost`
- `market_value`, `unrealized_pnl`, `unrealized_pnl_percent` and the total are recomputed on every SSE event
- `/api/portfolio` (and `/api/watchlist` when relevant) is refetched after any trade, watchlist change, or chat response with actions

### Price Buffers, Flashing & Charts

- **Flash rule**: flash when `price !== lastRenderedPrice` for that ticker, green if higher and red if lower. Don't use the payload's `direction`, because SSE events can skip or double cache ticks. Identical-price events never flash
- **Buffers**: one ring buffer per watchlist ticker, capped at **600 points**, shared by the sparkline and the main chart. Buffers for tickers removed from the watchlist are dropped
- **Chart x-axis**: use the **client receive time**, not the payload `timestamp`. Lightweight Charts requires strictly increasing times in whole seconds, so **bucket per second (keep the last price)** and feed the chart with `series.update()`, which replaces a point with the same time
- **Charting libraries**:
  - **Lightweight Charts** (canvas) for the main price chart and the P&L line chart
  - small inline SVG for the sparklines
  - **Recharts `Treemap`** for the heatmap (Lightweight Charts has no treemap)

### Connection Status

Derived from the `EventSource`:
- **green**: `OPEN`
- **yellow**: `CONNECTING` (the browser retries every 1s thanks to `retry: 1000`)
- **red**: `CLOSED`, or stuck in `CONNECTING` for more than 10 seconds

If the `EventSource` reaches `CLOSED` (browsers stop retrying after HTTP errors), the frontend creates a new one after 5 seconds.

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Price flash effect: on a new price, briefly apply a CSS class with background color transition, then remove it
- In production all API calls go to the same origin (`/api/*`)
- Tailwind CSS for styling with a custom dark theme

### Local Development

Next.js `rewrites` don't work with `output: 'export'`. For local development:
- run the backend on `:8000` with `DEV_CORS=true` (enables CORS for `http://localhost:3000` only)
- run `next dev` on `:3000` with `NEXT_PUBLIC_API_BASE=http://localhost:8000`
- the frontend prefixes all API and SSE URLs with `NEXT_PUBLIC_API_BASE`, which is empty (same origin) in production builds

---

## 12. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm ci && npm run build (static export → frontend/out)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/ to /app
  - uv sync --frozen --no-dev
  - Copy frontend/out from stage 1 to /app/static
  - ENV DB_PATH=/app/db/finally.db STATIC_DIR=/app/static
  - EXPOSE 8000
  - HEALTHCHECK using Python (the slim image has no curl), e.g.
      python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
  - CMD: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

FastAPI serves the static frontend files and all API routes on port 8000. **All API routers must be registered before the static mount**, which is `StaticFiles(directory=STATIC_DIR, html=True)` at `/`.

### Docker Volume

The SQLite database persists via a **named Docker volume** (not a bind mount):

```bash
docker run -d --name finally -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The backend writes `/app/db/finally.db` inside the volume. To inspect it, use `docker cp finally:/app/db/finally.db .` or `docker exec`.

### Start/Stop Scripts

Keep the scripts minimal.

**`scripts/start_mac.sh`** (macOS/Linux):
1. If `.env` doesn't exist, copy `.env.example` to `.env` (since `docker run --env-file` fails on a missing file)
2. Build the image if it doesn't exist, or if `--build` is passed
3. `docker rm -f finally` to remove any old container (ignoring errors)
4. Run the `docker run` command above
5. Print `http://localhost:8000` and open it (`open` on macOS, `xdg-open` on Linux, ignoring failures)

**`scripts/stop_mac.sh`** (macOS/Linux):
- `docker rm -f finally`
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents (use `Start-Process` to open the browser).

All scripts are idempotent — safe to run multiple times. There is no root `docker-compose.yml`; the scripts are the only launch path.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 13. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data:
  - simulator generates valid prices, GBM math is correct, both implementations conform to the abstract interface
  - Massive response parsing, with **nanosecond** timestamps
  - `session_open` is set on the first write, carried forward, and cleared by `remove()`
  - `remove()` bumps `version`
  - deterministic seed prices for unknown tickers; `initial_prices` honored
  - `validate_ticker()`: found, not found, and 429 → `MarketDataRateLimitError`
  - 401/403 at startup → fallback to the simulator
- Portfolio:
  - trade execution logic and P&L calculations
  - selling more than owned, buying with insufficient cash, selling at a loss
  - selling the full position (row deleted, no float dust; sell clamp within 1e-6)
  - quantity rounding to 0 → 400
  - trading a ticker with no cached price
  - weighted `avg_cost` on repeated buys
- Tracked tickers: removing a held ticker from the watchlist keeps it priced; buying an unwatched ticker adds it to the watchlist
- DB: seeding only when the profile is missing; history downsampling (≤ 500 points, first and last kept)
- LLM:
  - structured output parsing handles all valid schemas
  - malformed responses → one retry, then an apology
  - transport errors → 200 apology
  - failed actions → `status: "failed"`
  - execution order: watchlist changes, then trades
  - mock-mode pattern parsing, including multiple commands and fractional quantities
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Flash triggers on `price !== lastRenderedPrice`, not on identical-price events
- Chg % column renders `session_change_percent`
- Watchlist rows come from the API, not from SSE keys
- Per-second bucketing and the 600-point buffer cap
- Watchlist CRUD operations
- Portfolio calculations: header, table and heatmap agree; price fallback order
- Chat message rendering, history restore, failed-action chips, and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` spins up the app container plus a Playwright container. The app container uses **no volume** (`DB_PATH` on a tmpfs), so every run starts from a fresh database. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` and the simulator (no `MASSIVE_API_KEY`).

**Ordering**: Playwright runs with `workers: 1`. The fresh-start spec runs first (file names prefixed `01-`, `02-`, …); later specs assert only relative changes, so they don't depend on exact earlier state.

**Assertions are relative, not exact.** Prices are random, so tests check that cash decreased or that a position row exists — never exact dollar values.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming, P&L chart has its initial point
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: a heatmap tile exists for each position, its color matches the sign of `unrealized_pnl` read from `/api/portfolio`, and the P&L chart has data points
- AI chat (mocked): send "buy 1 AAPL", receive a response, an executed trade chip appears inline; reload the page and the chat history is still there
- SSE resilience: block `/api/stream/prices` with Playwright `page.route` (abort), check the status dot leaves green, then unblock and check it returns to green. Don't use `context.setOffline`, which doesn't reliably close an open `EventSource`

---

## 14. Open Questions

None at present. Agents should add new questions here.
