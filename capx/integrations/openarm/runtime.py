from __future__ import annotations

import contextlib
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .catalog import MAGNITUDE_TO_GRIPPER_FRACTION
from .driver import (
    BiOpenArmFollower,
    BiOpenArmFollowerConfig,
    OpenArmFollowerConfig,
)
from .perception_adapter import OpenClawPerceptionConfig, OpenClawServiceAdapter


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ArmConnectionConfig:
    port: str = ""
    side: str = "left"
    can_interface: str = "socketcan"
    use_can_fd: bool = True
    can_bitrate: int = 1_000_000
    can_data_bitrate: int = 5_000_000
    max_relative_target: float = 8.0
    cameras: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenArmRuntimeConfig:
    robot_id: str = os.getenv("CAPX_OPENARM_ROBOT_ID", "capx_openarm")
    calibration_dir: Path | None = (
        Path(os.environ["CAPX_OPENARM_CALIBRATION_DIR"])
        if os.getenv("CAPX_OPENARM_CALIBRATION_DIR")
        else None
    )
    auto_calibrate: bool = _env_flag("CAPX_OPENARM_AUTO_CALIBRATE", False)
    default_speed: str = os.getenv("CAPX_OPENARM_DEFAULT_SPEED", "slow")
    move_tolerance_deg: float = float(os.getenv("CAPX_OPENARM_MOVE_TOLERANCE_DEG", "3.0"))
    command_timeout_s: float = float(os.getenv("CAPX_OPENARM_COMMAND_TIMEOUT_S", "6.0"))
    step_sleep_s: float = float(os.getenv("CAPX_OPENARM_STEP_SLEEP_S", "0.05"))
    max_step_delta_deg: float = float(os.getenv("CAPX_OPENARM_MAX_STEP_DELTA_DEG", "8.0"))
    joint_limit_margin_deg: float = float(os.getenv("CAPX_OPENARM_JOINT_MARGIN_DEG", "5.0"))
    left_arm: ArmConnectionConfig = field(
        default_factory=lambda: ArmConnectionConfig(
            port=os.getenv("CAPX_OPENARM_LEFT_PORT", ""),
            side="left",
            can_interface=os.getenv("CAPX_OPENARM_LEFT_CAN_INTERFACE", "socketcan"),
        )
    )
    right_arm: ArmConnectionConfig = field(
        default_factory=lambda: ArmConnectionConfig(
            port=os.getenv("CAPX_OPENARM_RIGHT_PORT", ""),
            side="right",
            can_interface=os.getenv("CAPX_OPENARM_RIGHT_CAN_INTERFACE", "socketcan"),
        )
    )
    perception: OpenClawPerceptionConfig = field(
        default_factory=lambda: OpenClawPerceptionConfig(
            base_url=os.getenv("CAPX_OPENARM_PERCEPTION_BASE_URL", "http://127.0.0.1:8000"),
            timeout_s=float(os.getenv("CAPX_OPENARM_PERCEPTION_TIMEOUT_S", "3.0")),
            enabled=_env_flag("CAPX_OPENARM_PERCEPTION_ENABLED", True),
        )
    )


class InRepoBiOpenArmDriver:
    def __init__(self, config: OpenArmRuntimeConfig) -> None:
        self.config = config
        self._robot: Any | None = None

    @property
    def is_connected(self) -> bool:
        return bool(self._robot and self._robot.is_connected)

    @property
    def is_calibrated(self) -> bool:
        return bool(self._robot and self._robot.is_calibrated)

    def connect(self, *, calibrate: bool) -> None:
        self._ensure_robot()
        assert self._robot is not None
        self._robot.connect(calibrate=calibrate)

    def disconnect(self) -> None:
        if self._robot is not None and self._robot.is_connected:
            self._robot.disconnect()

    def get_observation(self) -> dict[str, Any]:
        self._require_robot()
        assert self._robot is not None
        return dict(self._robot.get_observation())

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        self._require_robot()
        assert self._robot is not None
        return dict(self._robot.send_action(action))

    def _require_robot(self) -> None:
        if self._robot is None:
            raise RuntimeError("OpenArm driver is not connected. Call connect() first.")

    def _ensure_robot(self) -> None:
        if self._robot is not None:
            return
        left_cfg = OpenArmFollowerConfig(
            id=f"{self.config.robot_id}_left",
            calibration_dir=self.config.calibration_dir,
            port=self.config.left_arm.port,
            side="left",
            can_interface=self.config.left_arm.can_interface,
            use_can_fd=self.config.left_arm.use_can_fd,
            can_bitrate=self.config.left_arm.can_bitrate,
            can_data_bitrate=self.config.left_arm.can_data_bitrate,
            max_relative_target=self.config.left_arm.max_relative_target,
            cameras=self.config.left_arm.cameras,
        )
        right_cfg = OpenArmFollowerConfig(
            id=f"{self.config.robot_id}_right",
            calibration_dir=self.config.calibration_dir,
            port=self.config.right_arm.port,
            side="right",
            can_interface=self.config.right_arm.can_interface,
            use_can_fd=self.config.right_arm.use_can_fd,
            can_bitrate=self.config.right_arm.can_bitrate,
            can_data_bitrate=self.config.right_arm.can_data_bitrate,
            max_relative_target=self.config.right_arm.max_relative_target,
            cameras=self.config.right_arm.cameras,
        )
        robot_cfg = BiOpenArmFollowerConfig(
            id=self.config.robot_id,
            calibration_dir=self.config.calibration_dir,
            left_arm_config=left_cfg,
            right_arm_config=right_cfg,
        )
        self._robot = BiOpenArmFollower(robot_cfg)

