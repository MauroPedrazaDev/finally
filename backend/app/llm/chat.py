"""Chat turn orchestration (PLAN §10 "How It Works")."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pydantic import ValidationError

from app import db
from app.services import MarketContext
from app.services.portfolio import portfolio_summary
from app.services.watchlist import list_items

from . import client
from .actions import execute_actions
from .mock import mock_reply
from .prompt import HISTORY_LIMIT, build_messages, format_portfolio_context, schema_reminder
from .schema import ChatReply

logger = logging.getLogger(__name__)

NOT_CONFIGURED_MESSAGE = (
    "The AI assistant is not configured. Add an OPENROUTER_API_KEY to your .env file "
    "and restart FinAlly to enable chat."
)
UNAVAILABLE_MESSAGE = "The AI service is unavailable right now — please try again shortly."
PARSE_FAILURE_MESSAGE = "Sorry, I couldn't process that — please try again."


def _is_mock() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def failure_note(failed: int) -> str:
    noun = "action" if failed == 1 else "actions"
    return f"\n\n⚠ {failed} {noun} failed — see details below."


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def parse_reply(content: str) -> ChatReply:
    """Validate raw LLM content against `ChatReply` (raises ValidationError)."""
    return ChatReply.model_validate_json(_strip_code_fence(content))


def _load_context(ctx: MarketContext) -> tuple[str, list[dict[str, Any]]]:
    context = format_portfolio_context(portfolio_summary(ctx), list_items(ctx))
    return context, db.recent_chat_messages(HISTORY_LIMIT)


async def _ask_llm(ctx: MarketContext, user_message: str, api_key: str) -> ChatReply | str:
    """Return a parsed reply, or a fixed assistant message when the LLM can't provide one."""
    context, history = await asyncio.to_thread(_load_context, ctx)
    messages = build_messages(context, history, user_message)
    for attempt in range(2):
        try:
            content = await client.complete(messages, api_key)
        except client.LLMTransportError:
            return UNAVAILABLE_MESSAGE
        try:
            return parse_reply(content)
        except ValidationError as exc:
            logger.warning("Unparseable LLM reply (attempt %d): %s", attempt + 1, exc)
            messages = [*messages, {"role": "user", "content": schema_reminder()}]
    return PARSE_FAILURE_MESSAGE


def _persist_turn(user_message: str, reply_text: str, actions: list[dict[str, Any]]) -> None:
    with db.transaction() as conn:
        db.insert_chat_message("user", user_message, None, conn=conn)
        db.insert_chat_message("assistant", reply_text, actions, conn=conn)


async def handle_chat(ctx: MarketContext, message: str) -> dict[str, Any]:
    """Run one chat turn and return the §9 `POST /api/chat` response."""
    actions: list[dict[str, Any]] = []
    if _is_mock():
        outcome: ChatReply | str = mock_reply(message)
    else:
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        outcome = await _ask_llm(ctx, message, api_key) if api_key else NOT_CONFIGURED_MESSAGE

    if isinstance(outcome, ChatReply):
        reply_text = outcome.message
        actions = await execute_actions(ctx, outcome)
        failed = sum(1 for a in actions if a["status"] == "failed")
        if failed:
            reply_text += failure_note(failed)
    else:
        reply_text = outcome

    await asyncio.to_thread(_persist_turn, message, reply_text, actions)
    return {"message": reply_text, "actions": actions}
