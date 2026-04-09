from __future__ import annotations

import asyncio
from typing import Any

from capx.nanobot.bus import MessageBus
from capx.nanobot.messages import OutboundMessage

from .base import BaseChannel


class ChannelManager:
    """Manage embedded channels and route outbound messages."""

    def __init__(self, bus: MessageBus, channels: list[BaseChannel] | None = None) -> None:
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {channel.name: channel for channel in (channels or [])}
        self._dispatch_task: asyncio.Task | None = None
        self._channel_tasks: dict[str, asyncio.Task] = {}

    async def start_all(self) -> None:
        if self._dispatch_task is None:
            self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        for name, channel in self.channels.items():
            if name in self._channel_tasks:
                continue
            self._channel_tasks[name] = asyncio.create_task(channel.start())

    async def stop_all(self) -> None:
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None

        for channel in self.channels.values():
            try:
                await channel.stop()
            except Exception:
                pass

        for name, task in list(self._channel_tasks.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._channel_tasks.pop(name, None)

    async def wait_for_channels(self) -> None:
        tasks = list(self._channel_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _dispatch_outbound(self) -> None:
        while True:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            channel = self.channels.get(msg.channel)
            if channel is None:
                continue
            await channel.send(msg)

    def get_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {}
        for name, channel in self.channels.items():
            item: dict[str, Any] = {"running": channel.is_running}
            getter = getattr(channel, "get_status", None)
            if callable(getter):
                extra = getter()
                if isinstance(extra, dict):
                    item.update(extra)
            status[name] = item
        return status

    @property
    def enabled_channels(self) -> list[str]:
        return list(self.channels.keys())

    def get_channel(self, name: str) -> BaseChannel | None:
        return self.channels.get(name)
