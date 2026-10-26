from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from whale_girl.ports.llm import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMResult,
    LLMTimeoutError,
)

logger = logging.getLogger("whale_girl.infrastructure.llm.deepseek")


class DeepSeekProvider:
    """DeepSeek chat provider through its OpenAI-compatible API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client
        if self._client is None and api_key:
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )

    async def generate(self, request: LLMRequest) -> LLMResult:
        if self._client is None:
            raise LLMConfigurationError("未配置 DEEPSEEK_API_KEY")

        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend(
            {"role": message.role, "content": message.content}
            for message in request.messages
        )

        started = perf_counter()
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=request.max_output_tokens,
                temperature=request.temperature,
                timeout=request.timeout_seconds,
            )
        except APITimeoutError as exc:
            self._log_failure(exc)
            raise LLMTimeoutError("DeepSeek 请求超时") from exc
        except AuthenticationError as exc:
            self._log_failure(exc)
            raise LLMAuthenticationError("DeepSeek 鉴权失败") from exc
        except RateLimitError as exc:
            self._log_failure(exc)
            raise LLMRateLimitError("DeepSeek 请求被限流") from exc
        except BadRequestError as exc:
            self._log_failure(exc)
            raise LLMProviderError("DeepSeek 拒绝了请求参数") from exc
        except APIConnectionError as exc:
            self._log_failure(exc)
            raise LLMConnectionError("无法连接 DeepSeek") from exc
        except APIStatusError as exc:
            self._log_failure(exc)
            raise LLMProviderError(
                f"DeepSeek 返回 HTTP {exc.status_code}"
            ) from exc
        except Exception as exc:
            self._log_failure(exc)
            raise LLMProviderError("DeepSeek 调用失败") from exc

        latency_ms = (perf_counter() - started) * 1000
        if not completion.choices:
            raise LLMEmptyResponseError("DeepSeek 没有返回候选回复")

        content = completion.choices[0].message.content
        text = str(content).strip() if content is not None else ""
        if not text:
            raise LLMEmptyResponseError("DeepSeek 返回了空回复")

        usage = getattr(completion, "usage", None)
        return LLMResult(
            text=text,
            model=str(getattr(completion, "model", None) or self._model),
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _log_failure(exc: Exception) -> None:
        logger.warning("DeepSeek request failed category=%s", type(exc).__name__)
