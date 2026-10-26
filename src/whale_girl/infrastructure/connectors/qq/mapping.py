from datetime import datetime, timezone

from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)

from whale_girl.domain.message import ConversationType, InboundMessage, MessagePart


def event_to_inbound(event: MessageEvent) -> InboundMessage:
    """Convert a OneBot v11 message event into the domain message shape."""
    if isinstance(event, GroupMessageEvent):
        conversation_type = ConversationType.GROUP
        conversation_id = str(event.group_id)
    elif isinstance(event, PrivateMessageEvent):
        conversation_type = ConversationType.PRIVATE
        conversation_id = str(event.user_id)
    else:
        raise TypeError(f"不支持的 OneBot 消息事件: {type(event).__name__}")

    sender_name = (
        getattr(event.sender, "card", None)
        or getattr(event.sender, "nickname", None)
        or str(event.user_id)
    )

    return InboundMessage(
        platform="qq",
        account_id=str(event.self_id),
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        message_id=str(event.message_id),
        sender_id=str(event.user_id),
        sender_name=sender_name,
        timestamp=datetime.fromtimestamp(event.time, tz=timezone.utc),
        parts=tuple(
            MessagePart(type=segment.type, data=dict(segment.data))
            for segment in event.message
        ),
        is_to_me=event.is_tome(),
        is_self=event.user_id == event.self_id,
        reply_to_message_id=(
            str(event.reply.message_id) if event.reply is not None else None
        ),
        raw_event=event.model_dump(mode="json"),
    )
