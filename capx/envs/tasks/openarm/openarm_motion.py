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
- Prefer `execute_motion_primitive(...)` and `execute_motion_combo(...)`.
- Use `move_to_named_pose(...)` to reach known anchors like `home` or `safe_standby`.
- Use explicit joint control only when the motion catalog is insufficient.
- Only one active robot task is allowed at a time.
- The gripper is directly controllable; use tactile feedback when helpful.
- Do not assume unavailable perception or simulation features.

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
