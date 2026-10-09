"""FastAPI application: lifespan, routers and static frontend (entrypoint app.main:app)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.market import PriceCache, create_stream_router, start_market_data_source
from app.routes import chat, health, portfolio, watchlist
from app.services import ActionError, MarketContext
from app.services.portfolio import record_snapshot

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_STATIC_DIR = BACKEND_DIR / "static"
SNAPSHOT_INTERVAL = 30.0
DEV_CORS_ORIGIN = "http://localhost:3000"

# Local dev: load the project-root .env; real environment variables win.
load_dotenv(PROJECT_ROOT / ".env", override=False)

logger = logging.getLogger(__name__)


def _startup_state() -> tuple[list[str], dict[str, float]]:
    """Tracked tickers (watchlist ∪ positions) and last trade prices of held tickers."""
    tickers = db.tracked_tickers()
    held = [p.ticker for p in db.list_positions()]
    return tickers, db.last_trade_prices(held) if held else {}


async def _snapshot_loop(ctx: MarketContext, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(record_snapshot, ctx)
        except Exception:
            logger.exception("Portfolio snapshot failed")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def create_app(snapshot_interval: float = SNAPSHOT_INTERVAL) -> FastAPI:
    """Build a fresh app (own price cache and routers), so tests can create several."""
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(db.init_db)
        tickers, initial_prices = await asyncio.to_thread(_startup_state)
        source = await start_market_data_source(cache, tickers, initial_prices)
        ctx = MarketContext(cache=cache, source=source)
        app.state.market = ctx
        await asyncio.to_thread(record_snapshot, ctx)
        snapshot_task = asyncio.create_task(
            _snapshot_loop(ctx, snapshot_interval), name="portfolio-snapshots"
        )
        try:
            yield
        finally:
            snapshot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await snapshot_task
            await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    if _env_flag("DEV_CORS"):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[DEV_CORS_ORIGIN],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(ActionError)
    async def _action_error(_request: Request, exc: ActionError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    # All API routers before the static mount.
    app.include_router(create_stream_router(cache))
    app.include_router(health.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(chat.router)

    static_dir = Path(os.environ.get("STATIC_DIR", "").strip() or DEFAULT_STATIC_DIR)
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:
        logger.info("Static dir %s not found; serving API only", static_dir)

    return app


app = create_app()
