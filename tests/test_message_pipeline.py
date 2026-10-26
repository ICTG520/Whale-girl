from datetime import datetime, timezone

from whale_girl.application.handle_message import HandleInboundMessage
from whale_girl.application.reply_policy import ReplyPolicy
from whale_girl.bootstrap.config import Settings
from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    MessageOrigin,
    MessagePart,
)
from whale_girl.domain.turn import TurnStatus
from whale_girl.infrastructure.persistence.memory import InMemoryMessageRepository


def make_message(
    *,
    conversation_type: ConversationType = ConversationType.GROUP,
    conversation_id: str = "100",
    text: str = "普通群消息",
    is_to_me: bool = False,
    is_self: bool = False,
    message_id: str = "m1",
) -> InboundMessage:
    return InboundMessage(
        platform="qq",
        account_id="999",
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        message_id=message_id,
        sender_id="42",
        sender_name="测试用户",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        parts=(MessagePart(type="text", data={"text": text}),),
        is_to_me=is_to_me,
        is_self=is_self,
    )


def make_handler(
    settings: Settings,
    repository: InMemoryMessageRepository,
    *,
    ai_reply_generator=None,
    group_ai_reply_generator=None,
) -> HandleInboundMessage:
    return HandleInboundMessage(
        settings=settings,
        repository=repository,
        reply_policy=ReplyPolicy(settings),
        ai_reply_generator=ai_reply_generator,
        group_ai_reply_generator=group_ai_reply_generator,
    )


class CountingReplyGenerator:
    def __init__(self, reply: str = "AI 回复") -> None:
        self.reply = reply
        self.calls: list[InboundMessage] = []

    async def generate(self, message: InboundMessage) -> str:
        self.calls.append(message)
        return self.reply


async def test_group_message_is_observed_without_reply() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(make_message())

    assert reply is None
    assert len(repository.messages) == 1


async def test_at_message_triggers_fixed_reply() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is not None
    assert reply.conversation_id == "100"
    assert "骨架模式" in reply.text


async def test_wake_word_triggers_fixed_reply() -> None:
    settings = Settings(
        qq_group_whitelist=frozenset({"100"}),
        wake_words=("鲸鱼娘",),
    )
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(make_message(text="鲸鱼娘在吗"))

    assert reply is not None
    assert reply.reply_to_message_id == "m1"


async def test_group_outside_whitelist_is_ignored() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(
        make_message(conversation_id="999", text="鲸鱼娘在吗", is_to_me=True)
    )

    assert reply is None
    assert repository.messages == ()


