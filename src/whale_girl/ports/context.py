from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from whale_girl.domain.message import ConversationType, InboundMessage


ContextRole = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class ConversationKey:
    platform: str
    account_id: str
    conversation_type: ConversationType
    conversation_id: str

    @classmethod
    def from_message(cls, message: InboundMessage) -> "ConversationKey":
        return cls(
            platform=message.platform,
            account_id=message.account_id,
            conversation_type=message.conversation_type,
            conversation_id=message.conversation_id,
        )


@dataclass(frozen=True, slots=True)
class ContextMessage:
    role: ContextRole
    content: str


class ConversationContextStore(Protocol):
    """Conversation history isolated by platform conversation."""

    async def load(
        self,
        key: ConversationKey,
        *,
        max_messages: int,
        max_chars: int,
        max_message_chars: int | None = None,
    ) -> list[ContextMessage]: ...
