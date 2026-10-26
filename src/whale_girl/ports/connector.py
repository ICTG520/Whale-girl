from typing import Protocol

from whale_girl.domain.message import OutboundReply


class PlatformConnector(Protocol):
    """A platform adapter that can send normalized replies."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send(self, reply: OutboundReply) -> None: ...
