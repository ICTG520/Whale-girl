from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from whale_girl.application.handle_message import HandleInboundMessage
from whale_girl.application.reply_policy import ReplyPolicy
from whale_girl.bootstrap.config import Settings
from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    MessageOrigin,
    MessagePart,
    OutboundReply,
)
from whale_girl.domain.turn import TurnStatus, TurnTrigger
from whale_girl.infrastructure.persistence.sqlite import SQLiteMessageRepository
from whale_girl.infrastructure.persistence.sqlite_context import (
    SQLiteConversationContextStore,
)
from whale_girl.ports.context import ConversationKey


def make_message(
    *,
    message_id: str = "m1",
    text: str = "你好",
    conversation_type: ConversationType = ConversationType.GROUP,
    conversation_id: str = "807913552",
    sender_id: str = "3099225100",
    timestamp: datetime | None = None,
    parts: tuple[MessagePart, ...] | None = None,
    is_to_me: bool = False,
) -> InboundMessage:
    return InboundMessage(
        platform="qq",
        account_id="3424497994",
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name="测试用户",
        timestamp=timestamp or datetime(2026, 10, 24, 14, 45, tzinfo=timezone.utc),
        parts=parts or (MessagePart(type="text", data={"text": text}),),
        is_to_me=is_to_me,
        raw_event={"group_id": int(conversation_id), "message_id": message_id},
    )


