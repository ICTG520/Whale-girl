from datetime import date

from whale_girl.application.ai_guard import AIRequestGuard
from whale_girl.domain.message import ConversationType
from whale_girl.ports.limiter import AIRequestContext


def request(conversation_id: str) -> AIRequestContext:
    return AIRequestContext(
        platform="qq",
        account_id="999",
        conversation_type=ConversationType.PRIVATE,
        conversation_id=conversation_id,
        sender_id=conversation_id,
    )


def test_daily_limit_and_usage_reset_on_new_day() -> None:
    current_day = [date(2026, 10, 24)]
    guard = AIRequestGuard(
        cooldown_seconds=0,
        max_calls_per_minute=10,
        max_calls_per_day=1,
        monotonic=lambda: 100.0,
        today=lambda: current_day[0],
    )

    first = guard.begin(request("42"))
    guard.record_usage(request("42"), input_tokens=10, output_tokens=5)
    second = guard.begin(request("43"))

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason == "daily_limit"
    assert guard.snapshot.calls_today == 1
    assert guard.snapshot.input_tokens_today == 10

    current_day[0] = date(2026, 10, 25)
    third = guard.begin(request("42"))

    assert third.allowed is True
    assert guard.snapshot.calls_today == 1
    assert guard.snapshot.input_tokens_today == 0
    assert guard.snapshot.output_tokens_today == 0

def test_zero_minute_and_daily_limits_mean_unlimited() -> None:
    guard = AIRequestGuard(
        cooldown_seconds=0,
        max_calls_per_minute=0,
        max_calls_per_day=0,
        monotonic=lambda: 100.0,
        today=lambda: date(2026, 10, 24),
    )

    for index in range(50):
        decision = guard.begin(request(str(index)))
        assert decision.allowed is True

    assert guard.snapshot.calls_today == 50