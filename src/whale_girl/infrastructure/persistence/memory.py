from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone

from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    MessageOrigin,
    MessagePart,
    OutboundReply,
    StoredMessage,
)
from whale_girl.domain.turn import Turn, TurnStatus, TurnTrigger


ConversationIdentity = tuple[str, str, str, str]


class InMemoryMessageRepository:
    """In-memory repository used by unit tests and the walking skeleton."""

    def __init__(self) -> None:
        self._messages: list[StoredMessage] = []
        self._message_keys: set[tuple[str, str, str]] = set()
        self._next_message_id = 1
        self._conversation_refs: dict[ConversationIdentity, int] = {}
        self._session_ids: dict[ConversationIdentity, int] = {}
        self._next_session_id = 1
        self._turns: dict[str, Turn] = {}

    async def initialize(self) -> None:
        return None

    async def save_inbound(self, message: InboundMessage) -> StoredMessage | None:
        key = (message.platform, message.account_id, message.message_id)
        if key in self._message_keys:
            return None
        self._message_keys.add(key)

        identity = self._conversation_identity(message)
        conversation_ref_id = self._conversation_refs.setdefault(
            identity, len(self._conversation_refs) + 1
        )
        self._ensure_session_id(identity)

        stored = StoredMessage(
            id=self._next_message_id,
            platform=message.platform,
            account_id=message.account_id,
            conversation_type=message.conversation_type,
            conversation_id=message.conversation_id,
            message_id=message.message_id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            timestamp=message.timestamp,
            parts=message.parts,
            origin=MessageOrigin.INBOUND,
            is_to_me=message.is_to_me,
            is_self=message.is_self,
            reply_to_message_id=message.reply_to_message_id,
            turn_id=None,
            conversation_ref_id=conversation_ref_id,
            raw_event=message.raw_event,
        )
        self._next_message_id += 1
        self._messages.append(stored)
        return stored

    async def save(self, message: InboundMessage) -> bool:
        return await self.save_inbound(message) is not None

    async def create_turn(
        self,
        message: StoredMessage,
        *,
        trigger_type: TurnTrigger,
        persona_version: int,
        started_at: datetime | None = None,
    ) -> Turn:
        identity = (
            message.platform,
            message.account_id,
            message.conversation_type.value,
            message.conversation_id,
        )
        session_id = self._ensure_session_id(identity)
        turn = Turn(
            id=uuid.uuid4().hex,
            session_id=session_id,
            inbound_message_id=message.id,
            trigger_type=trigger_type,
            status=TurnStatus.PENDING,
            persona_version=persona_version,
            started_at=started_at or datetime.now(timezone.utc),
        )
        self._turns[turn.id] = turn
        for index, stored in enumerate(self._messages):
            if stored.id == message.id:
                self._messages[index] = replace(stored, turn_id=turn.id)
                break
        return turn

    async def mark_turn_generated(self, turn_id: str) -> None:
        self._set_turn_status(turn_id, TurnStatus.GENERATED)

    async def mark_turn_suppressed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None:
        self._set_turn_status(
            turn_id,
            TurnStatus.SUPPRESSED,
            completed_at=completed_at or datetime.now(timezone.utc),
        )

    async def mark_turn_failed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None:
        self._set_turn_status(
            turn_id,
            TurnStatus.FAILED,
            completed_at=completed_at or datetime.now(timezone.utc),
        )

    async def save_outbound(
        self,
        reply: OutboundReply,
        *,
        platform_message_id: str | None,
        agent_name: str,
        sent_at: datetime | None = None,
    ) -> StoredMessage:
        identity = (
            reply.platform,
            reply.account_id,
            reply.conversation_type.value,
            reply.conversation_id,
        )
        conversation_ref_id = self._conversation_refs.setdefault(
            identity, len(self._conversation_refs) + 1
        )
        self._ensure_session_id(identity)

        sent = sent_at or datetime.now(timezone.utc)
        message_id = (platform_message_id or "").strip() or f"local:{uuid.uuid4().hex}"
        stored = StoredMessage(
            id=self._next_message_id,
            platform=reply.platform,
            account_id=reply.account_id,
            conversation_type=reply.conversation_type,
            conversation_id=reply.conversation_id,
            message_id=message_id,
            sender_id=reply.account_id,
            sender_name=agent_name,
            timestamp=sent,
            parts=(MessagePart(type="text", data={"text": reply.text}),),
            origin=MessageOrigin.OUTBOUND,
            is_to_me=False,
            is_self=True,
            reply_to_message_id=reply.reply_to_message_id,
            turn_id=reply.turn_id,
            conversation_ref_id=conversation_ref_id,
            raw_event={},
        )
        self._next_message_id += 1
        self._messages.append(stored)

        if reply.turn_id is not None:
            turn = self._turns[reply.turn_id]
            self._turns[reply.turn_id] = replace(
                turn,
                outbound_message_id=stored.id,
                status=TurnStatus.SENT,
                completed_at=sent,
            )
        return stored

    async def list_for_conversation(
        self,
        *,
        platform: str,
        account_id: str,
        conversation_type: ConversationType,
        external_id: str,
    ) -> list[StoredMessage]:
        return [
            message
            for message in self._messages
            if message.platform == platform
            and message.account_id == account_id
            and message.conversation_type == conversation_type
            and message.conversation_id == external_id
        ]

    async def list_recent(
        self,
        *,
        platform: str | None = None,
        account_id: str | None = None,
        conversation_type: ConversationType | None = None,
        external_id: str | None = None,
        limit: int = 50,
    ) -> list[StoredMessage]:
        selected = [
            message
            for message in self._messages
            if (platform is None or message.platform == platform)
            and (account_id is None or message.account_id == account_id)
            and (
                conversation_type is None
                or message.conversation_type == conversation_type
            )
            and (external_id is None or message.conversation_id == external_id)
        ]
        return selected[-max(0, limit) :]

    @property
    def messages(self) -> tuple[StoredMessage, ...]:
        return tuple(self._messages)

    @property
    def turns(self) -> tuple[Turn, ...]:
        return tuple(self._turns.values())

    def _conversation_identity(self, message: InboundMessage) -> ConversationIdentity:
        return (
            message.platform,
            message.account_id,
            message.conversation_type.value,
            message.conversation_id,
        )

    def _ensure_session_id(self, identity: ConversationIdentity) -> int:
        if identity not in self._session_ids:
            self._session_ids[identity] = self._next_session_id
            self._next_session_id += 1
        return self._session_ids[identity]

    def _set_turn_status(
        self,
        turn_id: str,
        status: TurnStatus,
        *,
        completed_at: datetime | None = None,
    ) -> None:
        turn = self._turns[turn_id]
        self._turns[turn_id] = replace(
            turn,
            status=status,
            completed_at=completed_at or turn.completed_at,
        )
