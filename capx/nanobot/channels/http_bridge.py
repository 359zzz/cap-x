from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from capx.nanobot.messages import OutboundMessage

from .base import BaseChannel, ChannelConfig


@dataclass
class HttpBridgeChannelConfig(ChannelConfig):
    """Configuration for the embedded HTTP polling bridge channel."""

    sender_id: str = "http-user"
    max_pending_per_chat: int = 100


class HttpBridgeChannel(BaseChannel):
    """HTTP polling bridge for app-side nanobot integrations."""

    name = "http"
    display_name = "HTTP Bridge"

    def __init__(self, config: HttpBridgeChannelConfig, bus):
        super().__init__(config, bus)
        self.config = config
        self._pending: list[OutboundMessage] = []
        self._condition = asyncio.Condition()
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()
        try:
            await self._stop_event.wait()
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        async with self._condition:
            self._condition.notify_all()

    async def send(self, msg: OutboundMessage) -> None:
        async with self._condition:
            self._pending.append(msg)
            self._trim_pending_for_chat(msg.chat_id)
            self._condition.notify_all()

    async def receive_message(
        self,
        *,
        chat_id: str,
        content: str,
        sender_id: str | None = None,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
    ) -> None:
        await self._handle_message(
            sender_id=sender_id or self.config.sender_id,
            chat_id=chat_id,
            content=content,
            media=media,
            metadata=metadata,
            session_key=session_key,
        )

    async def pop_outbound(
        self,
        *,
        chat_id: str | None = None,
        limit: int = 20,
        wait_ms: int = 0,
    ) -> list[OutboundMessage]:
        limit = max(1, limit)
        deadline = time.monotonic() + max(0, wait_ms) / 1000.0

        async with self._condition:
            while True:
                selected, remaining = self._partition_pending(chat_id=chat_id, limit=limit)
                if selected:
                    self._pending = remaining
                    return selected
                if wait_ms <= 0 or not self._running:
                    return []
                remaining_wait = deadline - time.monotonic()
                if remaining_wait <= 0:
                    return []
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining_wait)
                except asyncio.TimeoutError:
                    return []

    def get_status(self) -> dict[str, Any]:
        pending_by_chat: dict[str, int] = {}
        for msg in self._pending:
            pending_by_chat[msg.chat_id] = pending_by_chat.get(msg.chat_id, 0) + 1
        return {
            "pending_total": len(self._pending),
            "pending_by_chat": pending_by_chat,
        }

    def _partition_pending(
        self,
        *,
        chat_id: str | None,
        limit: int,
    ) -> tuple[list[OutboundMessage], list[OutboundMessage]]:
        selected: list[OutboundMessage] = []
        remaining: list[OutboundMessage] = []
        for msg in self._pending:
            if len(selected) < limit and (chat_id is None or msg.chat_id == chat_id):
                selected.append(msg)
            else:
                remaining.append(msg)
        return selected, remaining

    def _trim_pending_for_chat(self, chat_id: str) -> None:
        max_pending = max(1, self.config.max_pending_per_chat)
        pending_for_chat = 0
        trimmed: list[OutboundMessage] = []
        for msg in reversed(self._pending):
            if msg.chat_id == chat_id:
                pending_for_chat += 1
                if pending_for_chat > max_pending:
                    continue
            trimmed.append(msg)
        trimmed.reverse()
        self._pending = trimmed
