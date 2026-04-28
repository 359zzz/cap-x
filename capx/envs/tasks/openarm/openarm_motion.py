from __future__ import annotations

import contextlib
import io
import sys
import traceback
from typing import Any

from capx.envs.tasks.base import CodeExecutionEnvBase, Tee

PROMPT = """
You are controlling a real OpenArm dual-arm robot through safe OpenArm APIs.

Rules:
- If the instruction contains explicit anchor names such as `safe_standby`, `left_neutral_ready`, or recorded names like `tomato_dual_grasp_sync`, treat the task as an exact motion script.
- For exact anchor scripts, execute the named anchors in the requested order with `move_to_named_pose(...)` and do not replace them with perception-driven behaviors.
- If the instruction says to first confirm a visual target and then run an exact anchor script, perform one visual confirmation step first and, if the target is present, continue immediately into the requested anchor sequence in the same code block. Do not stop after a successful detection.
- If the instruction says to continue even when the gripper cannot fully close around a grasped object, call `move_to_named_pose(..., ignore_gripper_when_closing=True)` for those anchor moves so the close is still attempted, but the script may continue once the other joints reach target even if the gripper alone cannot finish the close.
- Do not call `describe_scene(...)`, `detect_target(...)`, `get_target_pose(...)`, `align_to_target(...)`, or `approach_target(...)` unless the user explicitly asks to inspect, detect, search, align, or look at something in the scene.
- Prefer `execute_motion_primitive(...)` and `execute_motion_combo(...)`.
- Use `move_to_named_pose(...)` to reach known anchors like `home` or `safe_standby`.
- Use explicit joint control only when the motion catalog is insufficient.
- The gripper is directly controllable; use tactile feedback when helpful.
- Use `describe_scene(...)`, `detect_target(...)`, and `get_target_pose(...)` for visual decisions.
- If vision returns an image, description, or detections, use that evidence instead of guessing.
- Only one active robot task is allowed at a time.
- Do not assume unavailable simulation features.

Write ONLY executable Python code (no code fences). Import numpy if needed.
"""


class OpenArmMotionCodeEnv(CodeExecutionEnvBase):
    prompt = PROMPT

    def _init_exec_globals(self) -> None:
        g: dict[str, Any] = {
            "__name__": "__main__",
            "APIS": self._apis,
            "INPUTS": {},
            "RESULT": None,
        }
        for api in self._apis.values():
            for fn_name, fn in api.functions().items():
                g[fn_name] = fn
        self._exec_globals = g

    def _exec_user_code(self, code: str) -> dict[str, Any]:
        obs = self._get_observation()
        self._exec_globals["obs"] = obs
        self._exec_globals["APIS"] = self._apis
        for api in self._apis.values():
            for fn_name, fn in api.functions().items():
                self._exec_globals[fn_name] = fn

        stdout_buffer = io.StringIO()
        tee_out = Tee(sys.stdout, stdout_buffer)
        stderr_buffer = io.StringIO()
        tee_err = Tee(sys.stderr, stderr_buffer)
        ok = True
        try:
            with (
                contextlib.redirect_stdout(tee_out),
                contextlib.redirect_stderr(tee_err),
            ):
                exec(code, self._exec_globals, self._exec_globals)
        except BaseException:
            ok = False
            traceback.print_exc(file=tee_err)

        return {
            "ok": ok,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "result": self._exec_globals.get("RESULT"),
        }


__all__ = ["OpenArmMotionCodeEnv"]
