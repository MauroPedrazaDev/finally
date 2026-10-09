"""ChatReply schema, strict response_format, and mock-mode parsing."""

import json

import pytest
from pydantic import ValidationError

from app.llm.chat import parse_reply
from app.llm.mock import mock_reply
from app.llm.schema import ChatReply, chat_reply_json_schema, response_format


class TestParseReply:
    @pytest.mark.parametrize(
        "payload",
        [
            {"message": "Hi", "trades": [], "watchlist_changes": []},
            {"message": "Buying", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
             "watchlist_changes": []},
            {"message": "Selling", "trades": [{"ticker": "aapl", "side": "sell", "quantity": 0.5}],
             "watchlist_changes": []},
            {"message": "Watching", "trades": [],
             "watchlist_changes": [{"ticker": "PYPL", "action": "add"},
                                   {"ticker": "TSLA", "action": "remove"}]},
            {"message": "Both", "trades": [{"ticker": "NVDA", "side": "buy", "quantity": 1.25}],
             "watchlist_changes": [{"ticker": "NVDA", "action": "add"}]},
        ],
    )
    def test_valid_variants(self, payload):
        reply = parse_reply(json.dumps(payload))
        assert reply.model_dump() == {
            **payload,
            "trades": [{**t, "quantity": float(t["quantity"])} for t in payload["trades"]],
        }

    def test_code_fenced_json_is_accepted(self):
        content = '```json\n{"message": "ok", "trades": [], "watchlist_changes": []}\n```'
        assert parse_reply(content).message == "ok"

    @pytest.mark.parametrize(
        "content",
        [
            "not json at all",
            "",
            '{"message": "x"}',
            '{"message": "x", "trades": [], "watchlist_changes": [], "extra": 1}',
            '{"message": "x", "trades": [{"ticker": "A", "side": "hold", "quantity": 1}], "watchlist_changes": []}',
            '{"message": "x", "trades": [{"ticker": "A", "side": "buy", "quantity": 0}], "watchlist_changes": []}',
            '{"message": "x", "trades": [], "watchlist_changes": [{"ticker": "A", "action": "watch"}]}',
        ],
    )
    def test_invalid_replies_raise(self, content):
        with pytest.raises(ValidationError):
            parse_reply(content)


class TestStrictSchema:
    def _objects(self, node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from self._objects(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._objects(item)

    def test_every_object_is_strict(self):
        schema = chat_reply_json_schema()
        objects = list(self._objects(schema))
        assert len(objects) == 3
        for obj in objects:
            assert obj["additionalProperties"] is False
            assert set(obj["required"]) == set(obj["properties"])

    def test_schema_is_self_contained(self):
        text = json.dumps(chat_reply_json_schema())
        assert "$ref" not in text and "$defs" not in text

    def test_enums_and_arrays(self):
        props = chat_reply_json_schema()["properties"]
        assert props["trades"]["items"]["properties"]["side"]["enum"] == ["buy", "sell"]
        assert props["watchlist_changes"]["items"]["properties"]["action"]["enum"] == [
            "add", "remove"]
        assert props["trades"]["items"]["properties"]["quantity"]["type"] == "number"

    def test_response_format_envelope(self):
        fmt = response_format()
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["schema"] == chat_reply_json_schema()


class TestMockReply:
    def test_no_commands(self):
        reply = mock_reply("hello there")
        assert reply == ChatReply(message="Mock response: how can I help?", trades=[],
                                  watchlist_changes=[])

    def test_single_buy(self):
        reply = mock_reply("buy 1 AAPL")
        assert [t.model_dump() for t in reply.trades] == [
            {"ticker": "AAPL", "side": "buy", "quantity": 1.0}]
        assert reply.message == "Mock response: buy 1 AAPL"

    def test_case_insensitive_and_fractional(self):
        reply = mock_reply("Please BUY 0.5 tsla and Sell .25 nvda.")
        assert [(t.side, t.quantity, t.ticker) for t in reply.trades] == [
            ("buy", 0.5, "TSLA"), ("sell", 0.25, "NVDA")]
        assert reply.message == "Mock response: buy 0.5 TSLA, sell 0.25 NVDA"

    def test_multiple_commands_in_order_of_appearance(self):
        reply = mock_reply("remove TSLA, buy 10 AAPL then add PYPL and sell 2 MSFT")
        assert [(c.action, c.ticker) for c in reply.watchlist_changes] == [
            ("remove", "TSLA"), ("add", "PYPL")]
        assert [(t.side, t.ticker) for t in reply.trades] == [("buy", "AAPL"), ("sell", "MSFT")]
        assert reply.message == (
            "Mock response: remove TSLA, buy 10 AAPL, add PYPL, sell 2 MSFT")

    def test_zero_quantity_is_ignored(self):
        assert mock_reply("buy 0 AAPL").trades == []

    def test_words_containing_keywords_do_not_match(self):
        assert mock_reply("my address is unknown").watchlist_changes == []

    def test_dotted_ticker_passed_through_for_upstream_validation(self):
        assert mock_reply("buy 1 brk.b").trades[0].ticker == "BRK.B"
