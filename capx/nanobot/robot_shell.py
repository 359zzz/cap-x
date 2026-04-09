from __future__ import annotations

import asyncio
from dataclasses import dataclass

from capx.web.models import NanobotTaskStartRequest, NanobotTaskStatusResponse, SessionState

from .bus import MessageBus
from .messages import InboundMessage, OutboundMessage
from .task_client import CapxNanobotTaskClient


@dataclass
class RobotShellConfig:
    """Runtime settings for the cap-x nanobot robot shell."""

    relay_base_url: str = "http://127.0.0.1:8200"
    config_path: str | None = None
    model: str = "openai/gpt-5.4"
    server_url: str = "http://127.0.0.1:8110/chat/completions"
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
        if not text:
            return

        lower = text.lower()
        if lower in {"/help", "help"}:
            await self._reply(
                msg.channel,
                msg.chat_id,
                self._help_text(),
            )
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
                    action = await asyncio.to_thread(
                        self.client.inject_task,
                        status.session_id,
                        text,
                    )
                    await self._reply(
                        msg.channel,
                        msg.chat_id,
                        (
                            f"已把新指令注入到当前任务。\n"
                            f"session_id: {action.session_id}\n"
                            f"当前状态: {action.task.state.value if action.task else 'unknown'}"
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
            await self._reply(
                msg.channel,
                msg.chat_id,
                (
                    f"已启动机器人任务。\n"
                    f"session_id: {action.session_id}\n"
                    f"当前状态: {action.task.state.value if action.task else 'unknown'}\n"
                    f"可以继续发送自然语言；当任务进入 awaiting_user_input 时，我会把它作为后续指令注入。"
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
            await self._reply(msg.channel, msg.chat_id, "当前没有活跃机器人任务。")
            return

        await self._reply(
            msg.channel,
            msg.chat_id,
            self._format_status_message(status),
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
                await self._reply(msg.channel, msg.chat_id, "当前没有可停止的活跃机器人任务。")
                return

            action = await asyncio.to_thread(self.client.stop_task, session_id)
            await self._reply(
                msg.channel,
                msg.chat_id,
                (
                    f"已发送停止命令。\n"
                    f"session_id: {action.session_id}\n"
                    f"当前状态: {action.task.state.value if action.task else 'unknown'}"
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

                signature = (
                    status.state,
                    status.current_block_index,
                    status.total_code_blocks,
                    status.can_accept_injection,
                    status.last_error,
                    status.recent_events[-1].summary if status.recent_events else None,
                )
                if signature != self._last_status_signature:
                    await self._reply(
                        self._owner_channel,
                        self._owner_chat_id,
                        self._format_status_message(status),
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
                        f"任务监控异常: {exc}",
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
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=content,
                metadata=metadata or {},
            )
        )

    def _help_text(self) -> str:
        return (
            "可用命令:\n"
            "/help - 查看帮助\n"
            "/status - 查看当前机器人任务状态\n"
            "/stop - 停止当前机器人任务\n"
            "其他自然语言内容会被解释为:\n"
            "- 没有任务时: 启动新任务\n"
            "- 任务在 awaiting_user_input 时: 注入后续指令"
        )

    def _format_status_message(self, status: NanobotTaskStatusResponse) -> str:
        recent = status.recent_events[-1].summary if status.recent_events else "暂无事件"
        lines = [
            f"任务状态: {status.state.value}",
            f"session_id: {status.session_id}",
            f"代码块进度: {status.current_block_index}/{status.total_code_blocks}",
            f"可注入新指令: {'是' if status.can_accept_injection else '否'}",
            f"最近事件: {recent}",
        ]
        if status.last_error:
            lines.append(f"最后错误: {status.last_error}")
        if status.state == SessionState.AWAITING_USER_INPUT:
            lines.append("现在可以直接发送下一条自然语言，我会把它注入到当前任务。")
        if status.state in {SessionState.COMPLETE, SessionState.ERROR, SessionState.IDLE}:
            lines.append("当前任务已结束，可以直接发送新任务。")
        return "\n".join(lines)

    def _format_busy_message(self, status: NanobotTaskStatusResponse) -> str:
        recent = status.recent_events[-1].summary if status.recent_events else "暂无事件"
        return (
            f"机器人当前正在执行其他步骤，暂时不能接收新自然语言。\n"
            f"当前状态: {status.state.value}\n"
            f"最近事件: {recent}\n"
            f"如果需要查看细节，请发送 /status。"
        )
