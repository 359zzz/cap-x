from __future__ import annotations

import copy
import json
from typing import Any

from capx.web.models import SessionState
from capx.web.session_manager import Session


def apply_initial_instruction_to_env_factory(
    env_factory: dict[str, Any],
    instruction: str | None,
) -> dict[str, Any]:
    """Inject the current nanobot task instruction into a cap-x env config."""
    if not instruction or not instruction.strip():
        return copy.deepcopy(env_factory)

    updated = copy.deepcopy(env_factory)
    cfg = updated.setdefault("cfg", {})
    clean_instruction = instruction.strip()

    task_only_prompt = cfg.get("task_only_prompt")
    if isinstance(task_only_prompt, str) and task_only_prompt.strip():
        cfg["task_only_prompt"] = (
            f"{task_only_prompt.rstrip()}\n\n"
            f"Latest nanobot instruction:\n{clean_instruction}"
        )
    else:
        cfg["task_only_prompt"] = clean_instruction

    prompt = cfg.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        cfg["prompt"] = (
            f"{prompt.rstrip()}\n\n"
            "# Nanobot Runtime Instruction\n"
            "The latest user instruction arriving from the nanobot outer shell is:\n"
            f"{clean_instruction}\n"
            "Prioritize this instruction for the current run, but keep all robot safety constraints."
        )

    multi_turn_prompt = cfg.get("multi_turn_prompt")
    if isinstance(multi_turn_prompt, str) and multi_turn_prompt.strip():
        cfg["multi_turn_prompt"] = (
            f"{multi_turn_prompt.rstrip()}\n\n"
            "If the user injects follow-up guidance through nanobot, treat it as the latest instruction "
            "and update the next code block accordingly."
        )

    return updated


def build_nanobot_task_status(session: Session, *, max_events: int = 10) -> dict[str, Any]:
    """Build a compact task summary suitable for nanobot/app polling."""
    parsed_events = _parse_event_history(session.event_history)
    recent_events = parsed_events[-max_events:]
    error_events = [event for event in parsed_events if event["type"] == "error"]
    return {
        "session_id": session.session_id,
        "state": session.state,
        "config_path": session.config_path,
        "current_block_index": session.current_block_index,
        "total_code_blocks": session.total_code_blocks,
        "num_regenerations": session.num_regenerations,
        "can_accept_injection": session.state == SessionState.AWAITING_USER_INPUT,
        "active": session.state in (
            SessionState.LOADING_CONFIG,
            SessionState.RUNNING,
            SessionState.AWAITING_USER_INPUT,
        ),
        "recent_events": recent_events,
        "last_error": error_events[-1]["summary"] if error_events else None,
    }


def _parse_event_history(history: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for raw in history:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        parsed.append(
            {
                "type": str(event.get("type", "unknown")),
                "timestamp": event.get("timestamp"),
                "summary": _event_summary(event),
            }
        )
    return parsed


def _event_summary(event: dict[str, Any]) -> str:
    event_type = event.get("type")
    if event_type == "state_update":
        return f"session state -> {event.get('state')}"
    if event_type == "environment_init":
        return f"environment {event.get('status')}: {_truncate(event.get('message') or event.get('description_content') or '')}"
    if event_type == "model_streaming_end":
        decision = event.get("decision", "unknown")
        block_count = len(event.get("code_blocks", []) or [])
        return f"model decision={decision}, code_blocks={block_count}"
    if event_type == "code_execution_start":
        return f"executing block {event.get('block_index')}"
    if event_type == "code_execution_result":
        return (
            f"block {event.get('block_index')} success={event.get('success')} "
            f"reward={event.get('reward')}"
        )
    if event_type == "execution_step":
        tool_name = event.get("tool_name") or "tool"
        return f"{tool_name}: {_truncate(event.get('text') or '')}"
    if event_type == "user_prompt_request":
        return _truncate(event.get("current_state_summary") or "awaiting user input")
    if event_type == "trial_complete":
        return (
            f"trial complete success={event.get('success')} "
            f"reward={event.get('total_reward')} task_completed={event.get('task_completed')}"
        )
    if event_type == "error":
        return _truncate(event.get("message") or "unknown error")
    if event_type == "visual_feedback":
        return _truncate(event.get("description") or "captured visual feedback")
    if event_type == "image_analysis":
        return f"{event.get('analysis_type')}: {_truncate(event.get('content') or '')}"
    return _truncate(json.dumps(event, ensure_ascii=False))


def _truncate(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"
