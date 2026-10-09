"""handle_chat: parsing, retry, transport errors, execution, persistence."""

import json

from app import db
from app.llm import handle_chat
from app.llm.chat import (
    NOT_CONFIGURED_MESSAGE,
    PARSE_FAILURE_MESSAGE,
    UNAVAILABLE_MESSAGE,
    failure_note,
)
from app.llm.client import LLMTransportError


def reply(message="ok", trades=(), changes=()):
    return json.dumps(
        {"message": message, "trades": list(trades), "watchlist_changes": list(changes)})


def stored():
    return db.recent_chat_messages(50)


async def test_plain_reply_no_actions(ctx, services, llm):
    llm.script = [reply("Your portfolio is all cash.")]
    result = await handle_chat(ctx, "how am I doing?")
    assert result == {"message": "Your portfolio is all cash.", "actions": []}
    assert services.calls == []
    msgs = stored()
    assert [(m["role"], m["message"], m["actions"]) for m in msgs] == [
        ("user", "how am I doing?", None),
        ("assistant", "Your portfolio is all cash.", []),
    ]


async def test_prompt_contains_context_and_history(ctx, services, llm):
    db.insert_chat_message("user", "buy 10 AAPL", None)
    db.insert_chat_message("assistant", "Buying 10 AAPL.", [
        {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5,
         "status": "executed", "error": None}])
    llm.script = [reply()]
    await handle_chat(ctx, "and now?")
    messages = llm.calls[0]
    assert messages[0]["role"] == "system" and "FinAlly" in messages[0]["content"]
    assert "Cash: $10,000.00" in messages[1]["content"]
    assert "AAPL: $190.50" in messages[1]["content"]  # watchlist with live cache price
    assert messages[-3] == {"role": "user", "content": "buy 10 AAPL"}
    assert messages[-2]["content"].endswith("[buy 10 AAPL: executed @190.50]")
    assert messages[-1] == {"role": "user", "content": "and now?"}


async def test_executed_actions_shapes(ctx, services, llm):
    llm.script = [reply(
        "Buying 10 AAPL and adding PYPL.",
        trades=[{"ticker": "aapl", "side": "buy", "quantity": 10}],
        changes=[{"ticker": "PYPL", "action": "add"}],
    )]
    result = await handle_chat(ctx, "buy 10 AAPL and watch PYPL")
    assert result["message"] == "Buying 10 AAPL and adding PYPL."
    assert result["actions"] == [
        {"type": "watchlist", "ticker": "PYPL", "action": "add", "status": "executed",
         "error": None},
        {"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5,
         "status": "executed", "error": None},
    ]
    assert stored()[-1]["actions"] == result["actions"]


async def test_watchlist_changes_run_before_trades_in_array_order(ctx, services, llm):
    llm.script = [reply(
        trades=[{"ticker": "MSFT", "side": "buy", "quantity": 1},
                {"ticker": "AAPL", "side": "sell", "quantity": 2}],
        changes=[{"ticker": "PYPL", "action": "add"}, {"ticker": "TSLA", "action": "remove"}],
    )]
    await handle_chat(ctx, "do things")
    assert services.calls == [
        ("add", "PYPL"), ("remove", "TSLA"),
        ("trade", "MSFT", "buy", 1.0), ("trade", "AAPL", "sell", 2.0),
    ]


async def test_failed_action_reported_and_note_appended(ctx, services, llm):
    services.failures[("add", "PYPL")] = "Unknown ticker: PYPL"
    llm.script = [reply(
        "Buying 10 AAPL and adding PYPL to your watchlist.",
        trades=[{"ticker": "AAPL", "side": "buy", "quantity": 10}],
        changes=[{"ticker": "PYPL", "action": "add"}],
    )]
    result = await handle_chat(ctx, "buy 10 AAPL and watch PYPL")
    assert result["message"] == (
        "Buying 10 AAPL and adding PYPL to your watchlist."
        "\n\n⚠ 1 action failed — see details below.")
    assert result["actions"][0] == {
        "type": "watchlist", "ticker": "PYPL", "action": "add", "status": "failed",
        "error": "Unknown ticker: PYPL"}
    assert result["actions"][1]["status"] == "executed"
    assert stored()[-1]["message"] == result["message"]


