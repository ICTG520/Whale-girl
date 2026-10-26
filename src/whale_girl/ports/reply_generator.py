from typing import Protocol

from whale_girl.domain.message import InboundMessage


class ReplyGenerator(Protocol):
    """Produce reply text for one normalized inbound message."""

    async def generate(self, message: InboundMessage) -> str | None: ...
