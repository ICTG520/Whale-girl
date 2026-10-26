from __future__ import annotations

from whale_girl.domain.message import MessageOrigin, render_message_for_context
from whale_girl.ports.context import (
    ContextMessage,
    ConversationKey,
)
from whale_girl.ports.repositories import MessageRepository


class SQLiteConversationContextStore:
    """Rebuild conversation context from the durable message log."""

    def __init__(self, repository: MessageRepository) -> None:
        self._repository = repository

    async def load(
        self,
        key: ConversationKey,
        *,
        max_messages: int,
        max_chars: int,
        max_message_chars: int | None = None,
    ) -> list[ContextMessage]:
        stored_messages = await self._repository.list_recent(
            platform=key.platform,
            account_id=key.account_id,
            conversation_type=key.conversation_type,
            external_id=key.conversation_id,
            limit=max_messages,
        )

        rendered: list[ContextMessage] = []
        for message in stored_messages:
            if message.origin == MessageOrigin.SYSTEM:
                continue
            content = render_message_for_context(
                conversation_type=message.conversation_type,
                sender_name=message.sender_name,
                parts=message.parts,
                is_self=message.is_self or message.origin == MessageOrigin.OUTBOUND,
                max_chars=max_message_chars,
            )
            if not content:
                continue
            is_agent_message = (
                message.is_self or message.origin == MessageOrigin.OUTBOUND
            )
            rendered.append(
                ContextMessage(
                    role="assistant" if is_agent_message else "user",
                    content=content,
                )
            )

        selected: list[ContextMessage] = []
        used_chars = 0
        for message in reversed(rendered):
            remaining = max_chars - used_chars
            if remaining <= 0:
                break
            if len(message.content) > remaining:
                if not selected:
                    selected.append(
                        ContextMessage(
                            role=message.role,
                            content=message.content[-remaining:],
                        )
                    )
                break
            selected.append(message)
            used_chars += len(message.content)

        selected.reverse()
        return selected