async def test_failed_trade_has_null_price_and_plural_note(ctx, services, llm):
    services.failures[("trade", "AAPL")] = "Insufficient cash: need $19050.00, have $10000.00"
    services.failures[("trade", "MSFT")] = "Insufficient shares: have 0 MSFT"
    llm.script = [reply("Trying.", trades=[
        {"ticker": "AAPL", "side": "buy", "quantity": 100},
        {"ticker": "MSFT", "side": "sell", "quantity": 1}])]
    result = await handle_chat(ctx, "go")
    assert result["actions"][0] == {
        "type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 100, "price": None,
        "status": "failed", "error": "Insufficient cash: need $19050.00, have $10000.00"}
    assert result["message"].endswith("\n\n⚠ 2 actions failed — see details below.")


async def test_unexpected_service_error_becomes_failed_action(ctx, services, llm, monkeypatch):
    async def boom(*_args):
        raise RuntimeError("db exploded")

    monkeypatch.setattr("app.llm.actions.remove_ticker", boom)
    llm.script = [reply(changes=[{"ticker": "AAPL", "action": "remove"}])]
    result = await handle_chat(ctx, "remove AAPL")
    assert result["actions"][0]["status"] == "failed"
    assert result["actions"][0]["error"]


async def test_malformed_then_valid_retries_once(ctx, services, llm):
    llm.script = ["this is not json", reply("Fine now.")]
    result = await handle_chat(ctx, "hi")
    assert result == {"message": "Fine now.", "actions": []}
    assert len(llm.calls) == 2
    assert "not valid JSON" in llm.calls[1][-1]["content"]


async def test_malformed_twice_returns_apology(ctx, services, llm):
    llm.script = ["nope", '{"message": "missing arrays"}']
    result = await handle_chat(ctx, "hi")
    assert result == {"message": PARSE_FAILURE_MESSAGE, "actions": []}
    assert len(llm.calls) == 2
    assert stored()[-1]["message"] == PARSE_FAILURE_MESSAGE
    assert services.calls == []


async def test_transport_error_not_retried(ctx, services, llm):
    llm.script = [LLMTransportError("429 rate limited")]
    result = await handle_chat(ctx, "hi")
    assert result == {"message": UNAVAILABLE_MESSAGE, "actions": []}
    assert len(llm.calls) == 1
    assert [m["role"] for m in stored()] == ["user", "assistant"]
    assert stored()[-1] == {**stored()[-1], "message": UNAVAILABLE_MESSAGE, "actions": []}


async def test_transport_error_on_retry(ctx, services, llm):
    llm.script = ["garbage", LLMTransportError("timeout")]
    result = await handle_chat(ctx, "hi")
    assert result["message"] == UNAVAILABLE_MESSAGE


async def test_missing_api_key(ctx, services, llm, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    result = await handle_chat(ctx, "hi")
    assert result == {"message": NOT_CONFIGURED_MESSAGE, "actions": []}
    assert llm.calls == []
    assert stored()[-1]["message"] == NOT_CONFIGURED_MESSAGE


async def test_mock_mode_skips_llm_and_executes(ctx, services, llm, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "TRUE")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    result = await handle_chat(ctx, "buy 1 AAPL and add PYPL")
    assert llm.calls == []
    assert result["message"] == "Mock response: buy 1 AAPL, add PYPL"
    assert [a["type"] for a in result["actions"]] == ["watchlist", "trade"]
    assert services.calls == [("add", "PYPL"), ("trade", "AAPL", "buy", 1.0)]
    assert len(stored()) == 2


async def test_mock_mode_failure_note(ctx, services, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    services.failures[("trade", "AAPL")] = "Insufficient shares: have 0 AAPL"
    result = await handle_chat(ctx, "sell 5 AAPL")
    assert result["message"] == "Mock response: sell 5 AAPL" + failure_note(1)
