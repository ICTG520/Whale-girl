import logging
from dataclasses import dataclass
from pathlib import Path

from whale_girl.application.ai_guard import AIRequestGuard
from whale_girl.application.handle_message import HandleInboundMessage
from whale_girl.application.reply_generators import (
    AIReplyConfig,
    AIReplyGenerator,
    FixedReplyGenerator,
    GROUP_CHAT_PROMPT_SUFFIX,
)
from whale_girl.application.reply_policy import ReplyPolicy
from whale_girl.bootstrap.config import Settings
from whale_girl.bootstrap.persona import load_persona
from whale_girl.domain.persona import PersonaVersion
from whale_girl.infrastructure.llm.deepseek import DeepSeekProvider
from whale_girl.infrastructure.persistence.sqlite import SQLiteMessageRepository
from whale_girl.infrastructure.persistence.sqlite_context import (
    SQLiteConversationContextStore,
)
from whale_girl.ports.context import ConversationContextStore
from whale_girl.ports.llm import LLMProvider
from whale_girl.ports.repositories import MessageRepository

logger = logging.getLogger("whale_girl.bootstrap.container")


@dataclass(frozen=True, slots=True)
class AppContainer:
    settings: Settings
    persona: PersonaVersion
    repository: MessageRepository
    context_store: ConversationContextStore
    reply_policy: ReplyPolicy
    fixed_reply_generator: FixedReplyGenerator
    ai_reply_generator: AIReplyGenerator | None
    group_ai_reply_generator: AIReplyGenerator | None
    ai_guard: AIRequestGuard
    group_ai_guard: AIRequestGuard
    llm_provider: LLMProvider
    message_handler: HandleInboundMessage


def build_container(
    settings: Settings | None = None,
    repository: MessageRepository | None = None,
) -> AppContainer:
    resolved_settings = settings or Settings.from_env()
    persona = load_persona(_resolve_project_path(resolved_settings.persona_path))
    resolved_repository = repository or SQLiteMessageRepository(
        _resolve_project_path(resolved_settings.database_path),
        busy_timeout_ms=resolved_settings.sqlite_busy_timeout_ms,
    )
    logger.info(
        "Using SQLite message storage at %s",
        getattr(resolved_repository, "path", resolved_settings.database_path),
    )
    context_store = SQLiteConversationContextStore(resolved_repository)
    reply_policy = ReplyPolicy(resolved_settings)

    fixed_reply_generator = FixedReplyGenerator(resolved_settings.agent_name)
    llm_provider = DeepSeekProvider(
        api_key=resolved_settings.deepseek_api_key,
        base_url=resolved_settings.deepseek_base_url,
        model=resolved_settings.deepseek_model,
        timeout_seconds=resolved_settings.ai_timeout_seconds,
        max_retries=resolved_settings.ai_max_retries,
    )
    ai_guard = AIRequestGuard(
        cooldown_seconds=resolved_settings.ai_cooldown_seconds,
        max_calls_per_minute=resolved_settings.ai_max_calls_per_minute,
        max_calls_per_day=resolved_settings.ai_max_calls_per_day,
    )
    group_ai_guard = AIRequestGuard(
        cooldown_seconds=resolved_settings.ai_group_cooldown_seconds,
        max_calls_per_minute=resolved_settings.ai_group_max_calls_per_minute,
        max_calls_per_day=resolved_settings.ai_group_max_calls_per_day,
    )

    ai_reply_generator: AIReplyGenerator | None = None
    if resolved_settings.ai_enabled:
        ai_reply_generator = AIReplyGenerator(
            persona=persona,
            llm=llm_provider,
            context_store=context_store,
            config=AIReplyConfig(
                fallback_to_fixed=resolved_settings.ai_fallback_to_fixed,
                max_context_messages=resolved_settings.ai_max_context_messages,
                max_context_chars=resolved_settings.ai_max_context_chars,
                max_input_chars=resolved_settings.ai_max_input_chars,
                max_reply_chars=resolved_settings.ai_max_reply_chars,
                max_output_tokens=resolved_settings.ai_max_output_tokens,
                temperature=resolved_settings.ai_temperature,
                timeout_seconds=resolved_settings.ai_timeout_seconds,
                cooldown_seconds=resolved_settings.ai_cooldown_seconds,
                max_calls_per_minute=resolved_settings.ai_max_calls_per_minute,
                max_calls_per_day=resolved_settings.ai_max_calls_per_day,
            ),
            fixed_generator=fixed_reply_generator,
            limiter=ai_guard,
        )
        if not resolved_settings.has_deepseek_key:
            logger.warning(
                "REPLY_MODE=ai 但 DEEPSEEK_API_KEY 为空；请在 .env 中填写 Key。"
            )

    group_ai_reply_generator: AIReplyGenerator | None = None
    if resolved_settings.ai_enabled and resolved_settings.ai_group_enabled:
        group_ai_reply_generator = AIReplyGenerator(
            persona=persona,
            llm=llm_provider,
            context_store=context_store,
            config=AIReplyConfig(
                fallback_to_fixed=resolved_settings.ai_group_fallback_to_fixed,
                max_context_messages=resolved_settings.ai_group_max_context_messages,
                max_context_chars=resolved_settings.ai_max_context_chars,
                max_input_chars=resolved_settings.ai_max_input_chars,
                max_reply_chars=resolved_settings.ai_max_reply_chars,
                max_output_tokens=resolved_settings.ai_max_output_tokens,
                temperature=resolved_settings.ai_temperature,
                timeout_seconds=resolved_settings.ai_timeout_seconds,
                cooldown_seconds=resolved_settings.ai_group_cooldown_seconds,
                max_calls_per_minute=(
                    resolved_settings.ai_group_max_calls_per_minute
                ),
                max_calls_per_day=resolved_settings.ai_group_max_calls_per_day,
                system_prompt_suffix=GROUP_CHAT_PROMPT_SUFFIX,
            ),
            fixed_generator=fixed_reply_generator,
            limiter=group_ai_guard,
        )
        if not resolved_settings.has_deepseek_key:
            logger.warning(
                "群聊 AI 已启用但 DEEPSEEK_API_KEY 为空；群聊调用会按配置回退。"
            )

    message_handler = HandleInboundMessage(
        settings=resolved_settings,
        repository=resolved_repository,
        reply_policy=reply_policy,
        fixed_reply_generator=fixed_reply_generator,
        ai_reply_generator=ai_reply_generator,
        group_ai_reply_generator=group_ai_reply_generator,
        persona_version=persona.version,
    )
    return AppContainer(
        settings=resolved_settings,
        persona=persona,
        repository=resolved_repository,
        context_store=context_store,
        reply_policy=reply_policy,
        fixed_reply_generator=fixed_reply_generator,
        ai_reply_generator=ai_reply_generator,
        group_ai_reply_generator=group_ai_reply_generator,
        ai_guard=ai_guard,
        group_ai_guard=group_ai_guard,
        llm_provider=llm_provider,
        message_handler=message_handler,
    )


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parents[3]
    return project_root / path
