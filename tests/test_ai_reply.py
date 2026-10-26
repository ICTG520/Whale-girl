from datetime import date, datetime, timezone

from whale_girl.application.ai_guard import AIRequestGuard
from whale_girl.application.reply_generators import (
    AIReplyConfig,
    AIReplyGenerator,
    FixedReplyGenerator,
)
from whale_girl.domain.message import (
    ConversationType,
    InboundMessage,
    MessagePart,
    render_message_for_context,
)
from whale_girl.domain.persona import PersonaVersion
from whale_girl.infrastructure.persistence.memory_context import (
    InMemoryConversationContext,
)
from whale_girl.ports.context import ContextMessage, ConversationKey
from whale_girl.ports.llm import LLMResult, LLMTimeoutError, LLMRequest
from whale_girl.ports.limiter import (
    AIRequestContext,
    AIRequestLimiter,
    AIUsageSnapshot,
    LimitDecision,
)


PERSONA = PersonaVersion(
    version=1,
    name="鲸鱼娘",
    system_prompt="测试用人设提示词",
    active=True,
)


def make_message(
    text: str = "你好",
    *,
    message_id: str = "m1",
    conversation_id: str = "42",
    conversation_type: ConversationType = ConversationType.PRIVATE,
    sender_id: str = "42",
    sender_name: str = "测试用户",
    parts: tuple[MessagePart, ...] | None = None,
    raw_event: dict[str, str] | None = None,
) -> InboundMessage:
    return InboundMessage(
        platform="qq",
        account_id="999",
        conversation_type=conversation_type,
        conversation_id=conversation_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        parts=parts or (MessagePart(type="text", data={"text": text}),),
        raw_event=raw_event or {},
    )


