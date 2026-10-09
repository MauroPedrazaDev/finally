"""Portfolio endpoints: summary, trade execution, value history (PLAN §9)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import db
from app.services.portfolio import portfolio_summary
from app.services.trading import execute_trade

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float = Field(gt=0, allow_inf_nan=False)
    side: Literal["buy", "sell"]


@router.get("")
def get_portfolio(request: Request) -> dict[str, Any]:
    return portfolio_summary(request.app.state.market)


@router.post("/trade")
async def post_trade(body: TradeRequest, request: Request) -> dict[str, Any]:
    return await execute_trade(request.app.state.market, body.ticker, body.side, body.quantity)


@router.get("/history")
def get_history() -> list[dict[str, Any]]:
    return db.get_history()
