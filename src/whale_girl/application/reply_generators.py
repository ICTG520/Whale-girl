from __future__ import annotations

import logging
from dataclasses import dataclass

from whale_girl.application.ai_guard import AIRequestGuard
from whale_girl.domain.message import InboundMessage
from whale_girl.domain.persona import PersonaVersion
from whale_girl.ports.context import ConversationContextStore, ConversationKey
from whale_girl.ports.llm import (
    LLMEmptyResponseError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
)
from whale_girl.ports.limiter import AIRequestContext, AIRequestLimiter
from whale_girl.ports.reply_generator import ReplyGenerator

logger = logging.getLogger("whale_girl.application.reply_generators")


GROUP_CHAT_PROMPT_SUFFIX = """\n\n【群聊场景】
- 当前对话发生在一个多人群聊中，用户消息会以“成员昵称：内容”的形式出现。
- 只回应最后一条触发你的消息；可以参考最近群聊内容，但不要逐条回复所有人。
- 不要替其他成员发言，不要复述成员昵称，群聊回复通常控制在 1 到 2 句话。
"""


@dataclass(frozen=True, slots=True)
class AIReplyConfig:
    fallback_to_fixed: bool = True
    max_context_messages: int = 12
    max_context_chars: int = 6000
    max_input_chars: int = 2000
    max_reply_chars: int = 600
    max_output_tokens: int = 300
    temperature: float = 0.8
    timeout_seconds: float = 30.0
    cooldown_seconds: float = 2.0
    max_calls_per_minute: int = 10
    max_calls_per_day: int = 200
    system_prompt_suffix: str = ""


class FixedReplyGenerator:
    """Deterministic reply used before AI is configured or when it fails."""

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name

    async def generate(self, message: InboundMessage) -> str | None:
        return f"（骨架模式）{self._agent_name}收到消息了。"


class AIReplyGenerator:
    """Generate one conversation reply through the provider-neutral LLM port."""

    def __init__(
        self,
        *,
        persona: PersonaVersion,
        llm: LLMProvider,
        context_store: ConversationContextStore,
        config: AIReplyConfig,
        fixed_generator: ReplyGenerator,
        limiter: AIRequestLimiter | None = None,
    ) -> None:
        self._persona = persona
        self._llm = llm
        self._context_store = context_store
        self._config = config
        self._fixed_generator = fixed_generator
        self.limiter = limiter or AIRequestGuard(
            cooldown_seconds=config.cooldown_seconds,
            max_calls_per_minute=config.max_calls_per_minute,
            max_calls_per_day=config.max_calls_per_day,
        )

    async def generate(self, message: InboundMessage) -> str | None:
        key = ConversationKey.from_message(message)

        request_context = AIRequestContext.from_message(message)
        decision = self.limiter.begin(request_context)
        if not decision.allowed:
            logger.info("AI request skipped reason=%s", decision.reason)
            return None

        history = await self._context_store.load(
            key,
            max_messages=self._config.max_context_messages,
            max_chars=self._config.max_context_chars,
            max_message_chars=self._config.max_input_chars,
        )
        if not history:
            return await self._fallback(message, "empty_context")

        request = LLMRequest(
            system_prompt=(
                self._persona.system_prompt + self._config.system_prompt_suffix
            ),
            messages=tuple(
                LLMMessage(role=item.role, content=item.content) for item in history
            ),
            max_output_tokens=self._config.max_output_tokens,
            temperature=self._config.temperature,
            timeout_seconds=self._config.timeout_seconds,
        )

        try:
            result = await self._llm.generate(request)
            reply_text = self._sanitize_reply(result.text)
            if not reply_text:
                raise LLMEmptyResponseError("模型返回了空回复")

            self.limiter.record_usage(
                request_context,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            logger.info(
                "AI reply generated model=%s input_tokens=%s output_tokens=%s latency_ms=%.1f",
                result.model,
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
            )
            return reply_text
        except LLMError as exc:
            logger.warning("AI reply failed category=%s", type(exc).__name__)
            return await self._fallback(message, "llm_error")
        except Exception as exc:
            logger.warning("AI reply failed unexpectedly category=%s", type(exc).__name__)
            return await self._fallback(message, "unexpected_error")

    def _sanitize_reply(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) > self._config.max_reply_chars:
            cleaned = cleaned[: self._config.max_reply_chars].rstrip()
        return cleaned

    async def _fallback(
        self, message: InboundMessage, reason: str
    ) -> str | None:
        if not self._config.fallback_to_fixed:
            logger.info("AI reply suppressed reason=%s", reason)
            return None

        logger.info("AI reply falling back to fixed reply reason=%s", reason)
        return await self._fixed_generator.generate(message)

