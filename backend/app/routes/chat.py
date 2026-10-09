"""Chat endpoints: GET/POST /api/chat (PLAN §9)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from app import db
from app.llm import handle_chat

HISTORY_PAGE = 50

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


@router.get("")
def get_chat_history() -> list[dict[str, Any]]:
    return db.recent_chat_messages(HISTORY_PAGE)


@router.post("")
async def post_chat(body: ChatRequest, request: Request) -> dict[str, Any]:
    return await handle_chat(request.app.state.market, body.message)
