from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


LLMRole = Literal["user", "assistant"]


class LLMError(Exception):
    """Base error exposed by LLM providers to the application layer."""


class LLMConfigurationError(LLMError):
    """The provider is missing required local configuration."""


class LLMTimeoutError(LLMError):
    """The provider did not finish within the configured timeout."""


class LLMAuthenticationError(LLMError):
    """The provider rejected the configured credentials."""


class LLMRateLimitError(LLMError):
    """The provider rejected the request because of a rate limit."""


class LLMConnectionError(LLMError):
    """The provider could not be reached."""


class LLMProviderError(LLMError):
    """The provider returned an error or an invalid response."""


class LLMEmptyResponseError(LLMProviderError):
    """The provider returned no usable reply text."""


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system_prompt: str
    messages: tuple[LLMMessage, ...]
    max_output_tokens: int = 300
    temperature: float = 0.8
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


class LLMProvider(Protocol):
    """Provider-neutral boundary for chat completions."""

    async def generate(self, request: LLMRequest) -> LLMResult: ...
