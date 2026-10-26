from pathlib import Path

from whale_girl.bootstrap.config import Settings
from whale_girl.bootstrap.container import build_container


PERSONA_PATH = str(Path(__file__).parents[1] / "config" / "persona.toml")


def test_container_starts_with_ai_mode_and_no_api_key() -> None:
    container = build_container(
        Settings(persona_path=PERSONA_PATH, deepseek_api_key="")
    )

    assert container.settings.reply_mode == "ai"
    assert container.settings.has_deepseek_key is False
    assert container.ai_reply_generator is not None
    assert container.group_ai_reply_generator is not None
    assert container.persona.name == "鲸鱼娘"


def test_container_skips_ai_generator_in_fixed_mode() -> None:
    container = build_container(
        Settings(persona_path=PERSONA_PATH, reply_mode="fixed")
    )

    assert container.ai_reply_generator is None
    assert container.group_ai_reply_generator is None


def test_container_can_disable_group_ai_independently() -> None:
    container = build_container(
        Settings(
            persona_path=PERSONA_PATH,
            ai_group_enabled=False,
        )
    )

    assert container.ai_reply_generator is not None
    assert container.group_ai_reply_generator is None
