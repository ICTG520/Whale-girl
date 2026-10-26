from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    MessageOrigin,
    MessagePart,
    OutboundReply,
    StoredMessage,
)
from whale_girl.domain.turn import Turn, TurnStatus, TurnTrigger


MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                conversation_type TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE (platform, account_id, conversation_type, external_id)
            )
            """,
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                conversation_type TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                text TEXT NOT NULL,
                parts_json TEXT NOT NULL,
                raw_event_json TEXT NOT NULL,
                is_to_me INTEGER NOT NULL DEFAULT 0,
                is_self INTEGER NOT NULL DEFAULT 0,
                reply_to_message_id TEXT,
                UNIQUE (platform, account_id, message_id)
            )
            """,
            """
            CREATE INDEX idx_messages_conversation_time
            ON messages (
                platform,
                account_id,
                conversation_type,
                conversation_id,
                timestamp
            )
            """,
            """
            CREATE INDEX idx_messages_sender
            ON messages (platform, account_id, sender_id, timestamp)
            """,
        ),
    ),
    (
        2,
        (
            """
            ALTER TABLE messages
            ADD COLUMN origin TEXT NOT NULL DEFAULT 'inbound'
            """,
            """
            ALTER TABLE messages
            ADD COLUMN turn_id TEXT
            """,
            """
            ALTER TABLE messages
            ADD COLUMN conversation_ref_id INTEGER
            """,
            """
            UPDATE messages
            SET origin = CASE WHEN is_self = 1 THEN 'outbound' ELSE 'inbound' END
            """,
            """
            UPDATE messages
            SET conversation_ref_id = (
                SELECT conversations.id
                FROM conversations
                WHERE conversations.platform = messages.platform
                  AND conversations.account_id = messages.account_id
                  AND conversations.conversation_type = messages.conversation_type
                  AND conversations.external_id = messages.conversation_id
                LIMIT 1
            )
            """,
            """
            CREATE TABLE agent_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_ref_id INTEGER NOT NULL UNIQUE
                    REFERENCES conversations(id) ON DELETE CASCADE,
                state_json TEXT NOT NULL DEFAULT '{}',
                state_version INTEGER NOT NULL DEFAULT 1,
                last_summarized_message_id INTEGER,
                last_user_message_at TEXT,
                last_agent_message_at TEXT,
                last_seen_message_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE turns (
                id TEXT PRIMARY KEY,
                session_id INTEGER NOT NULL
                    REFERENCES agent_sessions(id) ON DELETE CASCADE,
                inbound_message_id INTEGER NOT NULL UNIQUE
                    REFERENCES messages(id),
                outbound_message_id INTEGER UNIQUE
                    REFERENCES messages(id),
                trigger_type TEXT NOT NULL,
                status TEXT NOT NULL,
                persona_version INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
            """,
            """
            CREATE INDEX idx_turns_session_started
            ON turns (session_id, started_at)
            """,
            """
            CREATE INDEX idx_messages_turn
            ON messages (turn_id)
            """,
            """
            INSERT INTO agent_sessions (
                conversation_ref_id,
                state_json,
                state_version,
                last_seen_message_id,
                created_at,
                updated_at
            )
            SELECT
                conversations.id,
                '{}',
                1,
                (
                    SELECT MAX(messages.id)
                    FROM messages
                    WHERE messages.conversation_ref_id = conversations.id
                ),
                conversations.first_seen_at,
                conversations.last_seen_at
            FROM conversations
            """,
        ),
    ),
)


