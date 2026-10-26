from pathlib import Path

import pytest

from whale_girl.bootstrap.persona import PersonaConfigError, load_persona
from whale_girl.domain.message import ConversationType
from whale_girl.infrastructure.persistence.memory_context import (
    InMemoryConversationContext,
)
from whale_girl.ports.context import ContextMessage, ConversationKey


def test_default_persona_loads_as_single_active_version() -> None:
    persona_path = Path(__file__).parents[1] / "config" / "persona.toml"

    persona = load_persona(persona_path)

    assert persona.name == "鲸鱼娘"
    assert persona.version == 1
    assert persona.active is True
    assert "不披露" in persona.system_prompt
    assert "不冒充真实人类" in persona.system_prompt


def test_persona_loader_rejects_missing_or_inactive_file(tmp_path: Path) -> None:
    with pytest.raises(PersonaConfigError, match="找不到"):
        load_persona(tmp_path / "missing.toml")

    inactive = tmp_path / "inactive.toml"
    inactive.write_text(
        'version = 1\nname = "test"\nactive = false\nsystem_prompt = "test"\n',
        encoding="utf-8",
    )
    with pytest.raises(PersonaConfigError, match="active"):
        load_persona(inactive)


async def test_context_keeps_recent_messages_and_isolates_conversations() -> None:
    store = InMemoryConversationContext(max_messages=3)
    first = ConversationKey("qq", "999", ConversationType.PRIVATE, "42")
    second = ConversationKey("qq", "999", ConversationType.PRIVATE, "43")

    for index in range(1, 5):
        await store.append(first, ContextMessage("user", f"message-{index}"))

    loaded = await store.load(first, max_messages=10, max_chars=100)

    assert [item.content for item in loaded] == [
        "message-2",
        "message-3",
        "message-4",
    ]
    assert store.stored_count(first) == 3
    assert await store.load(second, max_messages=10, max_chars=100) == []


async def test_context_trims_old_messages_by_character_budget() -> None:
    store = InMemoryConversationContext(max_messages=10)
    key = ConversationKey("qq", "999", ConversationType.PRIVATE, "42")
    await store.append(key, ContextMessage("user", "1234"))
    await store.append(key, ContextMessage("assistant", "5678"))

    loaded = await store.load(key, max_messages=10, max_chars=4)

    assert loaded == [ContextMessage("assistant", "5678")]


async def test_context_keeps_tail_of_a_single_oversized_message() -> None:
    store = InMemoryConversationContext(max_messages=10)
    key = ConversationKey("qq", "999", ConversationType.PRIVATE, "42")
    await store.append(key, ContextMessage("user", "abcdefghij"))

    loaded = await store.load(key, max_messages=10, max_chars=4)

    assert loaded == [ContextMessage("user", "ghij")]
