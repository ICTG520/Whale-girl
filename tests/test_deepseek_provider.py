import logging
from types import SimpleNamespace
from typing import Any

import pytest

from whale_girl.infrastructure.llm.deepseek import DeepSeekProvider
from whale_girl.ports.llm import (
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMMessage,
    LLMProviderError,
    LLMRequest,
)


class FakeCompletions:
    def __init__(self, *, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, *, response: Any = None, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(
            completions=FakeCompletions(response=response, error=error)
        )


def make_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="系统人设",
        messages=(LLMMessage("user", "你好"),),
        max_output_tokens=128,
        temperature=0.7,
        timeout_seconds=12,
    )


def make_provider(client: FakeClient) -> DeepSeekProvider:
    return DeepSeekProvider(
        api_key="sk-test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        timeout_seconds=30,
        max_retries=1,
        client=client,
    )


async def test_deepseek_provider_maps_request_and_usage() -> None:
    response = SimpleNamespace(
        model="deepseek-chat",
        choices=[SimpleNamespace(message=SimpleNamespace(content="  你好呀  "))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3),
    )
    client = FakeClient(response=response)
    provider = make_provider(client)

    result = await provider.generate(make_request())

    assert result.text == "你好呀"
    assert result.input_tokens == 11
    assert result.output_tokens == 3
    assert client.chat.completions.kwargs["model"] == "deepseek-chat"
    assert client.chat.completions.kwargs["max_tokens"] == 128
    assert client.chat.completions.kwargs["messages"] == [
        {"role": "system", "content": "系统人设"},
        {"role": "user", "content": "你好"},
    ]


async def test_deepseek_without_key_raises_configuration_error() -> None:
    provider = DeepSeekProvider(
        api_key="",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        timeout_seconds=30,
        max_retries=1,
    )

    with pytest.raises(LLMConfigurationError, match="DEEPSEEK_API_KEY"):
        await provider.generate(make_request())


async def test_deepseek_empty_completion_is_rejected() -> None:
    response = SimpleNamespace(
        model="deepseek-chat",
        choices=[SimpleNamespace(message=SimpleNamespace(content="   "))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=0),
    )
    provider = make_provider(FakeClient(response=response))

    with pytest.raises(LLMEmptyResponseError):
        await provider.generate(make_request())


async def test_deepseek_failure_log_does_not_contain_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "sk-secret-that-must-not-be-logged"
    client = FakeClient(error=RuntimeError(f"request failed with {secret}"))
    provider = make_provider(client)
    caplog.set_level(logging.WARNING)

    with pytest.raises(LLMProviderError) as error:
        await provider.generate(make_request())

    assert secret not in str(error.value)
    assert secret not in caplog.text