async def test_sqlite_save_and_read_preserves_full_message(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    message = InboundMessage(
        platform="qq",
        account_id="3424497994",
        conversation_type=ConversationType.GROUP,
        conversation_id="807913552",
        message_id="m-image",
        sender_id="3099225100",
        sender_name="测试用户",
        timestamp=datetime(2026, 10, 24, 14, 45, tzinfo=timezone.utc),
        parts=(
            MessagePart(type="text", data={"text": "看图"}),
            MessagePart(type="image", data={"file": "abc.jpg", "url": "https://x"}),
        ),
        raw_event={"group_id": 807913552, "sender": {"nickname": "测试用户"}},
    )

    assert await repository.save(message) is True

    stored = await repository.list_for_conversation(
        platform="qq",
        account_id="3424497994",
        conversation_type=ConversationType.GROUP,
        external_id="807913552",
    )
    assert len(stored) == 1
    assert stored[0].text == "看图"
    assert stored[0].parts[1].type == "image"
    assert stored[0].parts[1].data["file"] == "abc.jpg"
    assert stored[0].raw_event["sender"]["nickname"] == "测试用户"

    async with aiosqlite.connect(repository.path) as db:
        cursor = await db.execute("SELECT * FROM conversations")
        conversations = await cursor.fetchall()
        cursor = await db.execute("SELECT version FROM schema_migrations")
        migrations = await cursor.fetchall()
    assert len(conversations) == 1
    assert conversations[0][5] is None
    assert migrations == [(1,), (2,)]


async def test_sqlite_deduplicates_message_id(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    message = make_message(message_id="duplicate")

    assert await repository.save(message) is True
    assert await repository.save(message) is False

    stored = await repository.list_recent(limit=10)
    assert len(stored) == 1


async def test_sqlite_records_survive_repository_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "messages.sqlite3"
    first = SQLiteMessageRepository(database_path)
    await first.save(make_message(message_id="persisted", text="重启后还在"))

    second = SQLiteMessageRepository(database_path)
    stored = await second.list_recent(limit=10)

    assert len(stored) == 1
    assert stored[0].message_id == "persisted"
    assert stored[0].text == "重启后还在"


async def test_sqlite_recent_filter_and_chronological_order(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    base = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
    await repository.save(
        make_message(message_id="g1-1", conversation_id="807913552", timestamp=base)
    )
    await repository.save(
        make_message(
            message_id="g2-1",
            conversation_id="800000000",
            text="另一个群",
            timestamp=base + timedelta(seconds=1),
        )
    )
    await repository.save(
        make_message(
            message_id="g1-2",
            conversation_id="807913552",
            text="第二句",
            timestamp=base + timedelta(seconds=2),
        )
    )

    recent = await repository.list_recent(
        conversation_type=ConversationType.GROUP,
        external_id="807913552",
        limit=2,
    )

    assert [message.message_id for message in recent] == ["g1-1", "g1-2"]


async def test_group_outside_whitelist_is_not_persisted(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    settings = Settings(qq_group_whitelist=frozenset({"807913552"}))
    handler = HandleInboundMessage(
        settings=settings,
        repository=repository,
        reply_policy=ReplyPolicy(settings),
    )

    await handler.execute(make_message(message_id="allowed"))
    await handler.execute(
        make_message(message_id="other-group", conversation_id="800000000")
    )

    stored = await repository.list_recent(limit=10)
    assert [message.message_id for message in stored] == ["allowed"]


LEGACY_V1_SCHEMA = (
    """
    CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
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
)


async def _create_legacy_v1_database(path: Path) -> None:
    timestamp = "2026-10-24T14:45:00+00:00"
    async with aiosqlite.connect(path) as db:
        for statement in LEGACY_V1_SCHEMA:
            await db.execute(statement)
        await db.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)",
            (timestamp,),
        )
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
            ) VALUES ('qq', '3424497994', 'group', '807913552', NULL, ?, ?)
            """,
            (timestamp, timestamp),
        )
        await db.execute(
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
                reply_to_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qq",
                "3424497994",
                "group",
                "807913552",
                "legacy-in",
                "3099225100",
                "旧消息用户",
                timestamp,
                "旧入站消息",
                '[{"type": "text", "data": {"text": "旧入站消息"}}]',
                "{}",
                0,
                0,
                None,
            ),
        )
        await db.execute(
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
                reply_to_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qq",
                "3424497994",
                "group",
                "807913552",
                "legacy-out",
                "3424497994",
                "鲸鱼娘",
                timestamp,
                "旧出站消息",
                '[{"type": "text", "data": {"text": "旧出站消息"}}]',
                "{}",
                0,
                1,
                "legacy-in",
            ),
        )
        await db.commit()


async def _turn_row(path: Path, turn_id: str) -> aiosqlite.Row:
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM turns WHERE id = ?", (turn_id,))
        row = await cursor.fetchone()
    assert row is not None
    return row


async def test_v1_database_migrates_to_v2_without_data_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    await _create_legacy_v1_database(database_path)

    repository = SQLiteMessageRepository(database_path)
    await repository.initialize()

    stored = await repository.list_for_conversation(
        platform="qq",
        account_id="3424497994",
        conversation_type=ConversationType.GROUP,
        external_id="807913552",
    )
    assert [message.message_id for message in stored] == [
        "legacy-in",
        "legacy-out",
    ]
    assert [message.origin for message in stored] == [
        MessageOrigin.INBOUND,
        MessageOrigin.OUTBOUND,
    ]
    assert stored[0].conversation_ref_id is not None
    assert stored[0].conversation_ref_id == stored[1].conversation_ref_id

    async with aiosqlite.connect(database_path) as db:
        cursor = await db.execute("SELECT version FROM schema_migrations ORDER BY version")
        assert await cursor.fetchall() == [(1,), (2,)]
        cursor = await db.execute(
            "SELECT conversation_ref_id, last_seen_message_id FROM agent_sessions"
        )
        assert await cursor.fetchall() == [(stored[0].conversation_ref_id, 2)]
        cursor = await db.execute("PRAGMA integrity_check")
        assert await cursor.fetchone() == ("ok",)


async def test_outbound_reply_is_persisted_after_success(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    inbound = await repository.save_inbound(
        make_message(message_id="in-1", text="在吗", conversation_type=ConversationType.PRIVATE)
    )
    assert inbound is not None

    turn = await repository.create_turn(
        inbound,
        trigger_type=TurnTrigger.PRIVATE,
        persona_version=3,
    )
    assert (await _turn_row(repository.path, turn.id))["status"] == TurnStatus.PENDING
    linked_inbound = await repository.get_by_message_id(
        platform="qq",
        account_id="3424497994",
        message_id="in-1",
    )
    assert linked_inbound is not None
    assert linked_inbound.turn_id == turn.id

    await repository.mark_turn_generated(turn.id)
    assert (await _turn_row(repository.path, turn.id))["status"] == TurnStatus.GENERATED

    sent_at = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
    outbound = await repository.save_outbound(
        OutboundReply(
            platform="qq",
            account_id="3424497994",
            conversation_type=ConversationType.PRIVATE,
            conversation_id="807913552",
            text="在的",
            reply_to_message_id="in-1",
            turn_id=turn.id,
        ),
        platform_message_id="9001",
        agent_name="鲸鱼娘",
        sent_at=sent_at,
    )

    assert outbound.message_id == "9001"
    assert outbound.origin == MessageOrigin.OUTBOUND
    assert outbound.is_self is True
    assert outbound.turn_id == turn.id

    messages = await repository.list_for_conversation(
        platform="qq",
        account_id="3424497994",
        conversation_type=ConversationType.PRIVATE,
        external_id="807913552",
    )
    assert [message.message_id for message in messages] == ["in-1", "9001"]
    assert messages[1].id == outbound.id

    turn_row = await _turn_row(repository.path, turn.id)
    assert turn_row["status"] == TurnStatus.SENT
    assert turn_row["outbound_message_id"] == outbound.id
    assert turn_row["completed_at"] == sent_at.isoformat()


async def test_failed_send_does_not_write_outbound_message(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    inbound = await repository.save_inbound(make_message(message_id="in-1"))
    assert inbound is not None
    turn = await repository.create_turn(
        inbound,
        trigger_type=TurnTrigger.GROUP_AT,
        persona_version=1,
    )
    await repository.mark_turn_generated(turn.id)
    await repository.mark_turn_failed(turn.id)

    messages = await repository.list_recent(limit=10)
    assert [message.message_id for message in messages] == ["in-1"]
    turn_row = await _turn_row(repository.path, turn.id)
    assert turn_row["status"] == TurnStatus.FAILED
    assert turn_row["outbound_message_id"] is None
    assert turn_row["completed_at"] is not None


async def test_outbound_without_platform_id_uses_local_id(tmp_path: Path) -> None:
    repository = SQLiteMessageRepository(tmp_path / "messages.sqlite3")
    inbound = await repository.save_inbound(make_message(message_id="in-1"))
    assert inbound is not None
    turn = await repository.create_turn(
        inbound,
        trigger_type=TurnTrigger.PRIVATE,
        persona_version=1,
    )
    outbound = await repository.save_outbound(
        OutboundReply(
            platform="qq",
            account_id="3424497994",
            conversation_type=ConversationType.GROUP,
            conversation_id="807913552",
            text="本地编号回复",
            turn_id=turn.id,
        ),
        platform_message_id=None,
        agent_name="鲸鱼娘",
    )

    assert outbound.message_id.startswith("local:")


async def test_private_context_is_rebuilt_after_repository_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "messages.sqlite3"
    first_repository = SQLiteMessageRepository(database_path)
    first = make_message(
        message_id="private-1",
        text="第一句",
        conversation_type=ConversationType.PRIVATE,
        conversation_id="3099225100",
        sender_id="3099225100",
    )
    stored_first = await first_repository.save_inbound(first)
    assert stored_first is not None
    turn = await first_repository.create_turn(
        stored_first,
        trigger_type=TurnTrigger.PRIVATE,
        persona_version=1,
    )
    await first_repository.mark_turn_generated(turn.id)
    await first_repository.save_outbound(
        OutboundReply(
            platform="qq",
            account_id="3424497994",
            conversation_type=ConversationType.PRIVATE,
            conversation_id="3099225100",
            text="第一次回复",
            reply_to_message_id="private-1",
            turn_id=turn.id,
        ),
        platform_message_id="private-bot-1",
        agent_name="鲸鱼娘",
    )

    second_repository = SQLiteMessageRepository(database_path)
    second = make_message(
        message_id="private-2",
        text="第二句",
        conversation_type=ConversationType.PRIVATE,
        conversation_id="3099225100",
        sender_id="3099225100",
    )
    assert await second_repository.save_inbound(second) is not None

    context_store = SQLiteConversationContextStore(second_repository)
    history = await context_store.load(
        ConversationKey.from_message(second),
        max_messages=10,
        max_chars=1000,
    )
    assert [(message.role, message.content) for message in history] == [
        ("user", "第一句"),
        ("assistant", "第一次回复"),
        ("user", "第二句"),
    ]


async def test_group_context_is_rebuilt_after_repository_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "messages.sqlite3"
    first_repository = SQLiteMessageRepository(database_path)
    ordinary = make_message(message_id="group-1", text="普通聊天")
    assert await first_repository.save_inbound(ordinary) is not None
    trigger = make_message(message_id="group-2", text="鲸鱼娘在吗", is_to_me=True)
    stored_trigger = await first_repository.save_inbound(trigger)
    assert stored_trigger is not None
    turn = await first_repository.create_turn(
        stored_trigger,
        trigger_type=TurnTrigger.GROUP_AT,
        persona_version=1,
    )
    await first_repository.mark_turn_generated(turn.id)
    await first_repository.save_outbound(
        OutboundReply(
            platform="qq",
            account_id="3424497994",
            conversation_type=ConversationType.GROUP,
            conversation_id="807913552",
            text="在呢",
            reply_to_message_id="group-2",
            turn_id=turn.id,
        ),
        platform_message_id="group-bot-1",
        agent_name="鲸鱼娘",
    )

    second_repository = SQLiteMessageRepository(database_path)
    next_trigger = make_message(
        message_id="group-3",
        text="刚才说到哪了",
        is_to_me=True,
    )
    assert await second_repository.save_inbound(next_trigger) is not None

    context_store = SQLiteConversationContextStore(second_repository)
    history = await context_store.load(
        ConversationKey.from_message(next_trigger),
        max_messages=10,
        max_chars=1000,
    )
    assert [(message.role, message.content) for message in history] == [
        ("user", "测试用户: 普通聊天"),
        ("user", "测试用户: 鲸鱼娘在吗"),
        ("assistant", "在呢"),
        ("user", "测试用户: 刚才说到哪了"),
    ]
