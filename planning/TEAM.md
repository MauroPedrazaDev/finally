# FinAlly Agent Team — Ownership & Contracts

PLAN.md is the spec. This file says **who owns what** and pins the **interfaces between owners**, so members can build in parallel. If you need to change a contract below, message the affected owners first, then update this file.

## Team

| Name (SendMessage) | Role | Owns (only edit these) |
|---|---|---|
| `database` | Database Engineer | `backend/app/db/**`, `backend/tests/db/**` |
| `backend` | Backend API Engineer | `backend/app/main.py`, `backend/app/routes/**` (except `chat.py`), `backend/app/services/**`, `backend/app/market/**` (PLAN §6 "Required changes"), `backend/pyproject.toml`, `backend/uv.lock`, `backend/tests/{market,routes,services}/**`, `backend/tests/conftest.py`, `planning/MARKET_DATA_SUMMARY.md`, `backend/CLAUDE.md` |
| `llm` | LLM Engineer | `backend/app/llm/**`, `backend/app/routes/chat.py`, `backend/tests/llm/**` |
| `frontend` | Frontend Engineer | `frontend/**` |
| `devops` | DevOps Engineer | `Dockerfile`, `.dockerignore`, `scripts/**`, `test/docker-compose.test.yml` |
| `tester` | Integration Tester | `test/**` except `test/docker-compose.test.yml` |

Everyone writes unit tests for their own code. Need a change in a file you don't own? **Message its owner** — don't edit it.

## Environment notes (Windows host)

- `uv` is not on PATH. Use: `/c/Users/mauro/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe` (Bash) or `C:\Users\mauro\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe` (PowerShell).
- Node 20.17 / npm 10.8, Docker 29 are available.
- Only `backend` runs `uv add` / edits `pyproject.toml` (avoids lockfile races). Others: `uv run --extra dev pytest tests/<yours>`.
- **Ports**: 8000 = DevOps container (`finally`). Backend/LLM local smoke runs use **8010+** (`uvicorn app.main:app --port 8010`). Frontend `next dev` on 3000. Tester's compose stack must not publish host port 8000.
- Local smoke tests should set `DB_PATH` to a temp file, never the real `db/finally.db`.
- **Do not `git commit` or push.** The lead commits.

## Contracts

### Database — `app.db` (owner: `database`)

Stdlib `sqlite3`, one short-lived connection per operation, pragmas per PLAN §7. All functions are **synchronous**; callers in async code wrap them in `asyncio.to_thread`. Functions that accept `conn` run inside the caller's transaction when given one; otherwise they open their own connection.

```python
from app.db import (
    init_db,            # () -> None: create tables; seed only if profile "default" missing
    get_db_path,        # () -> Path: DB_PATH env or <project root>/db/finally.db
    transaction,        # contextmanager -> sqlite3.Connection, BEGIN IMMEDIATE, commit/rollback
    now_iso,            # () -> "YYYY-MM-DDTHH:MM:SSZ"
    # profile
    get_cash,           # (conn=None) -> float
    set_cash,           # (conn, value: float) -> None
    # watchlist
    list_watchlist,     # (conn=None) -> list[str], ordered by added_at asc
    is_on_watchlist,    # (ticker, conn=None) -> bool
    add_to_watchlist,   # (ticker, conn=None) -> bool   True if inserted, False if already present
    remove_from_watchlist,  # (ticker, conn=None) -> bool  False if not present
    # positions
    list_positions,     # (conn=None) -> list[Position], ordered by ticker asc
    get_position,       # (ticker, conn=None) -> Position | None
    upsert_position,    # (conn, ticker, quantity, avg_cost) -> None
    delete_position,    # (conn, ticker) -> None
    # trades
    insert_trade,       # (conn, ticker, side, quantity, price) -> str executed_at
    last_trade_prices,  # (tickers: list[str] | None = None) -> dict[str, float]
    # tracked tickers
    tracked_tickers,    # () -> list[str]  watchlist ∪ positions
    # snapshots
    insert_snapshot,    # (total_value, conn=None) -> None
    get_history,        # (hours=24, max_points=500) -> list[{"recorded_at", "total_value"}] oldest first, downsampled per §9
    # chat
    insert_chat_message,    # (role, content, actions: list[dict] | None, conn=None) -> None
    recent_chat_messages,   # (limit=50) -> list[{"role","message","actions","created_at"}] oldest first, actions decoded from JSON
)
# Position: dataclass(ticker: str, quantity: float, avg_cost: float, updated_at: str)
```

