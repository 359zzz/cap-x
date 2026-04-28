from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from capx.utils.runtime_defaults import default_llm_model_name, default_llm_server_url
from capx.web.models import NanobotTaskStartRequest, NanobotTaskStatusResponse, SessionState

from .bus import MessageBus
from .messages import InboundMessage, OutboundMessage
from .task_client import CapxNanobotTaskClient

_STATE_LABELS = {
    SessionState.IDLE: "空闲",
    SessionState.LOADING_CONFIG: "载入配置",
    SessionState.RUNNING: "执行中",
    SessionState.AWAITING_USER_INPUT: "等待指令",
    SessionState.COMPLETE: "已完成",
    SessionState.ERROR: "异常",
}


@dataclass
class RobotShellConfig:
    """Runtime settings for the cap-x nanobot robot shell."""

    relay_base_url: str = "http://127.0.0.1:8200"
    config_path: str | None = None
    model: str = field(default_factory=default_llm_model_name)
    server_url: str = field(default_factory=default_llm_server_url)
    temperature: float = 0.2
    max_tokens: int = 8192
    use_visual_feedback: bool | None = None
    use_img_differencing: bool | None = None
    visual_differencing_model: str | None = None
    visual_differencing_model_server_url: str | None = None
    await_user_input_each_turn: bool = True
    execution_timeout: int = 180
    poll_interval_s: float = 2.0


