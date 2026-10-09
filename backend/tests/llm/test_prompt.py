"""Prompt construction and action summaries."""

from app.llm.prompt import (
    HISTORY_LIMIT,
    SYSTEM_PROMPT,
    build_messages,
    format_portfolio_context,
    history_to_messages,
    summarize_actions,
)

TRADE_OK = {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5,
            "status": "executed", "error": None}
WATCH_FAIL = {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "failed",
              "error": "Unknown ticker: PYPL"}


def test_summarize_actions():
    assert summarize_actions([TRADE_OK, WATCH_FAIL]) == (
        "[buy 10 AAPL: executed @190.50; add PYPL: failed — Unknown ticker: PYPL]")
    assert summarize_actions([]) == ""
    assert summarize_actions(None) == ""


def test_history_appends_summary_to_assistant_only():
    history = [
        {"role": "user", "message": "buy 10 AAPL", "actions": None},
        {"role": "assistant", "message": "Buying 10 AAPL.", "actions": [TRADE_OK]},
        {"role": "assistant", "message": "Sure.", "actions": []},
    ]
    assert history_to_messages(history) == [
        {"role": "user", "content": "buy 10 AAPL"},
        {"role": "assistant", "content": "Buying 10 AAPL.\n[buy 10 AAPL: executed @190.50]"},
        {"role": "assistant", "content": "Sure."},
    ]


def test_portfolio_context_contents():
    summary = {
        "cash_balance": 8095.0, "total_value": 10012.4, "unrealized_pnl": 12.4,
        "positions": [{"ticker": "AAPL", "quantity": 10, "avg_cost": 190.5,
                       "current_price": 191.74, "market_value": 1917.4,
                       "unrealized_pnl": 12.4, "unrealized_pnl_percent": 0.65}],
    }
    watchlist = [{"ticker": "AAPL", "price": 191.74, "session_change_percent": 0.9},
                 {"ticker": "PYPL", "price": None, "session_change_percent": None}]
    text = format_portfolio_context(summary, watchlist)
    assert "Cash: $8,095.00" in text
    assert "Total value: $10,012.40" in text
    assert "AAPL: 10 sh, avg cost $190.50, price $191.74" in text
    assert "+0.65%" in text
    assert "AAPL: $191.74 (+0.90% today)" in text
    assert "PYPL: n/a" in text


def test_empty_portfolio_context():
    text = format_portfolio_context(
        {"cash_balance": 10000.0, "total_value": 10000.0, "unrealized_pnl": 0.0,
         "positions": []}, [])
    assert "Positions: none" in text and "Watchlist: empty" in text


def test_build_messages_order_and_history_cap():
    history = [{"role": "user", "message": f"m{i}", "actions": None} for i in range(30)]
    messages = build_messages("CONTEXT", history, "now")
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1] == {"role": "system", "content": "CONTEXT"}
    assert messages[-1] == {"role": "user", "content": "now"}
    middle = messages[2:-1]
    assert len(middle) == HISTORY_LIMIT == 20
    assert middle[0]["content"] == "m10"


def test_system_prompt_guidance():
    assert "FinAlly" in SYSTEM_PROMPT
    assert "Buying 10 AAPL" in SYSTEM_PROMPT
    assert "JSON" in SYSTEM_PROMPT
