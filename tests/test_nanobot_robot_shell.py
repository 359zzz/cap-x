from __future__ import annotations

import asyncio

from capx.nanobot import CapxNanobotRobotShell, InboundMessage, MessageBus, RobotShellConfig
from capx.web.models import (
    NanobotEventItem,
    NanobotTaskActionResponse,
    NanobotTaskStatusResponse,
    SessionState,
)


class FakeTaskClient:
    def __init__(self) -> None:
        self.start_calls: list[object] = []
        self.inject_calls: list[tuple[str, str]] = []
        self.inject_media_calls: list[list[str]] = []
        self.stop_calls: list[str] = []
        self.health_payload: dict[str, object] = {"status": "ok", "active_task": None}
        self.task_status = NanobotTaskStatusResponse(
            session_id="task-1",
            state=SessionState.RUNNING,
            current_block_index=0,
            total_code_blocks=1,
            can_accept_injection=False,
            active=True,
            recent_events=[],
            last_error=None,
        )

    def health(self) -> dict[str, object]:
        return self.health_payload

    def start_task(self, request) -> NanobotTaskActionResponse:
        self.start_calls.append(request)
        return NanobotTaskActionResponse(
            status="started",
            session_id="task-1",
            task=self.task_status,
        )

    def get_task(self, session_id: str) -> NanobotTaskStatusResponse:
        assert session_id == "task-1"
        return self.task_status

    def inject_task(
        self,
        session_id: str,
        text: str,
        *,
        media: list[str] | None = None,
    ) -> NanobotTaskActionResponse:
        self.inject_calls.append((session_id, text))
        self.inject_media_calls.append(list(media or []))
        return NanobotTaskActionResponse(
            status="injected",
            session_id=session_id,
            task=self.task_status,
        )

    def stop_task(self, session_id: str) -> NanobotTaskActionResponse:
        self.stop_calls.append(session_id)
        return NanobotTaskActionResponse(
            status="stopped",
            session_id=session_id,
            task=NanobotTaskStatusResponse(
                session_id=session_id,
                state=SessionState.IDLE,
                current_block_index=0,
                total_code_blocks=1,
                can_accept_injection=False,
                active=False,
                recent_events=[],
                last_error=None,
            ),
        )


async def _get_one_outbound(bus: MessageBus) -> str:
    msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
    return msg.content


async def _get_one_outbound_message(bus: MessageBus):
    return await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)


def test_robot_shell_starts_task_from_plain_message() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Raise the left arm a little.",
                )
            )
            content = await _get_one_outbound(bus)
            assert "已启动" in content
            assert "ID    task-1" in content
            assert "状态  执行中" in content
            assert len(client.start_calls) == 1
            assert client.start_calls[0].initial_instruction == "Raise the left arm a little."
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_robot_shell_forwards_initial_media_to_start_request() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            image = "data:image/png;base64,abc123"
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Describe the attached image.",
                    media=[image],
                )
            )
            await _get_one_outbound(bus)
            assert len(client.start_calls) == 1
            assert client.start_calls[0].initial_media == [image]
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_robot_shell_status_forwards_visual_media() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Start a task.",
                )
            )
            await _get_one_outbound(bus)

            image = "data:image/png;base64,abc123"
            client.task_status = NanobotTaskStatusResponse(
                session_id="task-1",
                state=SessionState.AWAITING_USER_INPUT,
                current_block_index=1,
                total_code_blocks=1,
                can_accept_injection=True,
                active=True,
                recent_events=[
                    NanobotEventItem(
                        type="visual_feedback",
                        summary="captured visual feedback",
                        media=[image],
                    )
                ],
                last_error=None,
            )

            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="/status",
                )
            )
            msg = await _get_one_outbound_message(bus)
            assert image in msg.media
            assert "captured visual feedback" in msg.content
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_robot_shell_injects_followup_when_task_awaits_input() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Start the task.",
                )
            )
            await _get_one_outbound(bus)

            client.task_status = NanobotTaskStatusResponse(
                session_id="task-1",
                state=SessionState.AWAITING_USER_INPUT,
                current_block_index=1,
                total_code_blocks=2,
                can_accept_injection=True,
                active=True,
                recent_events=[],
                last_error=None,
            )

            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Switch to a smaller arm opening.",
                )
            )
            content = await _get_one_outbound(bus)
            assert "已更新" in content
            assert "状态  等待指令" in content
            assert client.inject_calls == [("task-1", "Switch to a smaller arm opening.")]
            assert client.inject_media_calls == [[]]
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_robot_shell_forwards_followup_media_to_injection() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Start task",
                )
            )
            await _get_one_outbound(bus)

            client.task_status = NanobotTaskStatusResponse(
                session_id="task-1",
                state=SessionState.AWAITING_USER_INPUT,
                current_block_index=1,
                total_code_blocks=2,
                can_accept_injection=True,
                active=True,
                recent_events=[],
                last_error=None,
            )

            image = "data:image/png;base64,followup"
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Continue with this image.",
                    media=[image],
                )
            )
            await _get_one_outbound(bus)
            assert client.inject_calls == [("task-1", "Continue with this image.")]
            assert client.inject_media_calls == [[image]]
        finally:
            await shell.stop()

    asyncio.run(scenario())


def test_robot_shell_reports_busy_to_other_session() -> None:
    async def scenario() -> None:
        bus = MessageBus()
        client = FakeTaskClient()
        shell = CapxNanobotRobotShell(
            bus,
            RobotShellConfig(config_path="env_configs/openarm/openarm_motion_real.yaml", poll_interval_s=60.0),
            client=client,
        )
        await shell.start()
        try:
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-1",
                    chat_id="chat-1",
                    content="Start a task.",
                )
            )
            await _get_one_outbound(bus)

            client.task_status = NanobotTaskStatusResponse(
                session_id="task-1",
                state=SessionState.RUNNING,
                current_block_index=1,
                total_code_blocks=2,
                can_accept_injection=False,
                active=True,
                recent_events=[],
                last_error=None,
            )

            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="user-2",
                    chat_id="chat-2",
                    content="I also want to start a new task.",
                )
            )
            content = await _get_one_outbound(bus)
            assert "当前任务占用中" in content
            assert "状态  执行中" in content
            assert len(client.start_calls) == 1
        finally:
            await shell.stop()

    asyncio.run(scenario())
