from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .bus import MessageBus
from .channels import (
    ChannelManager,
    ConsoleChannel,
    ConsoleChannelConfig,
    HttpBridgeChannel,
    HttpBridgeChannelConfig,
)
from .robot_shell import CapxNanobotRobotShell, RobotShellConfig


@dataclass
class CapxNanobotRuntimeConfig:
    """Top-level runtime config for the embedded cap-x nanobot gateway."""

    shell: RobotShellConfig = field(default_factory=RobotShellConfig)
    console: ConsoleChannelConfig = field(default_factory=ConsoleChannelConfig)
    http_bridge: HttpBridgeChannelConfig = field(default_factory=HttpBridgeChannelConfig)
    enable_console_channel: bool = True
    enable_http_channel: bool = False


class CapxNanobotRuntime:
    """Bundle the embedded bus, robot shell, and channel manager."""

    def __init__(self, config: CapxNanobotRuntimeConfig | None = None) -> None:
        self.config = config or CapxNanobotRuntimeConfig()
        self.bus = MessageBus()
        self.shell = CapxNanobotRobotShell(self.bus, self.config.shell)
        channels = []
        if self.config.enable_console_channel and self.config.console.enabled:
            channels.append(ConsoleChannel(self.config.console, self.bus))
        if self.config.enable_http_channel and self.config.http_bridge.enabled:
            channels.append(HttpBridgeChannel(self.config.http_bridge, self.bus))
        self.channel_manager = ChannelManager(self.bus, channels)

    async def start(self) -> None:
        await self.shell.start()
        await self.channel_manager.start_all()

    async def stop(self) -> None:
        await self.channel_manager.stop_all()
        await self.shell.stop()

    async def wait(self) -> None:
        await self.channel_manager.wait_for_channels()

    def get_channel(self, name: str) -> Any | None:
        return self.channel_manager.get_channel(name)
