from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from datetime import date

from whale_girl.ports.limiter import (
    AIRequestContext,
    AIUsageSnapshot,
    LimitDecision,
)


class AIRequestGuard:
    """Apply per-conversation cooldown and global usage limits."""

    def __init__(
        self,
        *,
        cooldown_seconds: float,
        max_calls_per_minute: int,
        max_calls_per_day: int,
        monotonic: Callable[[], float] | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._max_calls_per_minute = max_calls_per_minute
        self._max_calls_per_day = max_calls_per_day
        self._monotonic = monotonic or time.monotonic
        self._today = today or date.today
        self._call_times: deque[float] = deque()
        self._last_call_by_conversation: dict[str, float] = {}
        self._usage_day = self._today()
        self._calls_today = 0
        self._input_tokens_today = 0
        self._output_tokens_today = 0

    def begin(self, request: AIRequestContext) -> LimitDecision:
        self._roll_day_if_needed()
        now = self._monotonic()
        self._evict_old_calls(now)
        conversation_key = request.conversation_key

        if self._cooldown_seconds > 0:
            last_call = self._last_call_by_conversation.get(conversation_key)
            if last_call is not None and now - last_call < self._cooldown_seconds:
                return LimitDecision(False, "conversation_cooldown")

        if (
            self._max_calls_per_minute > 0
            and len(self._call_times) >= self._max_calls_per_minute
        ):
            return LimitDecision(False, "minute_limit")

        if self._max_calls_per_day > 0 and self._calls_today >= self._max_calls_per_day:
            return LimitDecision(False, "daily_limit")

        self._call_times.append(now)
        self._last_call_by_conversation[conversation_key] = now
        self._calls_today += 1
        return LimitDecision(True)

    def record_usage(
        self,
        request: AIRequestContext,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self._roll_day_if_needed()
        self._input_tokens_today += max(0, input_tokens)
        self._output_tokens_today += max(0, output_tokens)

    @property
    def snapshot(self) -> AIUsageSnapshot:
        self._roll_day_if_needed()
        return AIUsageSnapshot(
            day=self._usage_day,
            calls_today=self._calls_today,
            input_tokens_today=self._input_tokens_today,
            output_tokens_today=self._output_tokens_today,
        )

    def _evict_old_calls(self, now: float) -> None:
        cutoff = now - 60.0
        while self._call_times and self._call_times[0] <= cutoff:
            self._call_times.popleft()

    def _roll_day_if_needed(self) -> None:
        current_day = self._today()
        if current_day == self._usage_day:
            return
        self._usage_day = current_day
        self._calls_today = 0
        self._input_tokens_today = 0
        self._output_tokens_today = 0
