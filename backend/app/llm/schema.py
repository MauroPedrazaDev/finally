"""Structured output schema for the chat assistant (PLAN §10).

`ChatReply` is the single source of truth: it builds the `response_format`
sent to the LLM, validates the reply, and is what mock mode produces.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class WatchlistChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: Literal["add", "remove"]


class ChatReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    trades: list[TradeInstruction]
    watchlist_changes: list[WatchlistChange]


# Keywords that strict JSON-schema modes reject or handle inconsistently across
# providers. Pydantic still enforces them when the reply is validated.
_STRIPPED_KEYWORDS = {"title", "exclusiveMinimum", "minimum", "default"}


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    """Resolve $refs, drop unsupported keywords, force strict-mode object rules."""
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _inline(copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]), defs)
    out = {k: _inline(v, defs) for k, v in node.items() if k not in _STRIPPED_KEYWORDS}
    out.pop("$defs", None)
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out


def chat_reply_json_schema() -> dict[str, Any]:
    """Self-contained strict JSON schema derived from `ChatReply`."""
    raw = ChatReply.model_json_schema()
    return _inline(raw, raw.get("$defs", {}))


def response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": "chat_reply", "strict": True, "schema": chat_reply_json_schema()},
    }