async def test_private_message_triggers_reply() -> None:
    settings = Settings(qq_friend_whitelist=frozenset({"42"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(
        make_message(conversation_type=ConversationType.PRIVATE, conversation_id="42")
    )

    assert reply is not None
    assert reply.conversation_type == ConversationType.PRIVATE


async def test_private_message_outside_whitelist_is_observed_without_reply() -> None:
    settings = Settings(qq_friend_whitelist=frozenset({"999"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(
        make_message(conversation_type=ConversationType.PRIVATE, conversation_id="42")
    )

    assert reply is None
    assert len(repository.messages) == 1


async def test_self_message_is_ignored() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(make_message(is_self=True))

    assert reply is None
    assert repository.messages == ()
    assert repository.turns == ()


async def test_duplicate_message_is_ignored() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)
    message = make_message(is_to_me=True)

    first_reply = await handler.execute(message)
    second_reply = await handler.execute(message)

    assert first_reply is not None
    assert second_reply is None
    assert len(repository.messages) == 1


async def test_reply_can_be_disabled_while_messages_are_still_observed() -> None:
    settings = Settings(
        qq_group_whitelist=frozenset({"100"}),
        reply_enabled=False,
    )
    repository = InMemoryMessageRepository()
    handler = make_handler(settings, repository)

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is None
    assert len(repository.messages) == 1


async def test_private_whitelisted_message_uses_ai_generator() -> None:
    settings = Settings(qq_friend_whitelist=frozenset({"42"}))
    repository = InMemoryMessageRepository()
    ai_generator = CountingReplyGenerator()
    handler = make_handler(settings, repository, ai_reply_generator=ai_generator)

    reply = await handler.execute(
        make_message(conversation_type=ConversationType.PRIVATE, conversation_id="42")
    )

    assert reply is not None
    assert reply.text == "AI 回复"
    assert len(ai_generator.calls) == 1


async def test_group_message_without_group_ai_uses_fixed_reply() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    ai_generator = CountingReplyGenerator()
    handler = make_handler(settings, repository, ai_reply_generator=ai_generator)

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is not None
    assert "骨架模式" in reply.text
    assert ai_generator.calls == []


async def test_group_message_observes_context_without_calling_ai() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator()
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(text="普通聊天"))

    assert reply is None
    assert [item.text for item in repository.messages] == ["普通聊天"]
    assert group_generator.calls == []
    assert repository.turns == ()


async def test_at_message_uses_group_ai_generator() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    private_generator = CountingReplyGenerator("私聊 AI")
    group_generator = CountingReplyGenerator("群聊 AI")
    handler = make_handler(
        settings,
        repository,
        ai_reply_generator=private_generator,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is not None
    assert reply.text == "群聊 AI"
    assert len(group_generator.calls) == 1
    assert private_generator.calls == []
    assert len(repository.turns) == 1
    assert repository.turns[0].status == TurnStatus.GENERATED


async def test_successful_send_persists_outbound_message_and_marks_turn_sent() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator("群聊 AI")
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is not None
    await handler.record_sent(reply, platform_message_id="bot-1")

    assert [message.message_id for message in repository.messages] == ["m1", "bot-1"]
    assert repository.messages[1].origin == MessageOrigin.OUTBOUND
    assert repository.messages[1].is_self is True
    assert repository.turns[0].status == TurnStatus.SENT
    assert repository.turns[0].outbound_message_id == repository.messages[1].id


async def test_failed_send_marks_turn_failed_without_outbound_message() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator("群聊 AI")
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is not None
    await handler.record_failed(reply)

    assert [message.message_id for message in repository.messages] == ["m1"]
    assert repository.turns[0].status == TurnStatus.FAILED
    assert repository.turns[0].outbound_message_id is None


async def test_wake_word_uses_group_ai_generator() -> None:
    settings = Settings(
        qq_group_whitelist=frozenset({"100"}),
        wake_words=("鲸鱼娘",),
    )
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator()
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(text="鲸鱼娘在吗"))

    assert reply is not None
    assert len(group_generator.calls) == 1


async def test_duplicate_group_message_is_observed_once() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator()
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )
    message = make_message(text="只记录一次")

    await handler.execute(message)
    await handler.execute(message)

    assert len(repository.messages) == 1
    assert group_generator.calls == []


async def test_group_outside_whitelist_is_not_observed_in_context() -> None:
    settings = Settings(qq_group_whitelist=frozenset({"100"}))
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator()
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(conversation_id="999", is_to_me=True))

    assert reply is None
    assert group_generator.calls == []
    assert repository.messages == ()


async def test_reply_disabled_still_observes_group_context() -> None:
    settings = Settings(
        qq_group_whitelist=frozenset({"100"}),
        reply_enabled=False,
    )
    repository = InMemoryMessageRepository()
    group_generator = CountingReplyGenerator()
    handler = make_handler(
        settings,
        repository,
        group_ai_reply_generator=group_generator,
    )

    reply = await handler.execute(make_message(is_to_me=True))

    assert reply is None
    assert len(repository.messages) == 1
    assert group_generator.calls == []


async def test_private_non_whitelisted_message_never_uses_ai_generator() -> None:
    settings = Settings(qq_friend_whitelist=frozenset({"999"}))
    repository = InMemoryMessageRepository()
    ai_generator = CountingReplyGenerator()
    handler = make_handler(settings, repository, ai_reply_generator=ai_generator)

    reply = await handler.execute(
        make_message(conversation_type=ConversationType.PRIVATE, conversation_id="42")
    )

    assert reply is None
    assert ai_generator.calls == []
    assert len(repository.messages) == 1
