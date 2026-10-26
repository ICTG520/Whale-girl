from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from whale_girl.domain.message import ConversationType, InboundMessage


@dataclass(frozen=True, slots=True)
class AIRequestContext:
    """Identity of one AI request, without provider-specific details."""

    platform: str
    account_id: str
    conversation_type: ConversationType
    conversation_id: str
    sender_id: str

    @classmethod
    def from_message(cls, message: InboundMessage) -> "AIRequestContext":
        return cls(
            platform=message.platform,
            account_id=message.account_id,
            conversation_type=message.conversation_type,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
        )

    @property
    def conversation_key(self) -> str:
        return (
            f"{self.platform}:{self.account_id}:"
            f"{self.conversation_type.value}:{self.conversation_id}"
        )


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AIUsageSnapshot:
    day: date
    calls_today: int
    input_tokens_today: int
    output_tokens_today: int


class AIRequestLimiter(Protocol):
    """Replaceable policy boundary for AI admission and usage tracking."""

    def begin(self, request: AIRequestContext) -> LimitDecision: ...

    def record_usage(
        self,
        request: AIRequestContext,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> None: ...

    @property
    def snapshot(self) -> AIUsageSnapshot: ...
