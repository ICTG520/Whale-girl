from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from whale_girl.bootstrap.config import Settings  # noqa: E402
from whale_girl.domain.message import ConversationType, StoredMessage  # noqa: E402
from whale_girl.infrastructure.persistence.sqlite import (  # noqa: E402
    SQLiteMessageRepository,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查询鲸鱼娘保存的 QQ 消息")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--group", help="只看指定群号")
    target.add_argument("--friend", help="只看指定好友 QQ 号")
    parser.add_argument("--account", help="只看指定机器人 QQ 号")
    parser.add_argument("--limit", type=int, default=20, help="最多显示多少条，1-500")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument("--db", help="覆盖 DATABASE_PATH")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    database_path = Path(args.db) if args.db else Path(settings.database_path)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path

    conversation_type: ConversationType | None = None
    external_id: str | None = None
    if args.group:
        conversation_type = ConversationType.GROUP
        external_id = str(args.group)
    elif args.friend:
        conversation_type = ConversationType.PRIVATE
        external_id = str(args.friend)

    repository = SQLiteMessageRepository(
        database_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
    )
    await repository.initialize()
    messages = await repository.list_recent(
        platform="qq",
        account_id=args.account,
        conversation_type=conversation_type,
        external_id=external_id,
        limit=max(1, min(args.limit, 500)),
    )

    if args.json:
        print(
            json.dumps(
                [_message_to_dict(message) for message in messages],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0

    if not messages:
        print("没有找到消息。")
        return 0

    for message in messages:
        print(_format_message(message))
    return 0


def _format_message(message: StoredMessage) -> str:
    timestamp = message.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    segment_types = " ".join(
        f"[{part.type}]" for part in message.parts if part.type != "text"
    )
    content = message.text.strip() or "[无文字内容]"
    if segment_types:
        content = f"{content} {segment_types}"
    turn = f" turn={message.turn_id}" if message.turn_id else ""
    speaker = (
        f"{message.sender_name}({message.sender_id})"
        if message.origin.value != "outbound"
        else f"机器人 {message.sender_name}({message.sender_id})"
    )
    return (
        f"{timestamp} "
        f"[{message.conversation_type.value}:{message.conversation_id}] "
        f"[#{message.id} {message.origin.value}{turn}] "
        f"{speaker}: {content}"
    )


def _message_to_dict(message: StoredMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "platform": message.platform,
        "account_id": message.account_id,
        "conversation_type": message.conversation_type.value,
        "conversation_id": message.conversation_id,
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "sender_name": message.sender_name,
        "timestamp": message.timestamp.isoformat(),
        "text": message.text,
        "origin": message.origin.value,
        "turn_id": message.turn_id,
        "conversation_ref_id": message.conversation_ref_id,
        "parts": [
            {"type": part.type, "data": dict(part.data)} for part in message.parts
        ],
        "is_to_me": message.is_to_me,
        "is_self": message.is_self,
        "reply_to_message_id": message.reply_to_message_id,
        "raw_event": dict(message.raw_event),
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(run(parse_args())))
