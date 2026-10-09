"""Deterministic mock replies for LLM_MOCK=true (PLAN §10)."""

from __future__ import annotations

import re

from .schema import ChatReply, TradeInstruction, WatchlistChange

_COMMAND = re.compile(
    r"\b(?:(?P<side>buy|sell)\s+(?P<qty>\d+(?:\.\d+)?|\.\d+)\s+(?P<trade_ticker>[a-z]+(?:\.[a-z]+)?)"
    r"|(?P<action>add|remove)\s+(?P<watch_ticker>[a-z]+(?:\.[a-z]+)?))",
    re.IGNORECASE,
)


def _fmt_qty(quantity: float) -> str:
    return f"{quantity:g}"


def mock_reply(user_message: str) -> ChatReply:
    trades: list[TradeInstruction] = []
    changes: list[WatchlistChange] = []
    summary: list[str] = []

    for match in _COMMAND.finditer(user_message):
        if match.group("side"):
            quantity = float(match.group("qty"))
            if quantity <= 0:
                continue
            side = match.group("side").lower()
            ticker = match.group("trade_ticker").upper()
            trades.append(TradeInstruction(ticker=ticker, side=side, quantity=quantity))
            summary.append(f"{side} {_fmt_qty(quantity)} {ticker}")
        else:
            action = match.group("action").lower()
            ticker = match.group("watch_ticker").upper()
            changes.append(WatchlistChange(ticker=ticker, action=action))
            summary.append(f"{action} {ticker}")

    text = "Mock response: " + (", ".join(summary) if summary else "how can I help?")
    return ChatReply(message=text, trades=trades, watchlist_changes=changes)
