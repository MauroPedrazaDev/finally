"""Prompt construction: system prompt, portfolio context, history (PLAN §10)."""

from __future__ import annotations

import json
from typing import Any

HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
The user trades a virtual portfolio with fake money; market orders fill instantly at the current price.

Your job:
- Analyze portfolio composition, risk concentration and P&L using the live context provided.
- Suggest trades with brief reasoning.
- Execute trades when the user asks for them or agrees to your suggestion, by listing them in "trades".
- Manage the watchlist proactively via "watchlist_changes" (add tickers the user is interested in, remove ones they no longer want).
- Be concise and data-driven. Use numbers from the context; never invent prices.
- Phrase trade and watchlist confirmations as intentions ("Buying 10 AAPL...", "Adding PYPL to your watchlist..."). Execution results are reported to the user separately, and some actions may fail.

Rules:
- Tickers are 1-5 uppercase letters (e.g. AAPL). Quantities are share counts > 0; fractional shares are allowed.
- Only include actions the user asked for or agreed to. When just analyzing or answering, leave both arrays empty.
- Buys need enough cash (quantity x price); sells cannot exceed the shares held.
- Earlier assistant turns end with a bracketed summary of what actually happened, e.g. [buy 10 AAPL: executed @190.50]. Trust those results.
- Always respond with valid JSON matching the required schema: {"message": string, "trades": [...], "watchlist_changes": [...]}. Both arrays are always present."""


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def format_portfolio_context(summary: dict[str, Any], watchlist: list[dict[str, Any]]) -> str:
    """Render the live portfolio and watchlist as compact text for the LLM."""
    lines = [
        "Current portfolio (live):",
        f"- Cash: {_money(summary.get('cash_balance'))}",
        f"- Total value: {_money(summary.get('total_value'))}",
        f"- Unrealized P&L: {_money(summary.get('unrealized_pnl'))}",
    ]
    positions = summary.get("positions") or []
    if positions:
        lines.append("Positions:")
        for p in positions:
            pct = p.get("unrealized_pnl_percent")
            pct_text = "n/a" if pct is None else f"{pct:+.2f}%"
            lines.append(
                f"- {p['ticker']}: {p['quantity']:g} sh, avg cost {_money(p.get('avg_cost'))}, "
                f"price {_money(p.get('current_price'))}, value {_money(p.get('market_value'))}, "
                f"P&L {_money(p.get('unrealized_pnl'))} ({pct_text})"
            )
    else:
        lines.append("Positions: none")

    if watchlist:
        lines.append("Watchlist:")
        for w in watchlist:
            chg = w.get("session_change_percent")
            chg_text = "" if chg is None else f" ({chg:+.2f}% today)"
            lines.append(f"- {w['ticker']}: {_money(w.get('price'))}{chg_text}")
    else:
        lines.append("Watchlist: empty")
    return "\n".join(lines)


def _action_summary(action: dict[str, Any]) -> str:
    if action.get("type") == "trade":
        label = f"{action.get('side')} {action.get('quantity'):g} {action.get('ticker')}"
    else:
        label = f"{action.get('action')} {action.get('ticker')}"
    if action.get("status") == "executed":
        price = action.get("price")
        return f"{label}: executed" + (f" @{price:.2f}" if price is not None else "")
    return f"{label}: failed — {action.get('error')}"


def summarize_actions(actions: list[dict[str, Any]] | None) -> str:
    """Compact `[buy 10 AAPL: executed @190.50; add PYPL: failed — ...]` summary."""
    if not actions:
        return ""
    return "[" + "; ".join(_action_summary(a) for a in actions) + "]"


def history_to_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = []
    for item in history:
        content = item["message"]
        if item["role"] == "assistant":
            summary = summarize_actions(item.get("actions"))
            if summary:
                content = f"{content}\n{summary}"
        messages.append({"role": item["role"], "content": content})
    return messages


def build_messages(
    context: str, history: list[dict[str, Any]], user_message: str
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context},
        *history_to_messages(history[-HISTORY_LIMIT:]),
        {"role": "user", "content": user_message},
    ]


def schema_reminder() -> str:
    """Corrective nudge appended on the single retry after an unparseable reply."""
    example = {"message": "...", "trades": [], "watchlist_changes": []}
    return (
        "Your previous reply was not valid JSON for the required schema. "
        f"Reply again with only a JSON object shaped like {json.dumps(example)}."
    )
