from dataclasses import dataclass

from whale_girl.domain.message import ConversationType


@dataclass(frozen=True, slots=True)
class Conversation:
    platform: str
    account_id: str
    conversation_type: ConversationType
    external_id: str
    title: str | None = None
