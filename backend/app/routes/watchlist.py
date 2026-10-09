"""Watchlist endpoints (PLAN §9)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import watchlist

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    ticker: str


@router.get("")
def get_watchlist(request: Request) -> list[dict[str, Any]]:
    return watchlist.list_items(request.app.state.market)


@router.post("", status_code=201)
async def post_watchlist(body: WatchlistAddRequest, request: Request) -> JSONResponse:
    item, created = await watchlist.add_ticker(request.app.state.market, body.ticker)
    return JSONResponse(item, status_code=201 if created else 200)


@router.delete("/{ticker}", status_code=204)
async def delete_watchlist(ticker: str, request: Request) -> Response:
    await watchlist.remove_ticker(request.app.state.market, ticker)
    return Response(status_code=204)
