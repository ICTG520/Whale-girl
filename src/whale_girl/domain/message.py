from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class ConversationType(StrEnum):
    GROUP = "group"
    PRIVATE = "private"


class MessageOrigin(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class MessagePart:
    """A platform-neutral message segment."""

    type: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """A normalized message received from any social platform."""

    platform: str
    account_id: str
    conversation_type: ConversationType
    conversation_id: str
    message_id: str
    sender_id: str
    sender_name: str
    timestamp: datetime
    parts: tuple[MessagePart, ...]
    is_to_me: bool = False
    is_self: bool = False
    reply_to_message_id: str | None = None
    raw_event: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def text(self) -> str:
        return "".join(
            str(part.data.get("text", ""))
            for part in self.parts
            if part.type == "text"
        )


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """A message loaded from durable storage."""

    id: int
    platform: str
    account_id: str
    conversation_type: ConversationType
    conversation_id: str
    message_id: str
    sender_id: str
    sender_name: str
    timestamp: datetime
    parts: tuple[MessagePart, ...]
    origin: MessageOrigin = MessageOrigin.INBOUND
    is_to_me: bool = False
    is_self: bool = False
    reply_to_message_id: str | None = None
    turn_id: str | None = None
    conversation_ref_id: int | None = None
    raw_event: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def text(self) -> str:
        return "".join(
            str(part.data.get("text", ""))
            for part in self.parts
            if part.type == "text"
        )


@dataclass(frozen=True, slots=True)
class OutboundReply:
    """A platform-neutral reply produced by the application layer."""

    platform: str
    account_id: str
    conversation_type: ConversationType
    conversation_id: str
    text: str
    reply_to_message_id: str | None = None
    turn_id: str | None = None


_PART_PLACEHOLDERS = {
    "image": "[图片]",
    "face": "[表情]",
    "mface": "[表情包]",
    "record": "[语音]",
    "video": "[视频]",
    "file": "[文件]",
    "at": "[提及]",
    "reply": "[引用]",
    "json": "[卡片]",
    "xml": "[卡片]",
}


def render_message_for_context(
    *,
    conversation_type: ConversationType,
    sender_name: str,
    parts: tuple[MessagePart, ...],
    is_self: bool,
    max_chars: int | None = None,
) -> str:
    rendered: list[str] = []
    for part in parts:
        if part.type == "text":
            rendered.append(str(part.data.get("text", "")))
        else:
            rendered.append(_PART_PLACEHOLDERS.get(part.type, f"[{part.type}]"))

    content = "".join(rendered).strip()
    if not content:
        return ""
    if conversation_type == ConversationType.GROUP and not is_self:
        speaker = " ".join(sender_name.split())[:40] or "未知成员"
        content = f"{speaker}: {content}"
    if max_chars is not None:
        content = content[:max_chars].rstrip()
    return content
