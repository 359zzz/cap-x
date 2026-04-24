from __future__ import annotations

import asyncio
from dataclasses import dataclass

from capx.nanobot.messages import OutboundMessage
from capx.nanobot.console_io import read_console_line

from .base import BaseChannel, ChannelConfig


@dataclass
class ConsoleChannelConfig(ChannelConfig):
    """Configuration for the built-in local console channel."""

    sender_id: str = "local-user"
    chat_id: str = "local-chat"
    intro: bool = True


class ConsoleChannel(BaseChannel):
    """Local stdin/stdout channel for debugging the embedded nanobot shell."""

    name = "console"
    display_name = "Console"

    def __init__(self, config: ConsoleChannelConfig, bus):
        super().__init__(config, bus)
        self.config = config

    async def start(self) -> None:
        self._running = True
        if self.config.intro:
            print("Capx Nanobot Gateway")
            print("Type natural language to start/inject tasks.")
            print("Commands: /help /status /stop exit")
            print()
        try:
            while self._running:
                text = await self._read_input("You: ")
                if text is None:
                    break
                stripped = text.strip()
                if not stripped:
                    continue
                if stripped.lower() in {"exit", "quit"}:
                    break
                await self._handle_message(
                    sender_id=self.config.sender_id,
                    chat_id=self.config.chat_id,
                    content=text,
                )
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        print()
        print("Robot:")
        print(msg.content)
        print()

    async def _read_input(self, prompt: str) -> str | None:
        try:
            return await asyncio.to_thread(read_console_line, prompt)
        except EOFError:
            return None
