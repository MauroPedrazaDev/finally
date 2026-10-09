"""Fixtures for LLM tests: temp DB, fake services, and a scripted LLM client.

Nothing here touches the network: `app.llm.client.complete` is always replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app import db
from app.market import PriceCache
from app.services import ActionError


@pytest.fixture(autouse=True)
def llm_env(monkeypatch, tmp_path):
    """Fresh temp DB and a clean LLM environment for every test."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    db.init_db()


@pytest.fixture
def ctx():
    cache = PriceCache()
    cache.update("AAPL", 190.5)
    return SimpleNamespace(cache=cache, source=None)


@dataclass
class FakeServices:
    """Records calls in order; `failures` maps (kind, ticker) to an error detail."""

    calls: list[tuple] = field(default_factory=list)
    failures: dict[tuple[str, str], str] = field(default_factory=dict)
    price: float = 190.5

    def _maybe_fail(self, kind: str, ticker: str) -> None:
        detail = self.failures.get((kind, ticker.upper()))
        if detail is not None:
            raise ActionError(400, detail)

    async def execute_trade(self, ctx, ticker, side, quantity):
        self.calls.append(("trade", ticker, side, quantity))
        self._maybe_fail("trade", ticker)
        return {
            "ticker": ticker.upper(),
            "side": side,
            "quantity": round(quantity, 4),
            "price": self.price,
            "cash_balance": 8095.0,
            "executed_at": "2026-10-07T14:03:11Z",
        }

    async def add_ticker(self, ctx, ticker):
        self.calls.append(("add", ticker))
        self._maybe_fail("add", ticker)
        return {"ticker": ticker.upper(), "price": None}, True

    async def remove_ticker(self, ctx, ticker):
        self.calls.append(("remove", ticker))
        self._maybe_fail("remove", ticker)


@pytest.fixture
def services(monkeypatch):
    fake = FakeServices()
    monkeypatch.setattr("app.llm.actions.execute_trade", fake.execute_trade)
    monkeypatch.setattr("app.llm.actions.add_ticker", fake.add_ticker)
    monkeypatch.setattr("app.llm.actions.remove_ticker", fake.remove_ticker)
    monkeypatch.setattr(
        "app.llm.chat.portfolio_summary",
        lambda ctx: {
            "cash_balance": 10000.0,
            "total_value": 10000.0,
            "unrealized_pnl": 0.0,
            "positions": [],
        },
    )
    return fake


class ScriptedLLM:
    """Stands in for `client.complete`: returns/raises the scripted items in order."""

    def __init__(self) -> None:
        self.script: list[Any] = []
        self.calls: list[list[dict[str, str]]] = []

    async def __call__(self, messages, api_key):
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def llm(monkeypatch):
    fake = ScriptedLLM()
    monkeypatch.setattr("app.llm.client.complete", fake)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return fake
