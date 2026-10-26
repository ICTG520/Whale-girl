from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TurnTrigger(StrEnum):
    PRIVATE = "private"
    GROUP_AT = "group_at"
    GROUP_WAKE_WORD = "group_wake_word"


class TurnStatus(StrEnum):
    PENDING = "pending"
    GENERATED = "generated"
    SUPPRESSED = "suppressed"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Turn:
    """One reply attempt tied to a persisted inbound message."""

    id: str
    session_id: int
    inbound_message_id: int
    trigger_type: TurnTrigger
    status: TurnStatus
    persona_version: int
    started_at: datetime
    outbound_message_id: int | None = None
    completed_at: datetime | None = None
