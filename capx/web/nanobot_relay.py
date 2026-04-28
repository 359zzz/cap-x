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
_SESSION_STATE_LABELS = {
    "idle": "空闲",
    "loading_config": "载入配置",
    "running": "执行中",
    "awaiting_user_input": "等待指令",
    "complete": "已完成",
    "error": "异常",
}


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
        return f"状态切换为{_format_state_label(event.get('state'))}"
    if event_type == "environment_init":
        status = str(event.get("status") or "")
        detail = event.get("message") or event.get("description_content") or ""
        if status in {"starting", "building_description"}:
            return "环境准备中"
        if status in {"complete", "description_complete"}:
            return "环境已就绪"
        return f"环境  {_truncate(detail)}"
    if event_type == "model_thinking":
        phase = event.get("phase") or "unknown"
        if phase == "multi_turn_decision":
            return "正在规划下一步"
        return "正在生成初始动作"
    if event_type == "model_streaming_start":
        phase = event.get("phase") or "unknown"
        if phase == "multi_turn_decision":
            return "正在规划下一步"
        return "正在生成初始动作"
    if event_type == "model_streaming_end":
        decision = event.get("decision", "unknown")
        block_count = len(event.get("code_blocks", []) or [])
        if decision == "finish":
            return "规划结束"
        if decision == "regenerate":
            return f"已重规划，生成 {block_count} 段动作"
        return f"已生成 {block_count} 段动作"
    if event_type == "code_execution_start":
        return f"执行第 {_block_index_label(event.get('block_index'))} 段动作"
    if event_type == "code_execution_result":
        success = bool(event.get("success"))
        return f"第 {_block_index_label(event.get('block_index'))} 段{'完成' if success else '失败'}"
    if event_type == "execution_step":
        tool_name = event.get("tool_name") or "tool"
        return _format_execution_step_summary(str(tool_name), str(event.get("text") or ""))
    if event_type == "user_prompt_request":
        return "等待下一条指令"
    if event_type == "trial_complete":
        return "任务已完成" if event.get("success") else "任务已结束"
    if event_type == "error":
        return f"异常：{_truncate(event.get('message') or 'unknown error')}"
    if event_type == "visual_feedback":
        return _truncate(event.get("description") or "已采集视觉反馈")
    if event_type == "image_analysis":
        return f"视觉分析：{_truncate(event.get('content') or '')}"
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


def _format_state_label(value: object) -> str:
    key = str(value or "").strip().lower()
    return _SESSION_STATE_LABELS.get(key, key or "未知")


def _block_index_label(value: object) -> int:
    if isinstance(value, int):
        return value + 1
    try:
        return int(value) + 1
    except (TypeError, ValueError):
        return 1


def _format_execution_step_summary(tool_name: str, text: str) -> str:
    clean = _truncate(text)
    if tool_name == "move_to_named_pose":
        match = re.search(r"anchor '([^']+)'", text)
        if match:
            return f"移动到 {match.group(1)}"
        return "执行 anchor 动作"
    if tool_name == "detect_target":
        match = re.search(r"target '([^']+)'", text)
        if match:
            return f"识别 {match.group(1)}"
        return "识别目标"
    if tool_name == "align_to_target":
        match = re.search(r"Aligning ([a-z]+) arm to target '([^']+)'", text)
        if match:
            return f"{match.group(1)} 臂对齐 {match.group(2)}"
        return "执行目标对齐"
    if tool_name == "execute_motion_combo":
        return f"执行组合动作  {clean}"
    if tool_name == "execute_motion_primitive":
        return f"执行基础动作  {clean}"
    if tool_name == "record_anchor":
        return f"录制锚点  {clean}"
    return clean
