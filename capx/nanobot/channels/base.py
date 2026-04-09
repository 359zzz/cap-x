from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from capx.nanobot.bus import MessageBus
from capx.nanobot.messages import InboundMessage, OutboundMessage


@dataclass
class ChannelConfig:
    """Minimal channel configuration shared by embedded cap-x channels."""

    enabled: bool = True
    allow_from: list[str] = field(default_factory=lambda: ["*"])


class BaseChannel(ABC):
    """Base interface for cap-x embedded nanobot channels."""

    name: str = "base"
    display_name: str = "Base"

    def __init__(self, config: ChannelConfig, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start the long-running channel receive loop."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and release resources."""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send one outbound message through this channel."""

    def is_allowed(self, sender_id: str) -> bool:
        allow_from = self.config.allow_from
        if "*" in allow_from:
            return True
        return str(sender_id) in allow_from

    async def _handle_message(
        self,
        *,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
    ) -> None:
        if not self.is_allowed(sender_id):
            return
        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=str(sender_id),
                chat_id=str(chat_id),
                content=content,
                media=media or [],
                metadata=metadata or {},
                session_key_override=session_key,
            )
        )

    @property
    def is_running(self) -> bool:
        return self._running
