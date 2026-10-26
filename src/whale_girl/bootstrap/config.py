from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _parse_list(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None or not value.strip():
        return default

    raw = value.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"无法解析列表配置: {raw}") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"列表配置必须是 JSON 数组: {raw}")
        items = parsed
    else:
        items = raw.split(",")

    return tuple(str(item).strip() for item in items if str(item).strip())


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"无法解析布尔配置: {value}")


def _parse_port(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError(f"端口必须是整数: {value}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"端口超出范围: {port}")
    return port


def _parse_int(
    name: str,
    value: str | None,
    default: int,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数: {value}") from exc
    if parsed < minimum or (maximum is not None and parsed > maximum):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise ValueError(f"{name} 超出范围 {bounds}: {parsed}")
    return parsed


def _parse_float(
    name: str,
    value: str | None,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字: {value}") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} 超出范围 {minimum}..{maximum}: {parsed}")
    return parsed


def _parse_reply_mode(value: str | None, default: str) -> str:
    mode = (value or default).strip().lower()
    if mode not in {"fixed", "ai"}:
        raise ValueError(f"REPLY_MODE 只能是 fixed 或 ai: {value}")
    return mode


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8090
    access_token: str = field(default="", repr=False)
    agent_name: str = "鲸鱼娘"
    qq_group_whitelist: frozenset[str] = field(default_factory=frozenset)
    qq_friend_whitelist: frozenset[str] = field(default_factory=frozenset)
    wake_words: tuple[str, ...] = ("鲸鱼娘",)
    observe_all_group_messages: bool = True
    reply_enabled: bool = True

    reply_mode: str = "ai"
    deepseek_api_key: str = field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ai_fallback_to_fixed: bool = True
    ai_max_context_messages: int = 12
    ai_max_context_chars: int = 6000
    ai_max_input_chars: int = 2000
    ai_max_reply_chars: int = 600
    ai_max_output_tokens: int = 300
    ai_temperature: float = 0.8
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 1
    ai_cooldown_seconds: float = 2.0
    ai_max_calls_per_minute: int = 10
    ai_max_calls_per_day: int = 200
    ai_group_enabled: bool = True
    ai_group_fallback_to_fixed: bool = False
    ai_group_max_context_messages: int = 20
    ai_group_cooldown_seconds: float = 30.0
    ai_group_max_calls_per_minute: int = 6
    ai_group_max_calls_per_day: int = 100
    persona_path: str = "config/persona.toml"
    database_path: str = "data/whale_girl.sqlite3"
    sqlite_busy_timeout_ms: int = 5000

    @property
    def ai_enabled(self) -> bool:
        return self.reply_mode == "ai"

    @property
    def has_deepseek_key(self) -> bool:
        return bool(self.deepseek_api_key.strip())

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        if env is None:
            load_dotenv()
            env = os.environ

        group_ids = _parse_list(env.get("QQ_GROUP_WHITELIST"), ())
        friend_ids = _parse_list(env.get("QQ_FRIEND_WHITELIST"), ())
        wake_words = _parse_list(env.get("WAKE_WORDS"), ("鲸鱼娘",))

        return cls(
            host=env.get("HOST", "127.0.0.1"),
            port=_parse_port(env.get("PORT"), 8090),
            access_token=env.get("ONEBOT_V11_ACCESS_TOKEN", "").strip(),
            agent_name=env.get("AGENT_NAME", "鲸鱼娘"),
            qq_group_whitelist=frozenset(group_ids),
            qq_friend_whitelist=frozenset(friend_ids),
            wake_words=wake_words,
            observe_all_group_messages=_parse_bool(
                env.get("OBSERVE_ALL_GROUP_MESSAGES"), True
            ),
            reply_enabled=_parse_bool(env.get("REPLY_ENABLED"), True),
            reply_mode=_parse_reply_mode(env.get("REPLY_MODE"), "ai"),
            deepseek_api_key=env.get("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=env.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-chat").strip(),
            ai_fallback_to_fixed=_parse_bool(
                env.get("AI_FALLBACK_TO_FIXED"), True
            ),
            ai_max_context_messages=_parse_int(
                "AI_MAX_CONTEXT_MESSAGES",
                env.get("AI_MAX_CONTEXT_MESSAGES"),
                12,
                minimum=1,
                maximum=1000,
            ),
            ai_max_context_chars=_parse_int(
                "AI_MAX_CONTEXT_CHARS",
                env.get("AI_MAX_CONTEXT_CHARS"),
                6000,
                minimum=100,
                maximum=100_000,
            ),
            ai_max_input_chars=_parse_int(
                "AI_MAX_INPUT_CHARS",
                env.get("AI_MAX_INPUT_CHARS"),
                2000,
                minimum=100,
                maximum=100_000,
            ),
            ai_max_reply_chars=_parse_int(
                "AI_MAX_REPLY_CHARS",
                env.get("AI_MAX_REPLY_CHARS"),
                600,
                minimum=20,
                maximum=10_000,
            ),
            ai_max_output_tokens=_parse_int(
                "AI_MAX_OUTPUT_TOKENS",
                env.get("AI_MAX_OUTPUT_TOKENS"),
                300,
                minimum=1,
                maximum=8192,
            ),
            ai_temperature=_parse_float(
                "AI_TEMPERATURE",
                env.get("AI_TEMPERATURE"),
                0.8,
                minimum=0.0,
                maximum=2.0,
            ),
            ai_timeout_seconds=_parse_float(
                "AI_TIMEOUT_SECONDS",
                env.get("AI_TIMEOUT_SECONDS"),
                30.0,
                minimum=1.0,
                maximum=300.0,
            ),
            ai_max_retries=_parse_int(
                "AI_MAX_RETRIES",
                env.get("AI_MAX_RETRIES"),
                1,
                minimum=0,
                maximum=5,
            ),
            ai_cooldown_seconds=_parse_float(
                "AI_COOLDOWN_SECONDS",
                env.get("AI_COOLDOWN_SECONDS"),
                2.0,
                minimum=0.0,
                maximum=300.0,
            ),
            ai_max_calls_per_minute=_parse_int(
                "AI_MAX_CALLS_PER_MINUTE",
                env.get("AI_MAX_CALLS_PER_MINUTE"),
                10,
                minimum=0,
                maximum=1000,
            ),
            ai_max_calls_per_day=_parse_int(
                "AI_MAX_CALLS_PER_DAY",
                env.get("AI_MAX_CALLS_PER_DAY"),
                200,
                minimum=0,
                maximum=100_000,
            ),
            ai_group_enabled=_parse_bool(env.get("AI_GROUP_ENABLED"), True),
            ai_group_fallback_to_fixed=_parse_bool(
                env.get("AI_GROUP_FALLBACK_TO_FIXED"), False
            ),
            ai_group_max_context_messages=_parse_int(
                "AI_GROUP_MAX_CONTEXT_MESSAGES",
                env.get("AI_GROUP_MAX_CONTEXT_MESSAGES"),
                20,
                minimum=1,
                maximum=1000,
            ),
            ai_group_cooldown_seconds=_parse_float(
                "AI_GROUP_COOLDOWN_SECONDS",
                env.get("AI_GROUP_COOLDOWN_SECONDS"),
                30.0,
                minimum=0.0,
                maximum=3600.0,
            ),
            ai_group_max_calls_per_minute=_parse_int(
                "AI_GROUP_MAX_CALLS_PER_MINUTE",
                env.get("AI_GROUP_MAX_CALLS_PER_MINUTE"),
                6,
                minimum=0,
                maximum=1000,
            ),
            ai_group_max_calls_per_day=_parse_int(
                "AI_GROUP_MAX_CALLS_PER_DAY",
                env.get("AI_GROUP_MAX_CALLS_PER_DAY"),
                100,
                minimum=0,
                maximum=100_000,
            ),
            persona_path=env.get("PERSONA_PATH", "config/persona.toml").strip(),
            database_path=env.get(
                "DATABASE_PATH", "data/whale_girl.sqlite3"
            ).strip(),
            sqlite_busy_timeout_ms=_parse_int(
                "SQLITE_BUSY_TIMEOUT_MS",
                env.get("SQLITE_BUSY_TIMEOUT_MS"),
                5000,
                minimum=100,
                maximum=60_000,
            ),
        )
