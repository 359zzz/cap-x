from __future__ import annotations

import asyncio
import json

from capx.web.models import SessionState
from capx.web.nanobot_relay import (
    apply_initial_instruction_to_env_factory,
    build_nanobot_task_status,
)
from capx.web.session_manager import Session, SessionManager


def test_apply_initial_instruction_to_env_factory_is_non_mutating() -> None:
    env_factory = {
        "cfg": {
            "prompt": "Base prompt.",
            "task_only_prompt": "Base task.",
            "multi_turn_prompt": "Base multi turn.",
        }
    }

    updated = apply_initial_instruction_to_env_factory(
        env_factory,
        "Raise the left hand slightly.",
    )

    assert updated is not env_factory
    assert updated["cfg"]["task_only_prompt"].endswith("Raise the left hand slightly.")
    assert "Nanobot Runtime Instruction" in updated["cfg"]["prompt"]
    assert "follow-up guidance through nanobot" in updated["cfg"]["multi_turn_prompt"]
    assert env_factory["cfg"]["task_only_prompt"] == "Base task."
    assert env_factory["cfg"]["prompt"] == "Base prompt."


def test_apply_initial_instruction_to_env_factory_adds_anchor_motion_hints() -> None:
    env_factory = {
        "cfg": {
            "prompt": "Base prompt.",
            "task_only_prompt": "Base task.",
            "multi_turn_prompt": "Base multi turn.",
        }
    }

    updated = apply_initial_instruction_to_env_factory(
        env_factory,
        (
            "Run tomato_dual_locate_ready, tomato_dual_grasp_sync, "
            "then safe standby. If the gripper cannot fully reach the recorded value, continue anyway."
        ),
    )

    prompt = updated["cfg"]["prompt"]
    assert "Nanobot Instruction Hints" in prompt
    assert "tomato_dual_locate_ready" in prompt
    assert "safe_standby" in prompt
    assert "ignore_gripper=True" in prompt
    assert "avoid perception tools" in updated["cfg"]["multi_turn_prompt"]


def test_build_nanobot_task_status_summarizes_session_history() -> None:
    session = Session(
        session_id="session-1",
        state=SessionState.AWAITING_USER_INPUT,
        config_path="env_configs/openarm/openarm_motion_real.yaml",
        current_block_index=2,
        total_code_blocks=3,
        num_regenerations=1,
    )
    session.event_history = [
        json.dumps(
            {
                "type": "state_update",
                "timestamp": "2026-04-09T10:00:00Z",
                "state": "running",
            }
        ),
        json.dumps(
            {
                "type": "code_execution_result",
                "timestamp": "2026-04-09T10:00:01Z",
                "block_index": 2,
                "success": True,
                "reward": 0.0,
            }
        ),
        json.dumps(
            {
                "type": "user_prompt_request",
                "timestamp": "2026-04-09T10:00:02Z",
                "current_state_summary": "Waiting for a follow-up instruction.",
            }
        ),
    ]

    status = build_nanobot_task_status(session, max_events=2)

    assert status["session_id"] == "session-1"
    assert status["state"] == SessionState.AWAITING_USER_INPUT
    assert status["can_accept_injection"] is True
    assert status["active"] is True
    assert len(status["recent_events"]) == 2
    assert status["recent_events"][-1]["summary"] == "等待下一条指令"
    assert status["last_error"] is None


def test_build_nanobot_task_status_includes_last_error() -> None:
    session = Session(
        session_id="session-2",
        state=SessionState.ERROR,
        config_path="env_configs/openarm/openarm_motion_real.yaml",
    )
    session.event_history = [
        json.dumps(
            {
                "type": "error",
                "timestamp": "2026-04-09T10:01:00Z",
                "message": "Perception service unavailable.",
            }
        )
    ]

    status = build_nanobot_task_status(session)

    assert status["active"] is False
    assert status["can_accept_injection"] is False
    assert status["last_error"] == "异常：Perception service unavailable."


def test_build_nanobot_task_status_includes_image_analysis_media() -> None:
    image = "data:image/png;base64,abc123"
    session = Session(
        session_id="session-3",
        state=SessionState.AWAITING_USER_INPUT,
        config_path="env_configs/openarm/openarm_motion_real.yaml",
    )
    session.event_history = [
        json.dumps(
            {
                "type": "image_analysis",
                "timestamp": "2026-04-09T10:02:00Z",
                "analysis_type": "initial_description",
                "content": "A red block is on the table.",
                "images": [image],
            }
        )
    ]

    status = build_nanobot_task_status(session)

    assert status["recent_events"][0]["summary"] == "视觉分析：A red block is on the table."
    assert status["recent_events"][0]["media"] == [image]


def test_build_nanobot_task_status_skips_streaming_deltas_and_summarizes_planning() -> None:
    session = Session(
        session_id="session-4",
        state=SessionState.RUNNING,
        config_path="env_configs/openarm/openarm_motion_real.yaml",
    )
    session.event_history = [
        json.dumps(
            {
                "type": "model_streaming_start",
                "timestamp": "2026-04-09T10:03:00Z",
                "phase": "multi_turn_decision",
            }
        ),
        json.dumps(
            {
                "type": "model_streaming_delta",
                "timestamp": "2026-04-09T10:03:01Z",
                "content_delta": "ignored",
            }
        ),
    ]

    status = build_nanobot_task_status(session)

    assert len(status["recent_events"]) == 1
    assert status["recent_events"][0]["summary"] == "正在规划下一步"


def test_session_manager_can_reject_new_active_session() -> None:
    async def scenario() -> None:
        manager = SessionManager()
        session = await manager.create_session()
        assert session is not None
        session.state = SessionState.RUNNING

        replacement = await manager.create_session(replace_existing=False)

        assert replacement is None
        assert manager.get_active_session() is session
        assert len(manager._sessions) == 1

    asyncio.run(scenario())
