from __future__ import annotations

from fastapi.testclient import TestClient

from capx.nanobot import CapxNanobotRuntime, CapxNanobotRuntimeConfig, RobotShellConfig
from capx.nanobot.channels import HttpBridgeChannelConfig
from capx.nanobot.gateway_app import create_gateway_app
from capx.web.models import (
    NanobotTaskActionResponse,
    NanobotTaskStatusResponse,
    SessionState,
)


class FakeTaskClient:
    def __init__(self) -> None:
        self.start_calls: list[object] = []
        self.inject_calls: list[tuple[str, str]] = []
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

    def inject_task(self, session_id: str, text: str) -> NanobotTaskActionResponse:
        self.inject_calls.append((session_id, text))
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


def test_http_gateway_bridges_inbound_and_outbound_messages() -> None:
    runtime = CapxNanobotRuntime(
        CapxNanobotRuntimeConfig(
            shell=RobotShellConfig(
                config_path="env_configs/openarm/openarm_motion_real.yaml",
                poll_interval_s=60.0,
            ),
            http_bridge=HttpBridgeChannelConfig(),
            enable_console_channel=False,
            enable_http_channel=True,
        )
    )
    fake_client = FakeTaskClient()
    runtime.shell.client = fake_client

    with TestClient(create_gateway_app(runtime=runtime)) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert "http" in health.json()["enabled_channels"]

        inbound = client.post(
            "/channels/http/inbound",
            json={
                "chat_id": "chat-1",
                "sender_id": "user-1",
                "content": "把左手抬到胸前",
            },
        )
        assert inbound.status_code == 200
        assert inbound.json()["status"] == "queued"

        outbound = client.get(
            "/channels/http/outbound",
            params={"chat_id": "chat-1", "wait_ms": 2000},
        )
        payload = outbound.json()
        assert outbound.status_code == 200
        assert payload["count"] == 1
        assert "已启动机器人任务" in payload["messages"][0]["content"]
        assert len(fake_client.start_calls) == 1

        fake_client.task_status = NanobotTaskStatusResponse(
            session_id="task-1",
            state=SessionState.AWAITING_USER_INPUT,
            current_block_index=1,
            total_code_blocks=2,
            can_accept_injection=True,
            active=True,
            recent_events=[],
            last_error=None,
        )

        followup = client.post(
            "/channels/http/inbound",
            json={
                "chat_id": "chat-1",
                "sender_id": "user-1",
                "content": "改成轻微张开左腕",
            },
        )
        assert followup.status_code == 200

        outbound = client.get(
            "/channels/http/outbound",
            params={"chat_id": "chat-1", "wait_ms": 2000},
        )
        payload = outbound.json()
        assert payload["count"] == 1
        assert "已把新指令注入到当前任务" in payload["messages"][0]["content"]
        assert fake_client.inject_calls == [("task-1", "改成轻微张开左腕")]
