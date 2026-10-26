from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, PrivateMessageEvent
from nonebot.adapters.onebot.v11.event import Sender

from whale_girl.domain.message import ConversationType
from whale_girl.infrastructure.connectors.qq.mapping import event_to_inbound


def make_group_event(*, to_me: bool = False) -> GroupMessageEvent:
    return GroupMessageEvent(
        time=1_767_225_600,
        self_id=999,
        post_type="message",
        sub_type="normal",
        user_id=42,
        message_type="group",
        message_id=1,
        message=Message("你好"),
        original_message=Message("你好"),
        raw_message="你好",
        font=0,
        sender=Sender(user_id=42, nickname="测试用户"),
        to_me=to_me,
        group_id=100,
    )


def test_group_event_mapping() -> None:
    message = event_to_inbound(make_group_event(to_me=True))

    assert message.platform == "qq"
    assert message.account_id == "999"
    assert message.conversation_type == ConversationType.GROUP
    assert message.conversation_id == "100"
    assert message.sender_name == "测试用户"
    assert message.text == "你好"
    assert message.is_to_me is True
    assert message.is_self is False
    assert message.raw_event["group_id"] == 100


def test_private_event_mapping() -> None:
    event = PrivateMessageEvent(
        time=1_767_225_600,
        self_id=999,
        post_type="message",
        sub_type="friend",
        user_id=42,
        message_type="private",
        message_id=2,
        message=Message("私聊"),
        original_message=Message("私聊"),
        raw_message="私聊",
        font=0,
        sender=Sender(user_id=42, nickname="测试用户"),
        to_me=False,
    )

    message = event_to_inbound(event)

    assert message.conversation_type == ConversationType.PRIVATE
    assert message.conversation_id == "42"
    assert message.text == "私聊"
