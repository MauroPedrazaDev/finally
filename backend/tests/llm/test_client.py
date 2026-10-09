"""client.complete against a fake `litellm` module (no network)."""

import sys
import types
from types import SimpleNamespace

import pytest

from app.llm import client
from app.llm.schema import response_format


@pytest.fixture
def fake_litellm(monkeypatch):
    module = types.ModuleType("litellm")
    module.calls = []
    module.result = None

    async def acompletion(**kwargs):
        module.calls.append(kwargs)
        if isinstance(module.result, Exception):
            raise module.result
        return module.result

    module.acompletion = acompletion
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def envelope(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


async def test_request_parameters(fake_litellm):
    fake_litellm.result = envelope('{"message": "hi"}')
    content = await client.complete([{"role": "user", "content": "x"}], "key-123")
    assert content == '{"message": "hi"}'
    kwargs = fake_litellm.calls[0]
    assert kwargs["model"] == "openrouter/openai/gpt-oss-120b"
    assert kwargs["extra_body"] == {"provider": {"order": ["cerebras"]}}
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["response_format"] == response_format()
    assert kwargs["api_key"] == "key-123"
    assert kwargs["timeout"] == 30
    assert kwargs["num_retries"] == 0 and kwargs["max_retries"] == 0


async def test_none_content_becomes_empty_string(fake_litellm):
    fake_litellm.result = envelope(None)
    assert await client.complete([], "k") == ""


@pytest.mark.parametrize("exc", [TimeoutError("t"), RuntimeError("401 Unauthorized"),
                                 ConnectionError("down")])
async def test_errors_become_transport_errors(fake_litellm, exc):
    fake_litellm.result = exc
    with pytest.raises(client.LLMTransportError):
        await client.complete([], "k")
    assert len(fake_litellm.calls) == 1


async def test_malformed_envelope(fake_litellm):
    fake_litellm.result = SimpleNamespace(choices=[])
    with pytest.raises(client.LLMTransportError):
        await client.complete([], "k")
