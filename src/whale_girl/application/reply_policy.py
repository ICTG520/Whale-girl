from whale_girl.bootstrap.config import Settings
from whale_girl.domain.message import ConversationType, InboundMessage


class ReplyPolicy:
    """Decide whether an observed message should receive a reply."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def should_reply(self, message: InboundMessage) -> bool:
        if message.is_self or not self._settings.reply_enabled:
            return False

        if message.conversation_type == ConversationType.PRIVATE:
            return message.sender_id in self._settings.qq_friend_whitelist

        if message.conversation_type != ConversationType.GROUP:
            return False

        if message.conversation_id not in self._settings.qq_group_whitelist:
            return False

        if message.is_to_me:
            return True

        text = message.text.casefold()
        return any(word.casefold() in text for word in self._settings.wake_words)