class SQLiteMessageRepository:
    """Persist messages, sessions and reply turns in SQLite."""

    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self._path = Path(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            self._path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self._path) as db:
                await db.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                await db.commit()

                cursor = await db.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
                applied = {row[0] for row in await cursor.fetchall()}

                for version, statements in MIGRATIONS:
                    if version in applied:
                        continue
                    try:
                        await db.execute("BEGIN IMMEDIATE")
                        for statement in statements:
                            await db.execute(statement)
                        await db.execute(
                            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                            (version, _utc_now()),
                        )
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise

            self._initialized = True

    async def save_inbound(self, message: InboundMessage) -> StoredMessage | None:
        async with self._connect() as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                conversation_ref_id = await _upsert_conversation(
                    db,
                    platform=message.platform,
                    account_id=message.account_id,
                    conversation_type=message.conversation_type,
                    conversation_id=message.conversation_id,
                    title=_conversation_title(message),
                    timestamp=message.timestamp,
                )
                cursor = await db.execute(
                    """
                    INSERT INTO messages (
                        platform,
                        account_id,
                        conversation_type,
                        conversation_id,
                        message_id,
                        sender_id,
                        sender_name,
                        timestamp,
                        text,
                        parts_json,
                        raw_event_json,
                        is_to_me,
                        is_self,
                        reply_to_message_id,
                        origin,
                        turn_id,
                        conversation_ref_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.platform,
                        message.account_id,
                        message.conversation_type.value,
                        message.conversation_id,
                        message.message_id,
                        message.sender_id,
                        message.sender_name,
                        message.timestamp.isoformat(),
                        message.text,
                        _json_dumps(
                            [
                                {"type": part.type, "data": dict(part.data)}
                                for part in message.parts
                            ]
                        ),
                        _json_dumps(dict(message.raw_event)),
                        int(message.is_to_me),
                        int(message.is_self),
                        message.reply_to_message_id,
                        MessageOrigin.INBOUND.value,
                        None,
                        conversation_ref_id,
                    ),
                )
            except aiosqlite.IntegrityError:
                await db.rollback()
                return None
            except Exception:
                await db.rollback()
                raise

            message_ref_id = cursor.lastrowid
            if message_ref_id is None:
                await db.rollback()
                raise RuntimeError("SQLite did not return an inbound message ID")

            session_id = await _ensure_session(db, conversation_ref_id)
            updated_at = _utc_now()
            await db.execute(
                """
                UPDATE agent_sessions
                SET last_user_message_at = ?,
                    last_seen_message_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (message.timestamp.isoformat(), message_ref_id, updated_at, session_id),
            )
            await db.commit()
            return StoredMessage(
                id=message_ref_id,
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
        if message.conversation_ref_id is None:
            raise ValueError("Stored message has no conversation reference")

        turn_id = uuid.uuid4().hex
        started = started_at or _utc_now_datetime()
        async with self._connect() as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute(
                    "SELECT id FROM agent_sessions WHERE conversation_ref_id = ?",
                    (message.conversation_ref_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise RuntimeError("Agent session is missing for stored message")
                session_id = int(row["id"])
                await db.execute(
                    """
                    INSERT INTO turns (
                        id,
                        session_id,
                        inbound_message_id,
                        outbound_message_id,
                        trigger_type,
                        status,
                        persona_version,
                        started_at,
                        completed_at
                    ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL)
                    """,
                    (
                        turn_id,
                        session_id,
                        message.id,
                        trigger_type.value,
                        TurnStatus.PENDING.value,
                        persona_version,
                        started.isoformat(),
                    ),
                )
                cursor = await db.execute(
                    """
                    UPDATE messages
                    SET turn_id = ?
                    WHERE id = ? AND turn_id IS NULL
                    """,
                    (turn_id, message.id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Inbound message cannot be linked to turn: {message.id}"
                    )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return Turn(
            id=turn_id,
            session_id=session_id,
            inbound_message_id=message.id,
            trigger_type=trigger_type,
            status=TurnStatus.PENDING,
            persona_version=persona_version,
            started_at=started,
        )

    async def mark_turn_generated(self, turn_id: str) -> None:
        await self._set_turn_status(turn_id, TurnStatus.GENERATED)

    async def mark_turn_suppressed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None:
        await self._set_turn_status(
            turn_id,
            TurnStatus.SUPPRESSED,
            completed_at=completed_at or _utc_now_datetime(),
        )

    async def mark_turn_failed(
        self, turn_id: str, *, completed_at: datetime | None = None
    ) -> None:
        await self._set_turn_status(
            turn_id,
            TurnStatus.FAILED,
            completed_at=completed_at or _utc_now_datetime(),
        )

    async def save_outbound(
        self,
        reply: OutboundReply,
        *,
        platform_message_id: str | None,
        agent_name: str,
        sent_at: datetime | None = None,
    ) -> StoredMessage:
        sent = sent_at or _utc_now_datetime()
        message_id = (platform_message_id or "").strip()
        if not message_id:
            message_id = f"local:{uuid.uuid4().hex}"

        async with self._connect() as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                conversation_ref_id = await _upsert_conversation(
                    db,
                    platform=reply.platform,
                    account_id=reply.account_id,
                    conversation_type=reply.conversation_type,
                    conversation_id=reply.conversation_id,
                    title=None,
                    timestamp=sent,
                )
                cursor = await db.execute(
                    """
                    INSERT INTO messages (
                        platform,
                        account_id,
                        conversation_type,
                        conversation_id,
                        message_id,
                        sender_id,
                        sender_name,
                        timestamp,
                        text,
                        parts_json,
                        raw_event_json,
                        is_to_me,
                        is_self,
                        reply_to_message_id,
                        origin,
                        turn_id,
                        conversation_ref_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?)
                    """,
                    (
                        reply.platform,
                        reply.account_id,
                        reply.conversation_type.value,
                        reply.conversation_id,
                        message_id,
                        reply.account_id,
                        agent_name,
                        sent.isoformat(),
                        reply.text,
                        _json_dumps(
                            [
                                {
                                    "type": "text",
                                    "data": {"text": reply.text},
                                }
                            ]
                        ),
                        "{}",
                        reply.reply_to_message_id,
                        MessageOrigin.OUTBOUND.value,
                        reply.turn_id,
                        conversation_ref_id,
                    ),
                )
            except aiosqlite.IntegrityError:
                await db.rollback()
                existing = await self.get_by_message_id(
                    platform=reply.platform,
                    account_id=reply.account_id,
                    message_id=message_id,
                )
                if existing is not None:
                    return existing
                raise
            except Exception:
                await db.rollback()
                raise

            message_ref_id = cursor.lastrowid
            if message_ref_id is None:
                await db.rollback()
                raise RuntimeError("SQLite did not return an outbound message ID")

            session_id = await _ensure_session(db, conversation_ref_id)
            await db.execute(
                """
                UPDATE agent_sessions
                SET last_agent_message_at = ?,
                    last_seen_message_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (sent.isoformat(), message_ref_id, _utc_now(), session_id),
            )
            if reply.turn_id is not None:
                cursor = await db.execute(
                    """
                    UPDATE turns
                    SET outbound_message_id = ?,
                        status = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        message_ref_id,
                        TurnStatus.SENT.value,
                        sent.isoformat(),
                        reply.turn_id,
                    ),
                )
                if cursor.rowcount != 1:
                    await db.rollback()
                    raise RuntimeError(f"Turn not found: {reply.turn_id}")
            await db.commit()

        return StoredMessage(
            id=message_ref_id,
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

    async def get_by_message_id(
        self,
        *,
        platform: str,
        account_id: str,
        message_id: str,
    ) -> StoredMessage | None:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM messages
                WHERE platform = ? AND account_id = ? AND message_id = ?
                LIMIT 1
                """,
                (platform, account_id, message_id),
            )
            row = await cursor.fetchone()
        return _row_to_stored_message(row) if row is not None else None

    async def list_for_conversation(
        self,
        *,
        platform: str,
        account_id: str,
        conversation_type: ConversationType,
        external_id: str,
    ) -> list[StoredMessage]:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM messages
                WHERE platform = ?
                  AND account_id = ?
                  AND conversation_type = ?
                  AND conversation_id = ?
                ORDER BY id ASC
                """,
                (
                    platform,
                    account_id,
                    conversation_type.value,
                    external_id,
                ),
            )
            rows = await cursor.fetchall()
        return [_row_to_stored_message(row) for row in rows]

    async def list_recent(
        self,
        *,
        platform: str | None = None,
        account_id: str | None = None,
        conversation_type: ConversationType | None = None,
        external_id: str | None = None,
        limit: int = 50,
    ) -> list[StoredMessage]:
        safe_limit = max(1, min(limit, 500))
        clauses: list[str] = []
        params: list[Any] = []

        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform)
        if account_id is not None:
            clauses.append("account_id = ?")
            params.append(account_id)
        if conversation_type is not None:
            clauses.append("conversation_type = ?")
            params.append(conversation_type.value)
        if external_id is not None:
            clauses.append("conversation_id = ?")
            params.append(external_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        async with self._connect() as db:
            cursor = await db.execute(
                f"""
                SELECT *
                FROM messages
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params),
            )
            rows = await cursor.fetchall()

        return [_row_to_stored_message(row) for row in reversed(rows)]

    async def _set_turn_status(
        self,
        turn_id: str,
        status: TurnStatus,
        *,
        completed_at: datetime | None = None,
    ) -> None:
        async with self._connect() as db:
            cursor = await db.execute(
                """
                UPDATE turns
                SET status = ?,
                    completed_at = COALESCE(?, completed_at)
                WHERE id = ?
                """,
                (
                    status.value,
                    completed_at.isoformat() if completed_at is not None else None,
                    turn_id,
                ),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                raise RuntimeError(f"Turn not found: {turn_id}")
            await db.commit()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        await self.initialize()
        db = await aiosqlite.connect(self._path)
        try:
            db.row_factory = aiosqlite.Row
            await db.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            await db.execute("PRAGMA foreign_keys=ON")
            yield db
        finally:
            await db.close()


async def _upsert_conversation(
    db: aiosqlite.Connection,
    *,
    platform: str,
    account_id: str,
    conversation_type: ConversationType,
    conversation_id: str,
    title: str | None,
    timestamp: datetime,
) -> int:
    timestamp_text = timestamp.isoformat()
    await db.execute(
        """
        INSERT INTO conversations (
            platform,
            account_id,
            conversation_type,
            external_id,
            title,
            first_seen_at,
            last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform, account_id, conversation_type, external_id)
        DO UPDATE SET
            title = COALESCE(excluded.title, conversations.title),
            last_seen_at = CASE
                WHEN excluded.last_seen_at > conversations.last_seen_at
                THEN excluded.last_seen_at
                ELSE conversations.last_seen_at
            END
        """,
        (
            platform,
            account_id,
            conversation_type.value,
            conversation_id,
            title,
            timestamp_text,
            timestamp_text,
        ),
    )
    cursor = await db.execute(
        """
        SELECT id
        FROM conversations
        WHERE platform = ?
          AND account_id = ?
          AND conversation_type = ?
          AND external_id = ?
        """,
        (platform, account_id, conversation_type.value, conversation_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise RuntimeError("Conversation upsert did not return an ID")
    return int(row["id"])


async def _ensure_session(db: aiosqlite.Connection, conversation_ref_id: int) -> int:
    now = _utc_now()
    await db.execute(
        """
        INSERT INTO agent_sessions (
            conversation_ref_id,
            state_json,
            state_version,
            last_summarized_message_id,
            last_user_message_at,
            last_agent_message_at,
            last_seen_message_id,
            created_at,
            updated_at
        ) VALUES (?, '{}', 1, NULL, NULL, NULL, NULL, ?, ?)
        ON CONFLICT (conversation_ref_id) DO NOTHING
        """,
        (conversation_ref_id, now, now),
    )
    cursor = await db.execute(
        "SELECT id FROM agent_sessions WHERE conversation_ref_id = ?",
        (conversation_ref_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise RuntimeError("Agent session upsert did not return an ID")
    return int(row["id"])


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _conversation_title(message: InboundMessage) -> str | None:
    if message.conversation_type == ConversationType.PRIVATE:
        return message.sender_name
    return None


def _row_to_stored_message(row: aiosqlite.Row) -> StoredMessage:
    parts_data = json.loads(row["parts_json"] or "[]")
    raw_event = json.loads(row["raw_event_json"] or "{}")
    return StoredMessage(
        id=int(row["id"]),
        platform=str(row["platform"]),
        account_id=str(row["account_id"]),
        conversation_type=ConversationType(row["conversation_type"]),
        conversation_id=str(row["conversation_id"]),
        message_id=str(row["message_id"]),
        sender_id=str(row["sender_id"]),
        sender_name=str(row["sender_name"]),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        parts=tuple(
            MessagePart(type=str(item["type"]), data=dict(item.get("data", {})))
            for item in parts_data
        ),
        origin=MessageOrigin(row["origin"]),
        is_to_me=bool(row["is_to_me"]),
        is_self=bool(row["is_self"]),
        reply_to_message_id=row["reply_to_message_id"],
        turn_id=row["turn_id"],
        conversation_ref_id=(
            int(row["conversation_ref_id"])
            if row["conversation_ref_id"] is not None
            else None
        ),
        raw_event=raw_event if isinstance(raw_event, dict) else {},
    )
