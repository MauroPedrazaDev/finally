"""GET/POST /api/chat on a minimal app (mock mode, fake services)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.routes.chat import router


@pytest.fixture
def http(ctx, services, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    app = FastAPI()
    app.include_router(router)
    app.state.market = ctx
    return TestClient(app)


def test_history_empty(http):
    response = http.get("/api/chat")
    assert response.status_code == 200
    assert response.json() == []


def test_post_then_history(http):
    response = http.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Mock response: buy 1 AAPL"
    assert body["actions"] == [
        {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 1, "price": 190.5,
         "status": "executed", "error": None}]

    history = http.get("/api/chat").json()
    assert [(m["role"], m["message"], m["actions"]) for m in history] == [
        ("user", "buy 1 AAPL", None),
        ("assistant", "Mock response: buy 1 AAPL", body["actions"]),
    ]
    assert all(m["created_at"].endswith("Z") for m in history)


def test_history_limited_to_last_50(http):
    for i in range(60):
        db.insert_chat_message("user", f"m{i}", None)
    history = http.get("/api/chat").json()
    assert len(history) == 50
    assert history[0]["message"] == "m10" and history[-1]["message"] == "m59"


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}, {"msg": "x"}])
def test_invalid_body_is_422(http, payload):
    assert http.post("/api/chat", json=payload).status_code == 422


def test_failed_action_still_200(http, services):
    services.failures[("add", "ZZZZ")] = "Unknown ticker: ZZZZ"
    response = http.post("/api/chat", json={"message": "add zzzz"})
    assert response.status_code == 200
    assert response.json()["actions"][0]["status"] == "failed"
    assert "⚠ 1 action failed" in response.json()["message"]


class _FakeSource:
    def __init__(self):
        self.tickers = {"AAPL"}

    def get_tickers(self):
        return list(self.tickers)

    async def validate_ticker(self, ticker):
        return True

    async def add_ticker(self, ticker):
        self.tickers.add(ticker)

    async def remove_ticker(self, ticker):
        self.tickers.discard(ticker)


def test_mock_chat_through_real_services(ctx, monkeypatch):
    """End-to-end over the real service layer: trade executes, failure is reported."""
    from app.services import MarketContext

    monkeypatch.setenv("LLM_MOCK", "true")
    app = FastAPI()
    app.include_router(router)
    app.state.market = MarketContext(cache=ctx.cache, source=_FakeSource())
    client = TestClient(app)

    body = client.post("/api/chat", json={"message": "buy 2 AAPL then sell 999 AAPL"}).json()
    assert [a["status"] for a in body["actions"]] == ["executed", "failed"]
    assert body["actions"][0]["price"] == 190.5
    assert body["actions"][1]["error"].startswith("Insufficient shares")
    assert body["message"].endswith("⚠ 1 action failed — see details below.")
    assert db.get_position("AAPL").quantity == 2
    assert db.get_cash() == 10000.0 - 381.0
