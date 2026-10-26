import pytest

from whale_girl.bootstrap.config import Settings


def test_settings_parse_json_lists() -> None:
    settings = Settings.from_env(
        {
            "QQ_GROUP_WHITELIST": '["100", "200"]',
            "QQ_FRIEND_WHITELIST": '["300"]',
            "WAKE_WORDS": '["鲸鱼娘", "小鲸鱼"]',
            "OBSERVE_ALL_GROUP_MESSAGES": "true",
            "REPLY_ENABLED": "false",
        }
    )

    assert settings.qq_group_whitelist == frozenset({"100", "200"})
    assert settings.qq_friend_whitelist == frozenset({"300"})
    assert settings.wake_words == ("鲸鱼娘", "小鲸鱼")
    assert settings.observe_all_group_messages is True
    assert settings.reply_enabled is False


def test_settings_parse_csv_lists() -> None:
    settings = Settings.from_env({"QQ_GROUP_WHITELIST": "100, 200"})

    assert settings.qq_group_whitelist == frozenset({"100", "200"})


def test_settings_reject_invalid_port() -> None:
    with pytest.raises(ValueError, match="端口"):
        Settings.from_env({"PORT": "not-a-port"})


def test_settings_use_defaults_for_empty_values() -> None:
    settings = Settings.from_env({})

    assert settings.port == 8090
    assert settings.qq_group_whitelist == frozenset()
    assert settings.qq_friend_whitelist == frozenset()
    assert settings.wake_words == ("鲸鱼娘",)
    assert settings.observe_all_group_messages is True
    assert settings.reply_mode == "ai"
    assert settings.ai_fallback_to_fixed is True
    assert settings.ai_max_context_messages == 12
    assert settings.ai_group_enabled is True
    assert settings.ai_group_fallback_to_fixed is False
    assert settings.ai_group_max_context_messages == 20
    assert settings.ai_group_cooldown_seconds == 30.0
    assert settings.ai_group_max_calls_per_minute == 6
    assert settings.ai_group_max_calls_per_day == 100


def test_settings_parse_ai_config_without_exposing_key() -> None:
    settings = Settings.from_env(
        {
            "REPLY_MODE": "AI",
            "DEEPSEEK_API_KEY": "sk-test-secret-value",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "AI_FALLBACK_TO_FIXED": "false",
            "AI_MAX_CONTEXT_MESSAGES": "8",
            "AI_MAX_CONTEXT_CHARS": "4000",
            "AI_MAX_INPUT_CHARS": "1200",
            "AI_MAX_REPLY_CHARS": "400",
            "AI_MAX_OUTPUT_TOKENS": "256",
            "AI_TEMPERATURE": "0.6",
            "AI_TIMEOUT_SECONDS": "15",
            "AI_MAX_RETRIES": "0",
            "AI_COOLDOWN_SECONDS": "1.5",
            "AI_MAX_CALLS_PER_MINUTE": "5",
            "AI_MAX_CALLS_PER_DAY": "50",
            "AI_GROUP_ENABLED": "false",
            "AI_GROUP_FALLBACK_TO_FIXED": "true",
            "AI_GROUP_MAX_CONTEXT_MESSAGES": "16",
            "AI_GROUP_COOLDOWN_SECONDS": "45",
            "AI_GROUP_MAX_CALLS_PER_MINUTE": "3",
            "AI_GROUP_MAX_CALLS_PER_DAY": "30",
        }
    )

    assert settings.reply_mode == "ai"
    assert settings.has_deepseek_key is True
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.ai_fallback_to_fixed is False
    assert settings.ai_max_context_messages == 8
    assert settings.ai_max_context_chars == 4000
    assert settings.ai_max_input_chars == 1200
    assert settings.ai_max_reply_chars == 400
    assert settings.ai_max_output_tokens == 256
    assert settings.ai_temperature == 0.6
    assert settings.ai_timeout_seconds == 15.0
    assert settings.ai_max_retries == 0
    assert settings.ai_cooldown_seconds == 1.5
    assert settings.ai_max_calls_per_minute == 5
    assert settings.ai_max_calls_per_day == 50
    assert settings.ai_group_enabled is False
    assert settings.ai_group_fallback_to_fixed is True
    assert settings.ai_group_max_context_messages == 16
    assert settings.ai_group_cooldown_seconds == 45.0
    assert settings.ai_group_max_calls_per_minute == 3
    assert settings.ai_group_max_calls_per_day == 30
    assert "sk-test-secret-value" not in repr(settings)


def test_settings_do_not_expose_onebot_token_in_repr() -> None:
    settings = Settings.from_env({"ONEBOT_V11_ACCESS_TOKEN": "onebot-secret"})

    assert "onebot-secret" not in repr(settings)


@pytest.mark.parametrize("value", ["invalid", "fixed-ish"])
def test_settings_reject_invalid_reply_mode(value: str) -> None:
    with pytest.raises(ValueError, match="REPLY_MODE"):
        Settings.from_env({"REPLY_MODE": value})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AI_MAX_CONTEXT_MESSAGES", "0"),
        ("AI_MAX_OUTPUT_TOKENS", "9000"),
        ("AI_TEMPERATURE", "2.5"),
        ("AI_TIMEOUT_SECONDS", "0"),
        ("AI_GROUP_MAX_CONTEXT_MESSAGES", "0"),
        ("AI_GROUP_COOLDOWN_SECONDS", "3601"),
    ],
)
def test_settings_reject_out_of_range_ai_values(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        Settings.from_env({name: value})


def test_settings_accept_relaxed_context_and_unlimited_rate_limits() -> None:
    settings = Settings.from_env(
        {
            "AI_MAX_INPUT_CHARS": "4000",
            "AI_MAX_CONTEXT_CHARS": "10000",
            "AI_MAX_CONTEXT_MESSAGES": "120",
            "AI_GROUP_MAX_CONTEXT_MESSAGES": "200",
            "AI_COOLDOWN_SECONDS": "0",
            "AI_MAX_CALLS_PER_MINUTE": "0",
            "AI_MAX_CALLS_PER_DAY": "0",
            "AI_GROUP_COOLDOWN_SECONDS": "0",
            "AI_GROUP_MAX_CALLS_PER_MINUTE": "0",
            "AI_GROUP_MAX_CALLS_PER_DAY": "0",
        }
    )

    assert settings.ai_max_input_chars == 4000
    assert settings.ai_max_context_chars == 10000
    assert settings.ai_max_context_messages == 120
    assert settings.ai_group_max_context_messages == 200
    assert settings.ai_cooldown_seconds == 0.0
    assert settings.ai_max_calls_per_minute == 0
    assert settings.ai_max_calls_per_day == 0
    assert settings.ai_group_cooldown_seconds == 0.0
    assert settings.ai_group_max_calls_per_minute == 0
    assert settings.ai_group_max_calls_per_day == 0