class FakeLLM:
    def __init__(
        self,
        results: list[LLMResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._results = list(results or [])
        self._error = error
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._results.pop(0)


def make_generator(
    llm: FakeLLM,
    *,
    context_store: InMemoryConversationContext | None = None,
    config: AIReplyConfig | None = None,
    limiter: AIRequestLimiter | None = None,
) -> tuple[AIReplyGenerator, InMemoryConversationContext]:
    store = context_store or InMemoryConversationContext(max_messages=12)
    generator = AIReplyGenerator(
        persona=PERSONA,
        llm=llm,
        context_store=store,
        config=config
        or AIReplyConfig(
            cooldown_seconds=0,
            max_calls_per_minute=10,
            max_calls_per_day=100,
        ),
        fixed_generator=FixedReplyGenerator("鲸鱼娘"),
        limiter=limiter,
    )
    return generator, store


async def seed_message(
    store: InMemoryConversationContext,
    message: InboundMessage,
    *,
    role: str = "user",
    text: str | None = None,
) -> None:
    content = text
    if content is None:
        content = render_message_for_context(
            conversation_type=message.conversation_type,
            sender_name=message.sender_name,
            parts=message.parts,
            is_self=message.is_self,
        )
    await store.append(
        ConversationKey.from_message(message),
        ContextMessage(role=role, content=content),
    )


async def test_ai_success_updates_context_and_usage() -> None:
    llm = FakeLLM(
        [
            LLMResult(
                text="  你好呀  ",
                model="deepseek-chat",
                input_tokens=12,
                output_tokens=4,
                latency_ms=88.0,
            )
        ]
    )
    generator, store = make_generator(llm)
    message = make_message("今天有点累")
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply == "你好呀"
    assert llm.requests[0].system_prompt == PERSONA.system_prompt
    assert [message.content for message in llm.requests[0].messages] == ["今天有点累"]
    history = await store.load(
        key=ConversationKey.from_message(message),
        max_messages=10,
        max_chars=100,
    )
    assert [(item.role, item.content) for item in history] == [
        ("user", "今天有点累")
    ]
    assert generator.limiter.snapshot.calls_today == 1
    assert generator.limiter.snapshot.input_tokens_today == 12
    assert generator.limiter.snapshot.output_tokens_today == 4


async def test_ai_second_turn_receives_prior_context_but_not_raw_event() -> None:
    llm = FakeLLM(
        [
            LLMResult(text="第一次回复", model="deepseek-chat"),
            LLMResult(text="第二次回复", model="deepseek-chat"),
        ]
    )
    generator, store = make_generator(llm)
    first = make_message("第一句", message_id="m1")
    second = make_message(
        "第二句",
        message_id="m2",
        raw_event={"private_secret": "raw-event-secret"},
    )

    await seed_message(store, first)
    await seed_message(store, first, role="assistant", text="第一次回复")
    await seed_message(store, second)

    await generator.generate(second)

    second_request = llm.requests[0]
    assert [(item.role, item.content) for item in second_request.messages] == [
        ("user", "第一句"),
        ("assistant", "第一次回复"),
        ("user", "第二句"),
    ]
    assert "raw-event-secret" not in str(second_request)


async def test_ai_empty_reply_falls_back_to_fixed() -> None:
    llm = FakeLLM([LLMResult(text="   ", model="deepseek-chat")])
    generator, store = make_generator(llm)
    message = make_message()
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply is not None
    assert "骨架模式" in reply


async def test_ai_timeout_falls_back_to_fixed() -> None:
    llm = FakeLLM(error=LLMTimeoutError("timeout"))
    generator, store = make_generator(llm)
    message = make_message()
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply is not None
    assert "骨架模式" in reply


async def test_ai_failure_can_stay_silent() -> None:
    llm = FakeLLM(error=LLMTimeoutError("timeout"))
    generator, store = make_generator(
        llm,
        config=AIReplyConfig(
            fallback_to_fixed=False,
            cooldown_seconds=0,
            max_calls_per_minute=10,
            max_calls_per_day=100,
        ),
    )
    message = make_message()
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply is None


async def test_ai_truncates_input_and_output() -> None:
    llm = FakeLLM([LLMResult(text="123456", model="deepseek-chat")])
    generator, store = make_generator(
        llm,
        config=AIReplyConfig(
            cooldown_seconds=0,
            max_calls_per_minute=10,
            max_calls_per_day=100,
            max_input_chars=5,
            max_reply_chars=4,
        ),
    )
    message = make_message("abcdefghij")
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply == "1234"
    assert llm.requests[0].messages[0].content == "abcde"


async def test_ai_cooldown_skips_second_call_in_same_conversation() -> None:
    now = [100.0]
    guard = AIRequestGuard(
        cooldown_seconds=10,
        max_calls_per_minute=10,
        max_calls_per_day=100,
        monotonic=lambda: now[0],
    )
    llm = FakeLLM(
        [
            LLMResult(text="第一次", model="deepseek-chat"),
            LLMResult(text="第二次", model="deepseek-chat"),
        ]
    )
    generator, store = make_generator(llm, limiter=guard)
    first_message = make_message("一", message_id="m1")
    second_message = make_message("二", message_id="m2")
    await seed_message(store, first_message)
    await seed_message(store, second_message)

    first = await generator.generate(first_message)
    now[0] = 101.0
    second = await generator.generate(second_message)

    assert first == "第一次"
    assert second is None
    assert len(llm.requests) == 1


async def test_ai_per_minute_limit_applies_across_conversations() -> None:
    guard = AIRequestGuard(
        cooldown_seconds=0,
        max_calls_per_minute=1,
        max_calls_per_day=100,
        monotonic=lambda: 100.0,
    )
    llm = FakeLLM(
        [
            LLMResult(text="第一次", model="deepseek-chat"),
            LLMResult(text="第二次", model="deepseek-chat"),
        ]
    )
    generator, store = make_generator(llm, limiter=guard)
    first_message = make_message("一", conversation_id="42")
    second_message = make_message("二", conversation_id="43")
    await seed_message(store, first_message)
    await seed_message(store, second_message)

    first = await generator.generate(first_message)
    second = await generator.generate(second_message)

    assert first == "第一次"
    assert second is None
    assert len(llm.requests) == 1


async def test_group_context_labels_speakers_and_uses_group_prompt() -> None:
    llm = FakeLLM([LLMResult(text="在呢", model="deepseek-chat")])
    generator, store = make_generator(
        llm,
        config=AIReplyConfig(
            cooldown_seconds=0,
            max_calls_per_minute=10,
            max_calls_per_day=100,
            system_prompt_suffix="\n\n群聊规则",
        ),
    )
    observed = make_message(
        "今天有点累",
        message_id="g1",
        conversation_type=ConversationType.GROUP,
        conversation_id="100",
        sender_id="1",
        sender_name="小明",
    )
    trigger = make_message(
        "鲸鱼娘在吗",
        message_id="g2",
        conversation_type=ConversationType.GROUP,
        conversation_id="100",
        sender_id="2",
        sender_name="小红",
    )

    await seed_message(store, observed)
    await seed_message(store, trigger)
    reply = await generator.generate(trigger)

    assert reply == "在呢"
    assert llm.requests[0].system_prompt == PERSONA.system_prompt + "\n\n群聊规则"
    assert [item.content for item in llm.requests[0].messages] == [
        "小明: 今天有点累",
        "小红: 鲸鱼娘在吗",
    ]
    history = await store.load(
        ConversationKey.from_message(trigger), max_messages=10, max_chars=1000
    )
    assert [(item.role, item.content) for item in history] == [
        ("user", "小明: 今天有点累"),
        ("user", "小红: 鲸鱼娘在吗"),
    ]


async def test_group_observe_renders_non_text_parts_without_calling_llm() -> None:
    llm = FakeLLM()
    generator, store = make_generator(llm)
    message = make_message(
        "",
        message_id="g1",
        conversation_type=ConversationType.GROUP,
        conversation_id="100",
        parts=(
            MessagePart(type="at", data={"qq": "999"}),
            MessagePart(type="image", data={"file": "x.jpg"}),
            MessagePart(type="face", data={"id": "13"}),
        ),
    )

    await seed_message(store, message)

    history = await store.load(
        ConversationKey.from_message(message), max_messages=10, max_chars=1000
    )
    assert [(item.role, item.content) for item in history] == [
        ("user", "测试用户: [提及][图片][表情]")
    ]
    assert llm.requests == []


async def test_custom_limiter_can_block_generation_without_changing_generator() -> None:
    class DenyLimiter:
        def begin(self, request: AIRequestContext) -> LimitDecision:
            return LimitDecision(False, "custom_policy")

        def record_usage(
            self,
            request: AIRequestContext,
            *,
            input_tokens: int,
            output_tokens: int,
        ) -> None:
            raise AssertionError("usage should not be recorded for denied requests")

        @property
        def snapshot(self) -> AIUsageSnapshot:
            return AIUsageSnapshot(date.today(), 0, 0, 0)

    llm = FakeLLM([LLMResult(text="不应调用", model="deepseek-chat")])
    generator, store = make_generator(llm, limiter=DenyLimiter())
    message = make_message()
    await seed_message(store, message)

    reply = await generator.generate(message)

    assert reply is None
    assert llm.requests == []