### Services — `app.services` (owner: `backend`)

The single execution path for manual **and** LLM actions (PLAN §8). Async; DB work inside via `asyncio.to_thread`; `validate_ticker` before any transaction.

```python
from app.services import MarketContext, ActionError
# MarketContext: dataclass(cache: PriceCache, source: MarketDataSource) — stored on app.state.market
# ActionError(Exception): .status_code (400/404/503), .detail (str, exact PLAN §8/§9 message)

from app.services.trading import execute_trade
#   async (ctx, ticker: str, side: "buy"|"sell", quantity: float) -> dict   # §9 POST /api/portfolio/trade response
#   raises ActionError; records post-trade snapshot in the same transaction; manages tracked tickers (§6)
from app.services.watchlist import add_ticker, remove_ticker
#   add_ticker(ctx, ticker) -> tuple[dict, bool]   (§9 watchlist item, created)
#   remove_ticker(ctx, ticker) -> None              raises ActionError(404) if absent
from app.services.portfolio import portfolio_summary, portfolio_value
#   portfolio_summary(ctx) -> dict   (§9 GET /api/portfolio; sync, call via to_thread)
#   portfolio_value(ctx, conn=None) -> float
```

Inputs to services are raw; services normalize (uppercase) and validate format `^[A-Z]{1,5}$` and quantity rounding.

### LLM — `app.llm` + chat router (owner: `llm`)

```python
from app.routes.chat import router   # APIRouter with GET /api/chat and POST /api/chat; uses request.app.state.market
from app.llm import handle_chat       # async (ctx: MarketContext, message: str) -> {"message", "actions"}  (§9)
```

`backend` includes `app.routes.chat.router` in `main.py` before the static mount. `backend` adds `litellm` and `python-dotenv` to `pyproject.toml` first thing.

### App state & startup (owner: `backend`)

`app.state.market: MarketContext`. Lifespan order per PLAN §3. `create_app()` factory in `app/main.py` plus module-level `app = create_app()`, so tests can build fresh apps. Loads `../.env` via python-dotenv (real env wins).

### Frontend ↔ backend

Exactly the REST/SSE shapes in PLAN §6 and §9. `NEXT_PUBLIC_API_BASE` prefix (empty in production). Static export → `frontend/out`.

### E2E selectors (owners: `frontend` ↔ `tester`)

Frontend exposes stable `data-testid` attributes. Initial agreed set (extend by messaging each other):
`watchlist`, `watchlist-row-{TICKER}`, `price-{TICKER}`, `chg-{TICKER}`, `add-ticker-input`, `add-ticker-button`, `remove-ticker-{TICKER}`, `header-total-value`, `header-cash`, `connection-status` (with `data-status="connected|reconnecting|disconnected"`), `trade-ticker`, `trade-quantity`, `trade-buy`, `trade-sell`, `trade-error`, `positions-table`, `position-row-{TICKER}`, `heatmap`, `heatmap-tile-{TICKER}` (with `data-pnl-sign="positive|negative|zero"`), `pnl-chart` (with `data-points="{n}"`), `main-chart`, `chat-panel`, `chat-input`, `chat-send`, `chat-message` (with `data-role`), `chat-loading`, `action-chip` (with `data-status="executed|failed"`).
Added by `frontend`: `watchlist-error`, `chat-error`, `chat-toggle`; `main-chart` has `data-ticker` and `data-points`; `heatmap` has `data-tiles="{n}"`; `price-{TICKER}` has `data-flash="up|down"` while flashing; selected watchlist rows have `data-selected`.

## Workflow

1. `database`, `backend`, `llm`, `frontend`, `devops` start immediately. Code against the contracts; stub what you need from others in your tests.
2. When your piece is done and its unit tests pass, message `tester` with a short status.
3. `tester` writes the Playwright suite right away against the spec + selectors, then runs it once the container builds, and sends each failure to the owner with repro details. Owners fix and reply.
4. Report blockers to the owner directly. Stay available for fix requests until `tester` reports the suite green; your final result message goes to the lead.
