import logging

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from whale_girl.bootstrap.container import build_container
from whale_girl.infrastructure.connectors.qq.mapping import event_to_inbound

logger = logging.getLogger("whale_girl.qq_gateway")

container = build_container()
qq_message = on_message(priority=10, block=False)
driver = get_driver()


@driver.on_startup
async def initialize_message_storage() -> None:
    await container.repository.initialize()
    logger.info("Message storage initialized")


@qq_message.handle()
async def handle_qq_message(bot: Bot, event: MessageEvent) -> None:
    try:
        incoming = event_to_inbound(event)
        logger.info(
            "Observed QQ message platform=%s account=%s conversation=%s:%s sender=%s message_id=%s to_me=%s",
            incoming.platform,
            incoming.account_id,
            incoming.conversation_type.value,
            incoming.conversation_id,
            incoming.sender_id,
            incoming.message_id,
            incoming.is_to_me,
        )
        logger.debug("QQ message text length: %s", len(incoming.text))

        reply = await container.message_handler.execute(incoming)
        if reply is not None:
            try:
                sent = await bot.send(event, reply.text)
            except Exception:
                await container.message_handler.record_failed(reply)
                raise
            try:
                await container.message_handler.record_sent(
                    reply,
                    platform_message_id=_extract_message_id(sent),
                )
            except Exception:
                logger.exception("Failed to persist outbound QQ message")
    except Exception:
        logger.exception("Failed to process QQ message")


def _extract_message_id(result: object) -> str | None:
    if isinstance(result, dict):
        value = result.get("message_id")
    else:
        value = getattr(result, "message_id", result)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
