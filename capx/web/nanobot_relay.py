from __future__ import annotations

import copy
import json
import re
from typing import Any

from capx.integrations.openarm.catalog import DEFAULT_ANCHORS, DEFAULT_COMBOS, DEFAULT_PRIMITIVES
from capx.web.models import SessionState
from capx.web.session_manager import Session

_ANCHOR_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)(?![A-Za-z0-9_])"
)
_KNOWN_ANCHORS = set(DEFAULT_ANCHORS)
_NON_ANCHOR_SNAKE_CASE = set(DEFAULT_PRIMITIVES) | set(DEFAULT_COMBOS)
_ANCHOR_TOKEN_BLACKLIST = {
    "move_to_named_pose",
    "execute_motion_combo",
    "execute_motion_primitive",
    "detect_target",
    "align_to_target",
    "get_target_pose",
    "ignore_gripper",
}
_SKIPPED_EVENT_TYPES = {"model_streaming_delta"}


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
    hint_lines = _build_instruction_hints(clean_instruction)

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
    elif hint_lines:
        cfg["prompt"] = ""

    if hint_lines:
        hint_block = "\n".join(f"- {line}" for line in hint_lines)
        cfg["prompt"] = (
            f"{cfg.get('prompt', '').rstrip()}\n\n"
            "# Nanobot Instruction Hints\n"
            f"{hint_block}"
        ).strip()

    multi_turn_prompt = cfg.get("multi_turn_prompt")
    if isinstance(multi_turn_prompt, str) and multi_turn_prompt.strip():
        cfg["multi_turn_prompt"] = (
            f"{multi_turn_prompt.rstrip()}\n\n"
            "If the user injects follow-up guidance through nanobot, treat it as the latest instruction "
            "and update the next code block accordingly.\n"
            "If the latest instruction includes explicit anchor names, regenerate a pure anchor-motion script "
            "in that exact order and avoid perception tools unless the user explicitly asks for visual inspection."
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
        event_type = str(event.get("type", "unknown"))
        if event_type in _SKIPPED_EVENT_TYPES:
            continue
        parsed.append(
            {
                "type": event_type,
                "timestamp": event.get("timestamp"),
                "summary": _event_summary(event),
                "media": _event_media(event),
            }
        )
    return parsed


def _event_summary(event: dict[str, Any]) -> str:
    event_type = event.get("type")
    if event_type == "state_update":
        return f"state -> {event.get('state')}"
    if event_type == "environment_init":
        detail = event.get("message") or event.get("description_content") or ""
        return f"environment {event.get('status')}: {_truncate(detail)}"
    if event_type == "model_thinking":
        phase = event.get("phase") or "unknown"
        if phase == "multi_turn_decision":
            return "model is planning the next step"
        return "model is generating the initial plan"
    if event_type == "model_streaming_start":
        phase = event.get("phase") or "unknown"
        if phase == "multi_turn_decision":
            return "model is planning the next step"
        return "model is generating the initial plan"
    if event_type == "model_streaming_end":
        decision = event.get("decision", "unknown")
        block_count = len(event.get("code_blocks", []) or [])
        noun = "block" if block_count == 1 else "blocks"
        return f"model chose {decision} and produced {block_count} code {noun}"
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


def _event_media(event: dict[str, Any]) -> list[str]:
    event_type = event.get("type")
    if event_type in {"visual_feedback", "image_analysis"}:
        image_base64 = event.get("image_base64")
        images = event.get("images")
        media = [image_base64] if isinstance(image_base64, str) and image_base64 else []
        if isinstance(images, list):
            media.extend(item for item in images if isinstance(item, str) and item)
        return _dedupe_media(media)
    if event_type == "execution_step":
        images = event.get("images")
        if isinstance(images, list):
            return _dedupe_media([item for item in images if isinstance(item, str) and item])
    return []


def _dedupe_media(media: list[str]) -> list[str]:
    result: list[str] = []
    for item in media:
        if item and item not in result:
            result.append(item)
    return result


def _truncate(text: str, limit: int = 180) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _build_instruction_hints(instruction: str) -> list[str]:
    anchor_names = _extract_anchor_names(instruction)
    wants_relaxed_gripper = _instruction_mentions_relaxed_gripper(instruction)
    hints: list[str] = []
    if anchor_names:
        anchors = ", ".join(anchor_names)
        hints.append(f"Explicit anchor names detected: {anchors}.")
        hints.append(
            "Execute those anchors exactly in the order requested with move_to_named_pose(...)."
        )
        hints.append(
            "Do not call describe_scene, detect_target, get_target_pose, align_to_target, or approach_target unless the user explicitly asks for vision."
        )
    if anchor_names and wants_relaxed_gripper:
        hints.append(
            "For those anchor moves, preserve the current gripper state with move_to_named_pose(..., ignore_gripper=True)."
        )
    return hints


def _extract_anchor_names(instruction: str) -> list[str]:
    tokens: list[str] = []
    for match in _ANCHOR_NAME_RE.findall(instruction):
        token = str(match).strip()
        if token in _ANCHOR_TOKEN_BLACKLIST:
            continue
        if token in _NON_ANCHOR_SNAKE_CASE:
            continue
        if token not in _KNOWN_ANCHORS and token.count("_") < 2:
            continue
        if token not in tokens:
            tokens.append(token)
    lowered = instruction.lower()
    if "safe standby" in lowered and "safe_standby" not in tokens:
        tokens.append("safe_standby")
    return tokens


def _instruction_mentions_relaxed_gripper(instruction: str) -> bool:
    lowered = instruction.lower()
    keywords = (
        "ignore_gripper",
        "gripper",
        "holding",
        "grasped",
        "continue anyway",
        "continue to the next step",
        "cannot fully reach",
        "can't fully reach",
        "can't continue",
        "夹爪",
        "夹住",
        "继续下一步",
        "不能继续运动",
        "无法完全到位",
        "到不了位",
    )
    return any(keyword in lowered for keyword in keywords)
