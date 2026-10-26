from collections import defaultdict, deque

from whale_girl.ports.context import (
    ContextMessage,
    ConversationKey,
)


class InMemoryConversationContext:
    """Process-local short-term context; it intentionally does not persist."""

    def __init__(self, *, max_messages: int = 12) -> None:
        self._max_messages = max_messages
        self._messages: dict[ConversationKey, deque[ContextMessage]] = defaultdict(
            lambda: deque(maxlen=self._max_messages)
        )

    async def append(self, key: ConversationKey, message: ContextMessage) -> None:
        self._messages[key].append(message)

    async def load(
        self,
        key: ConversationKey,
        *,
        max_messages: int,
        max_chars: int,
        max_message_chars: int | None = None,
    ) -> list[ContextMessage]:
        messages = list(self._messages.get(key, ()))
        messages = messages[-max_messages:]
        if max_message_chars is not None:
            messages = [
                ContextMessage(
                    role=message.role,
                    content=message.content[:max_message_chars].rstrip(),
                )
                for message in messages
            ]

        selected: list[ContextMessage] = []
        used_chars = 0
        for message in reversed(messages):
            remaining = max_chars - used_chars
            if remaining <= 0:
                break
            content = message.content
            if len(content) > remaining:
                if not selected:
                    selected.append(
                        ContextMessage(role=message.role, content=content[-remaining:])
                    )
                break
            selected.append(message)
            used_chars += len(content)

        selected.reverse()
        return selected

    async def clear(self, key: ConversationKey) -> None:
        self._messages.pop(key, None)

    def stored_count(self, key: ConversationKey) -> int:
        return len(self._messages.get(key, ()))
