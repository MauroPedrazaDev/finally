"""LiteLLM → OpenRouter → Cerebras transport (cerebras-inference skill)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .schema import response_format

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
TIMEOUT_SECONDS = 30.0


class LLMTransportError(Exception):
    """Timeout, auth, rate limit, 5xx or any other failure to get a reply."""


async def complete(messages: list[dict[str, str]], api_key: str) -> str:
    """Request a structured `ChatReply` and return the raw JSON content.

    Transport errors are not retried (PLAN §10), so both LiteLLM's and the
    underlying client's retries are disabled.
    """
    import litellm  # imported lazily: it is slow to import and absent in some test envs

    try:
        response: Any = await asyncio.wait_for(
            litellm.acompletion(
                model=MODEL,
                messages=messages,
                response_format=response_format(),
                reasoning_effort="low",
                extra_body=EXTRA_BODY,
                api_key=api_key,
                timeout=TIMEOUT_SECONDS,
                num_retries=0,
                max_retries=0,
            ),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("LLM call failed: %s: %s", type(exc).__name__, exc)
        raise LLMTransportError(str(exc)) from exc

    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMTransportError(f"Malformed LLM response envelope: {exc}") from exc