class OpenArmRuntime:
    def __init__(
        self,
        config: OpenArmRuntimeConfig | None = None,
        *,
        driver: InRepoBiOpenArmDriver | None = None,
        perception: OpenClawServiceAdapter | None = None,
    ) -> None:
        self.config = config or OpenArmRuntimeConfig()
        self.driver = driver or InRepoBiOpenArmDriver(self.config)
        self.perception = perception or OpenClawServiceAdapter(self.config.perception)
        self._task_lock = threading.RLock()
        self._task_state = "IDLE"
        self._task_depth = 0
        self._latest_detection: dict[str, Any] | None = None
        self._latest_tactile: dict[str, Any] | None = None
        self._last_observation: dict[str, Any] = {}

    @property
    def task_state(self) -> str:
        return self._task_state

    @contextlib.contextmanager
    def active_task(self, name: str):
        del name
        if not self._task_lock.acquire(blocking=False):
            raise RuntimeError("Another OpenArm task is already active.")
        self._task_depth += 1
        self._task_state = "RUNNING"
        try:
            yield
        finally:
            self._task_depth = max(0, self._task_depth - 1)
            if self._task_depth == 0:
                self._task_state = "IDLE"
            self._task_lock.release()

    def connect(self) -> None:
        if not self.driver.is_connected:
            self.driver.connect(calibrate=self.config.auto_calibrate)

    def disconnect(self) -> None:
        self.driver.disconnect()
        self._task_depth = 0
        self._task_state = "IDLE"

    def ensure_connected(self) -> None:
        if not self.driver.is_connected:
            self.connect()

    def get_robot_state(self) -> dict[str, Any]:
        obs = self.get_observation()
        return {
            "connected": self.driver.is_connected,
            "calibrated": self.driver.is_calibrated,
            "task_state": self._task_state,
            "left_joint_positions": obs.get("left_arm", {}).get("joint_pos", {}),
            "right_joint_positions": obs.get("right_arm", {}).get("joint_pos", {}),
            "latest_tactile": self._latest_tactile,
            "latest_detection": self._latest_detection,
        }

    def get_observation(self) -> dict[str, Any]:
        self.ensure_connected()
        flat_obs = self.driver.get_observation()
        structured = self._structure_observation(flat_obs)
        structured["latest_detection"] = self._latest_detection
        structured["latest_tactile"] = self._latest_tactile
        structured["task_state"] = self._task_state
        self._last_observation = structured
        return structured

    def get_arm_joint_positions(self, arm: str) -> dict[str, float]:
        arm_key = f"{arm}_arm"
        obs = self.get_observation()
        joints = obs.get(arm_key, {}).get("joint_pos", {})
        return {str(k): float(v) for k, v in joints.items()}

    def move_arm_joints_blocking(
        self,
        arm: str,
        target_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
    ) -> dict[str, float]:
        del speed
        self.ensure_connected()
        timeout_s = timeout_s or self.config.command_timeout_s
        current = self.get_arm_joint_positions(arm)
        steps = self._compute_step_count(current, target_joints)
        arm_prefix = f"{arm}_"
        for step_index in range(1, steps + 1):
            alpha = step_index / steps
            step_targets = {
                joint: float(current.get(joint, 0.0) + alpha * (target - current.get(joint, 0.0)))
                for joint, target in target_joints.items()
            }
            action = {
                f"{arm_prefix}{joint}.pos": float(
                    step_targets[joint]
                )
                for joint in target_joints
            }
            self.driver.send_action(action)
            self._wait_until_arm_close(arm, step_targets, timeout_s=min(timeout_s, 1.0))
            time.sleep(self.config.step_sleep_s)
        return self.get_arm_joint_positions(arm)

    def move_both_arms_blocking(
        self,
        left_joints: dict[str, float],
        right_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
    ) -> dict[str, dict[str, float]]:
        del speed
        self.ensure_connected()
        timeout_s = timeout_s or self.config.command_timeout_s
        left_current = self.get_arm_joint_positions("left")
        right_current = self.get_arm_joint_positions("right")
        steps = max(
            self._compute_step_count(left_current, left_joints),
            self._compute_step_count(right_current, right_joints),
        )
        for step_index in range(1, steps + 1):
            alpha = step_index / steps
            left_step_targets = {
                joint: float(
                    left_current.get(joint, 0.0) + alpha * (target - left_current.get(joint, 0.0))
                )
                for joint, target in left_joints.items()
            }
            right_step_targets = {
                joint: float(
                    right_current.get(joint, 0.0)
                    + alpha * (target - right_current.get(joint, 0.0))
                )
                for joint, target in right_joints.items()
            }
            action: dict[str, float] = {}
            action.update(
                {
                    f"left_{joint}.pos": float(left_step_targets[joint]) for joint in left_joints
                }
            )
            action.update(
                {
                    f"right_{joint}.pos": float(right_step_targets[joint]) for joint in right_joints
                }
            )
            self.driver.send_action(action)
            if left_step_targets:
                self._wait_until_arm_close("left", left_step_targets, timeout_s=min(timeout_s, 1.0))
            if right_step_targets:
                self._wait_until_arm_close("right", right_step_targets, timeout_s=min(timeout_s, 1.0))
            time.sleep(self.config.step_sleep_s)
        return {
            "left": self.get_arm_joint_positions("left"),
            "right": self.get_arm_joint_positions("right"),
        }

    def set_gripper_fraction(
        self,
        arm: str,
        fraction: float,
        *,
        blocking: bool = True,
    ) -> float:
        fraction = float(np.clip(fraction, 0.0, 1.0))
        gripper_pos = -65.0 + 65.0 * fraction
        self.move_arm_joints_blocking(arm, {"gripper": gripper_pos}, speed="slow")
        if blocking:
            time.sleep(self.config.step_sleep_s)
        return gripper_pos

    def set_gripper_by_magnitude(
        self,
        arm: str,
        primitive: str,
        magnitude: str,
    ) -> float:
        fraction = MAGNITUDE_TO_GRIPPER_FRACTION.get(magnitude, 1.0)
        if primitive == "close_gripper":
            fraction = 1.0 - fraction
        return self.set_gripper_fraction(arm, fraction)

    def hold_current_position(self) -> None:
        left = self.get_arm_joint_positions("left")
        right = self.get_arm_joint_positions("right")
        self.move_both_arms_blocking(left, right, speed="slow", timeout_s=1.0)

    def stop_motion(self) -> None:
        self._task_state = "STOPPING"
        self.hold_current_position()
        self._task_state = "IDLE"

    def read_tactile(self) -> dict[str, Any]:
        self._latest_tactile = self.perception.tactile_read()
        return dict(self._latest_tactile)

    def get_tactile_health(self) -> dict[str, Any]:
        return self.perception.tactile_health()

    def detect_target(self, target_name: str | None, *, top_k: int = 3) -> dict[str, Any]:
        self._latest_detection = self.perception.detect_once(target_name, top_k=top_k)
        return dict(self._latest_detection)

    def _compute_step_count(
        self,
        current: dict[str, float],
        target: dict[str, float],
    ) -> int:
        max_delta = 0.0
        for joint, target_value in target.items():
            max_delta = max(max_delta, abs(target_value - current.get(joint, target_value)))
        step_count = int(np.ceil(max_delta / max(self.config.max_step_delta_deg, 1.0)))
        return max(1, step_count)

    def _wait_until_arm_close(
        self,
        arm: str,
        target_joints: dict[str, float],
        *,
        timeout_s: float,
    ) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            current = self.get_arm_joint_positions(arm)
            errors = [
                abs(current.get(joint, target) - target)
                for joint, target in target_joints.items()
            ]
            if not errors or max(errors) <= self.config.move_tolerance_deg:
                return
            time.sleep(self.config.step_sleep_s)
        raise TimeoutError(f"Timed out waiting for {arm} joints to reach target {target_joints}")

    def _structure_observation(self, flat_obs: dict[str, Any]) -> dict[str, Any]:
        structured: dict[str, Any] = {
            "left_arm": {"joint_pos": {}, "joint_vel": {}, "joint_torque": {}},
            "right_arm": {"joint_pos": {}, "joint_vel": {}, "joint_torque": {}},
            "cameras": {},
        }
        for key, value in flat_obs.items():
            if key.startswith("left_") or key.startswith("right_"):
                prefix, suffix = key.split("_", 1)
                arm_key = f"{prefix}_arm"
                if suffix.endswith(".pos"):
                    joint_name = suffix[:-4]
                    structured[arm_key]["joint_pos"][joint_name] = float(value)
                elif suffix.endswith(".vel"):
                    joint_name = suffix[:-4]
                    structured[arm_key]["joint_vel"][joint_name] = float(value)
                elif suffix.endswith(".torque"):
                    joint_name = suffix[:-7]
                    structured[arm_key]["joint_torque"][joint_name] = float(value)
                else:
                    structured["cameras"][key] = value
            else:
                structured["cameras"][key] = value
        return structured
