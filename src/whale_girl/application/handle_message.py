import logging

from whale_girl.application.reply_generators import FixedReplyGenerator
from whale_girl.application.reply_policy import ReplyPolicy
from whale_girl.bootstrap.config import Settings
from whale_girl.domain.message import ConversationType, InboundMessage, OutboundReply
from whale_girl.domain.turn import TurnTrigger
from whale_girl.ports.reply_generator import ReplyGenerator
from whale_girl.ports.repositories import MessageRepository

logger = logging.getLogger("whale_girl.application.handle_message")


class HandleInboundMessage:
    """Observe a message and produce a reply when the reply policy allows it."""

    def __init__(
        self,
        settings: Settings,
        repository: MessageRepository,
        reply_policy: ReplyPolicy,
        fixed_reply_generator: ReplyGenerator | None = None,
        ai_reply_generator: ReplyGenerator | None = None,
        group_ai_reply_generator: ReplyGenerator | None = None,
        persona_version: int = 1,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._reply_policy = reply_policy
        self._fixed_reply_generator = (
            fixed_reply_generator or FixedReplyGenerator(settings.agent_name)
        )
        self._ai_reply_generator = ai_reply_generator
        self._group_ai_reply_generator = group_ai_reply_generator
        self._persona_version = persona_version

    async def execute(self, message: InboundMessage) -> OutboundReply | None:
        if message.is_self:
            return None

        should_reply = self._reply_policy.should_reply(message)

        if message.conversation_type == ConversationType.GROUP:
            if message.conversation_id not in self._settings.qq_group_whitelist:
                logger.debug("Ignoring group outside whitelist: %s", message.conversation_id)
                return None
            if not self._settings.observe_all_group_messages and not should_reply:
                return None

        stored = await self._repository.save_inbound(message)
        if stored is None:
            logger.debug("Ignoring duplicate message: %s", message.message_id)
            return None

        reply_generator = self._fixed_reply_generator
        if message.conversation_type == ConversationType.GROUP:
            if self._group_ai_reply_generator is None:
                if not should_reply:
                    return None
            elif not should_reply:
                return None
            else:
                reply_generator = self._group_ai_reply_generator
        else:
            if not should_reply:
                return None
            if self._ai_reply_generator is not None:
                reply_generator = self._ai_reply_generator

        turn = await self._repository.create_turn(
            stored,
            trigger_type=self._trigger_type(message),
            persona_version=self._persona_version,
        )
        try:
            text = await reply_generator.generate(message)
        except Exception:
            await self._repository.mark_turn_failed(turn.id)
            raise
        if text is None or not text.strip():
            await self._repository.mark_turn_suppressed(turn.id)
            return None

        await self._repository.mark_turn_generated(turn.id)
        return OutboundReply(
            platform=message.platform,
            account_id=message.account_id,
            conversation_type=message.conversation_type,
            conversation_id=message.conversation_id,
            text=text,
            reply_to_message_id=message.message_id,
            turn_id=turn.id,
        )

    async def record_sent(
        self,
        reply: OutboundReply,
        *,
        platform_message_id: str | None,
    ) -> None:
        if reply.turn_id is None:
            return
        await self._repository.save_outbound(
            reply,
            platform_message_id=platform_message_id,
            agent_name=self._settings.agent_name,
        )

    async def record_failed(self, reply: OutboundReply) -> None:
        if reply.turn_id is None:
            return
        await self._repository.mark_turn_failed(reply.turn_id)

    def _trigger_type(self, message: InboundMessage) -> TurnTrigger:
        if message.conversation_type == ConversationType.PRIVATE:
            return TurnTrigger.PRIVATE
        if message.is_to_me:
            return TurnTrigger.GROUP_AT
        return TurnTrigger.GROUP_WAKE_WORD
