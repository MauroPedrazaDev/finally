"""LLM chat assistant: structured outputs via LiteLLM → OpenRouter → Cerebras.

Public API:
    handle_chat  - async (ctx, message) -> {"message", "actions"} (PLAN §9)
    ChatReply    - the structured output model (PLAN §10)
"""

from .chat import handle_chat
from .schema import ChatReply

__all__ = ["ChatReply", "handle_chat"]