class CapxNanobotRobotShell:
    """Minimal nanobot-style outer shell for the cap-x robot runtime.

    The shell consumes inbound messages from a :class:`MessageBus`, translates
    them into cap-x nanobot relay calls, and publishes structured text updates
    back to the same bus.
    """

    def __init__(
        self,
        bus: MessageBus,
        config: RobotShellConfig | None = None,
        *,
        client: CapxNanobotTaskClient | None = None,
    ) -> None:
        self.bus = bus
        self.config = config or RobotShellConfig()
        self.client = client or CapxNanobotTaskClient(base_url=self.config.relay_base_url)

        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._task_lock = asyncio.Lock()

        self._owner_channel: str | None = None
        self._owner_chat_id: str | None = None
        self._owner_session_key: str | None = None
        self._task_session_id: str | None = None
        self._last_status_signature: tuple[object, ...] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._consume_inbound())
        self._monitor_task = asyncio.create_task(self._monitor_active_task())

    async def stop(self) -> None:
        self._running = False
        tasks = [task for task in (self._worker_task, self._monitor_task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        self._monitor_task = None

    async def _consume_inbound(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await self._handle_message(msg)

    async def _handle_message(self, msg: InboundMessage) -> None:
        text = msg.content.strip()
        if not text and msg.media:
            text = "Please inspect the attached image and use it for the robot task."
        elif not text:
            return

        lower = text.lower()
        if lower in {"/help", "help"}:
            await self._reply(msg.channel, msg.chat_id, self._help_text())
            return
        if lower == "/status":
            await self._handle_status(msg)
            return
        if lower == "/stop":
            await self._handle_stop(msg)
            return

        async with self._task_lock:
            status = await self._get_known_task_status()

            if status is not None and status.active:
                if self._owner_session_key and msg.session_key != self._owner_session_key:
                    await self._reply(
                        msg.channel,
                        msg.chat_id,
                        self._format_busy_message(status),
                    )
                    return

                if status.can_accept_injection:
                    inject_kwargs = {"media": msg.media} if msg.media else {}
                    action = await asyncio.to_thread(
                        self.client.inject_task,
                        status.session_id,
                        text,
                        **inject_kwargs,
                    )
                    state = action.task.state.value if action.task else "unknown"
                    await self._reply(
                        msg.channel,
                        msg.chat_id,
                        "\n".join(
                            (
                                "已更新",
                                f"状态  {self._format_state_label(state)}",
                            )
                        ),
                        metadata={"session_id": action.session_id, "action": "inject"},
                    )
                    return

                await self._reply(
                    msg.channel,
                    msg.chat_id,
                    self._format_busy_message(status),
                )
                return

            request = NanobotTaskStartRequest(
                config_path=self.config.config_path,
                initial_instruction=text,
                initial_media=list(msg.media),
                model=self.config.model,
                server_url=self.config.server_url,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                use_visual_feedback=self.config.use_visual_feedback,
                use_img_differencing=self.config.use_img_differencing,
                visual_differencing_model=self.config.visual_differencing_model or self.config.model,
                visual_differencing_model_server_url=(
                    self.config.visual_differencing_model_server_url or self.config.server_url
                ),
                await_user_input_each_turn=self.config.await_user_input_each_turn,
                execution_timeout=self.config.execution_timeout,
            )
            action = await asyncio.to_thread(self.client.start_task, request)
            self._adopt_task_owner(
                session_key=msg.session_key,
                channel=msg.channel,
                chat_id=msg.chat_id,
                session_id=action.session_id,
            )
            state = action.task.state.value if action.task else "unknown"
            await self._reply(
                msg.channel,
                msg.chat_id,
                "\n".join(
                    (
                        "已启动",
                        f"ID    {action.session_id}",
                        f"状态  {self._format_state_label(state)}",
                    )
                ),
                metadata={"session_id": action.session_id, "action": "start"},
            )

    async def _handle_status(self, msg: InboundMessage) -> None:
        status = await self._get_known_task_status()
        if status is None:
            health = await asyncio.to_thread(self.client.health)
            active_task = health.get("active_task")
            if isinstance(active_task, dict):
                status = NanobotTaskStatusResponse.model_validate(active_task)

        if status is None:
            await self._reply(msg.channel, msg.chat_id, "当前无任务")
            return

        await self._reply(
            msg.channel,
            msg.chat_id,
            self._format_status_message(status),
            media=self._recent_status_media(status),
            metadata={"session_id": status.session_id, "action": "status"},
        )

    async def _handle_stop(self, msg: InboundMessage) -> None:
        async with self._task_lock:
            session_id = self._task_session_id
            if session_id is None:
                health = await asyncio.to_thread(self.client.health)
                active_task = health.get("active_task")
                if isinstance(active_task, dict):
                    session_id = str(active_task.get("session_id") or "")
            if not session_id:
                await self._reply(msg.channel, msg.chat_id, "当前无任务")
                return

            action = await asyncio.to_thread(self.client.stop_task, session_id)
            state = action.task.state.value if action.task else "unknown"
            await self._reply(
                msg.channel,
                msg.chat_id,
                "\n".join(
                    (
                        "已请求停止",
                        f"状态  {self._format_state_label(state)}",
                    )
                ),
                metadata={"session_id": action.session_id, "action": "stop"},
            )
            if action.task is not None and not action.task.active:
                self._clear_task_owner()

    async def _monitor_active_task(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.config.poll_interval_s)
                status = await self._get_known_task_status()
                if status is None or self._owner_channel is None or self._owner_chat_id is None:
                    continue

                latest_summary = status.recent_events[-1].summary if status.recent_events else None
                latest_media = tuple(status.recent_events[-1].media) if status.recent_events else ()
                signature = (
                    status.state,
                    status.current_block_index,
                    status.total_code_blocks,
                    status.can_accept_injection,
                    status.last_error,
                    latest_summary,
                    latest_media,
                )
                if signature != self._last_status_signature:
                    await self._reply(
                        self._owner_channel,
                        self._owner_chat_id,
                        self._format_status_message(status),
                        media=self._recent_status_media(status),
                        metadata={"session_id": status.session_id, "action": "monitor"},
                    )
                    self._last_status_signature = signature

                if not status.active:
                    self._clear_task_owner()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._owner_channel and self._owner_chat_id:
                    await self._reply(
                        self._owner_channel,
                        self._owner_chat_id,
                        f"监控异常  {exc}",
                    )

    async def _get_known_task_status(self) -> NanobotTaskStatusResponse | None:
        if not self._task_session_id:
            return None
        try:
            return await asyncio.to_thread(self.client.get_task, self._task_session_id)
        except Exception:
            return None

    def _adopt_task_owner(
        self,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        session_id: str,
    ) -> None:
        self._owner_session_key = session_key
        self._owner_channel = channel
        self._owner_chat_id = chat_id
        self._task_session_id = session_id
        self._last_status_signature = None

    def _clear_task_owner(self) -> None:
        self._owner_session_key = None
        self._owner_channel = None
        self._owner_chat_id = None
        self._task_session_id = None
        self._last_status_signature = None

    async def _reply(
        self,
        channel: str,
        chat_id: str,
        content: str,
        *,
        media: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=content,
                media=media or [],
                metadata=metadata or {},
            )
        )

    def _recent_status_media(self, status: NanobotTaskStatusResponse) -> list[str]:
        media: list[str] = []
        for event in reversed(status.recent_events):
            event_media = getattr(event, "media", None) or []
            for item in event_media:
                if item and item not in media:
                    media.append(item)
                if len(media) >= 3:
                    return media
        return media

    def _help_text(self) -> str:
        return "\n".join(
            (
                "命令",
                "/help   查看帮助",
                "/status 查看状态",
                "/stop   停止任务",
                "其他文本会作为自然语言指令发送。",
            )
        )

    def _format_status_message(self, status: NanobotTaskStatusResponse) -> str:
        lines = [
            f"状态  {self._format_state_label(status.state)}",
            f"进度  {status.current_block_index}/{status.total_code_blocks}",
            f"注入  {'可用' if status.can_accept_injection else '不可'}",
        ]
        if status.last_error:
            lines.append(f"异常  {status.last_error}")

        recent_lines = self._format_recent_events(status)
        if recent_lines:
            lines.append("")
            lines.append("最近")
            lines.extend(recent_lines)

        if status.state == SessionState.AWAITING_USER_INPUT:
            lines.append("")
            lines.append("可直接发送下一条指令。")
        if status.state in {SessionState.COMPLETE, SessionState.ERROR, SessionState.IDLE}:
            lines.append("")
            lines.append("可发送新任务。")
        return "\n".join(lines)

    def _format_busy_message(self, status: NanobotTaskStatusResponse) -> str:
        lines = [
            "当前任务占用中",
            f"状态  {self._format_state_label(status.state)}",
        ]
        recent_lines = self._format_recent_events(status)
        if recent_lines:
            lines.append("最近")
            lines.extend(recent_lines)
        lines.append("输入 /status 查看详情。")
        return "\n".join(lines)

    def _format_recent_events(self, status: NanobotTaskStatusResponse) -> list[str]:
        recent = list(status.recent_events[-3:])
        if not recent:
            return []
        return [f"- {event.summary}" for event in reversed(recent)]

    def _format_state_label(self, state: SessionState | str) -> str:
        if isinstance(state, SessionState):
            return _STATE_LABELS.get(state, state.value)
        for enum_value, label in _STATE_LABELS.items():
            if enum_value.value == state:
                return label
        return str(state)
