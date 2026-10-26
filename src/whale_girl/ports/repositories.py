from datetime import datetime
from typing import Protocol

from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    OutboundReply,
    StoredMessage,
)
from whale_girl.domain.turn import Turn, TurnTrigger


class MessageRepository(Protocol):
    """Persistence boundary for observed messages."""

    async def initialize(self) -> None:
        """Create or migrate the backing store."""
        ...

    async def save_inbound(self, message: InboundMessage) -> StoredMessage | None:
        """Save an inbound message and return None when it was already stored."""
        ...

    async def save(self, message: InboundMessage) -> bool:
        """Compatibility helper returning whether an inbound message was new."""
        ...

    async def create_turn(
        self,
        message: StoredMessage,
        *,
        trigger_type: TurnTrigger,
        persona_version: int,
        started_at: datetime | None = None,
    ) -> Turn: ...

    async def mark_turn_generated(self, turn_id: str) -> None: ...

    async def mark_turn_suppressed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None: ...

    async def mark_turn_failed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None: ...

    async def save_outbound(
        self,
        reply: OutboundReply,
        *,
        platform_message_id: str | None,
        agent_name: str,
        sent_at: datetime | None = None,
    ) -> StoredMessage: ...

    async def list_for_conversation(
        self,
        *,
        platform: str,
        account_id: str,
        conversation_type: ConversationType,
        external_id: str,
    ) -> list[StoredMessage]: ...

    async def list_recent(
        self,
        *,
        platform: str | None = None,
        account_id: str | None = None,
        conversation_type: ConversationType | None = None,
        external_id: str | None = None,
        limit: int = 50,
    ) -> list[StoredMessage]:
        """Return recent messages in chronological order."""
        ...
