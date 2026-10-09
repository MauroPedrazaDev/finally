"""API route tests through the real app (lifespan, simulator, temp DB)."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from app.market.simulator import SimulatorDataSource


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-static"))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("DEV_CORS", raising=False)
    monkeypatch.setenv("LLM_MOCK", "true")
    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_startup_state(client):
    ctx = client.app.state.market
    assert isinstance(ctx.source, SimulatorDataSource)
    assert sorted(ctx.source.get_tickers()) == sorted(db.DEFAULT_WATCHLIST)
    history = client.get("/api/portfolio/history").json()
    assert len(history) == 1
    assert history[0]["total_value"] == 10000.0
    assert history[0]["recorded_at"].endswith("Z")


def test_fresh_portfolio(client):
    assert client.get("/api/portfolio").json() == {
        "cash_balance": 10000.0,
        "total_value": 10000.0,
        "unrealized_pnl": 0.0,
        "positions": [],
    }


def test_watchlist_get(client):
    items = client.get("/api/watchlist").json()
    assert [i["ticker"] for i in items] == list(db.DEFAULT_WATCHLIST)
    aapl = items[0]
    assert set(aapl) == {
        "ticker", "price", "previous_price", "direction", "session_open", "session_change_percent",
    }
    assert aapl["price"] > 0


def test_trade_buy_and_sell(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "aapl", "quantity": 2, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ticker", "side", "quantity", "price", "cash_balance", "executed_at"}
    assert body["ticker"] == "AAPL" and body["cash_balance"] < 10000

    portfolio = client.get("/api/portfolio").json()
    (pos,) = portfolio["positions"]
    assert pos["ticker"] == "AAPL" and pos["quantity"] == 2
    assert len(client.get("/api/portfolio/history").json()) == 2  # startup + post-trade

    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert r.status_code == 200
    assert client.get("/api/portfolio").json()["positions"] == []


def test_trade_business_errors_are_400(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Insufficient cash: need $")

    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Insufficient shares: have 0 AAPL"}

    r = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0.00001, "side": "buy"}
    )
    assert r.json() == {"detail": "Quantity too small"}

    r = client.post("/api/portfolio/trade", json={"ticker": "BRK.B", "quantity": 1, "side": "buy"})
    assert r.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"ticker": "AAPL", "quantity": 0, "side": "buy"},
        {"ticker": "AAPL", "quantity": -1, "side": "buy"},
        {"ticker": "AAPL", "quantity": 1, "side": "hold"},
        {"ticker": "AAPL", "side": "buy"},
        {"quantity": 1, "side": "buy"},
    ],
)
def test_trade_malformed_is_422(client, body):
    assert client.post("/api/portfolio/trade", json=body).status_code == 422


def test_buy_unwatched_ticker_adds_to_watchlist(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"})
    assert r.status_code == 200
    tickers = [i["ticker"] for i in client.get("/api/watchlist").json()]
    assert tickers[-1] == "PYPL"
    assert "PYPL" in client.app.state.market.source.get_tickers()


def test_watchlist_add_remove(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 201
    assert r.json()["ticker"] == "PYPL"
    assert r.json()["price"] > 0

    r = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r.status_code == 200

    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 204
    assert r.content == b""
    assert "PYPL" not in client.app.state.market.source.get_tickers()

    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_watchlist_validation(client):
    assert client.post("/api/watchlist", json={}).status_code == 422
    r = client.post("/api/watchlist", json={"ticker": "TOOLONG"})
    assert r.status_code == 400


def test_remove_held_ticker_keeps_it_priced(client):
    client.post("/api/portfolio/trade", json={"ticker": "NFLX", "quantity": 1, "side": "buy"})
    assert client.delete("/api/watchlist/NFLX").status_code == 204
    assert "NFLX" not in [i["ticker"] for i in client.get("/api/watchlist").json()]
    (pos,) = client.get("/api/portfolio").json()["positions"]
    assert pos["current_price"] is not None


def test_unknown_ticker_503_rate_limit(client, monkeypatch):
    from app.market import MarketDataRateLimitError

    async def limited(ticker):
        raise MarketDataRateLimitError("429")

    monkeypatch.setattr(client.app.state.market.source, "validate_ticker", limited)
    r = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r.status_code == 503
    assert r.json() == {"detail": "Market data rate limit reached — try again in a minute"}


def test_chat_router_registered(client):
    assert client.get("/api/chat").status_code == 200


def test_restart_resumes_held_ticker_price(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "no-static"))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        c.post("/api/portfolio/trade", json={"ticker": "PYPL", "quantity": 1, "side": "buy"})
        c.delete("/api/watchlist/PYPL")
        last_price = db.last_trade_prices(["PYPL"])["PYPL"]
    with TestClient(create_app()) as c:
        source = c.app.state.market.source
        assert "PYPL" in source.get_tickers()
        assert source._sim.get_price("PYPL") is not None
        # The simulator resumed from the last trade price (may have stepped once since)
        assert c.app.state.market.cache.get("PYPL").session_open == last_price


def test_static_mount(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATIC_DIR", str(static))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        assert "FinAlly" in c.get("/").text
        assert c.get("/api/health").json() == {"status": "ok"}


def test_dev_cors(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "none"))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.setenv("DEV_CORS", "true")
    with TestClient(create_app()) as c:
        r = c.get("/api/health", headers={"Origin": "http://localhost:3000"})
        assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
        r = c.get("/api/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in r.headers
