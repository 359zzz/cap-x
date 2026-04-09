from __future__ import annotations

import asyncio

from capx.nanobot import MessageBus
from capx.nanobot.channels import BaseChannel, ChannelConfig, ChannelManager
from capx.nanobot.messages import OutboundMessage


class DummyChannel(BaseChannel):
    name = "dummy"
    display_name = "Dummy"

    def __init__(self, config: ChannelConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.sent: list[OutboundMessage] = []

    async def start(self) -> None:
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(0.05)
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        self.sent.append(msg)


def test_channel_manager_routes_outbound_message() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        channel = DummyChannel(ChannelConfig(), bus)
        manager = ChannelManager(bus, [channel])
        await manager.start_all()
        try:
            await bus.publish_outbound(
                OutboundMessage(
                    channel="dummy",
                    chat_id="chat-1",
                    content="hello",
                )
            )
            await asyncio.sleep(0.2)
            assert len(channel.sent) == 1
            assert channel.sent[0].content == "hello"
        finally:
            await manager.stop_all()

    asyncio.run(scenario())


def test_base_channel_publishes_inbound_message() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        channel = DummyChannel(ChannelConfig(), bus)
        await channel._handle_message(
            sender_id="user-1",
            chat_id="chat-1",
            content="start task",
        )
        inbound = await asyncio.wait_for(bus.consume_inbound(), timeout=1.0)
        assert inbound.channel == "dummy"
        assert inbound.chat_id == "chat-1"
        assert inbound.content == "start task"

    asyncio.run(scenario())
