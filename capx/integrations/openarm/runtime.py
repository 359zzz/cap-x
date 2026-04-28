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


_SPEED_TO_DEG_PER_S = {
    "slow": 10.0,
    "normal": 18.0,
    "medium": 22.0,
    "fast": 38.0,
}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ArmConnectionConfig:
    port: str = ""
    side: str = "left"
    zero_on_connect: bool = False
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
    interpolation_profile: str = os.getenv("CAPX_OPENARM_INTERPOLATION_PROFILE", "quintic")
    min_trajectory_duration_s: float = float(
        os.getenv("CAPX_OPENARM_MIN_TRAJECTORY_DURATION_S", "0.25")
    )
    max_trajectory_duration_s: float = float(
        os.getenv("CAPX_OPENARM_MAX_TRAJECTORY_DURATION_S", "4.0")
    )
    slow_velocity_deg_s: float = float(os.getenv("CAPX_OPENARM_SLOW_VELOCITY_DEG_S", "10.0"))
    normal_velocity_deg_s: float = float(os.getenv("CAPX_OPENARM_NORMAL_VELOCITY_DEG_S", "18.0"))
    medium_velocity_deg_s: float = float(os.getenv("CAPX_OPENARM_MEDIUM_VELOCITY_DEG_S", "22.0"))
    fast_velocity_deg_s: float = float(os.getenv("CAPX_OPENARM_FAST_VELOCITY_DEG_S", "38.0"))
    joint_limit_margin_deg: float = float(os.getenv("CAPX_OPENARM_JOINT_MARGIN_DEG", "5.0"))
    left_arm: ArmConnectionConfig = field(
        default_factory=lambda: ArmConnectionConfig(
            port=os.getenv("CAPX_OPENARM_LEFT_PORT", ""),
            side="left",
            zero_on_connect=_env_flag("CAPX_OPENARM_LEFT_ZERO_ON_CONNECT", False),
            can_interface=os.getenv("CAPX_OPENARM_LEFT_CAN_INTERFACE", "socketcan"),
        )
    )
    right_arm: ArmConnectionConfig = field(
        default_factory=lambda: ArmConnectionConfig(
            port=os.getenv("CAPX_OPENARM_RIGHT_PORT", ""),
            side="right",
            zero_on_connect=_env_flag("CAPX_OPENARM_RIGHT_ZERO_ON_CONNECT", False),
            can_interface=os.getenv("CAPX_OPENARM_RIGHT_CAN_INTERFACE", "socketcan"),
        )
    )
    perception: OpenClawPerceptionConfig = field(
        default_factory=lambda: OpenClawPerceptionConfig(
            base_url=os.getenv("CAPX_OPENARM_PERCEPTION_BASE_URL", "http://127.0.0.1:8000"),
            timeout_s=float(os.getenv("CAPX_OPENARM_PERCEPTION_TIMEOUT_S", "3.0")),
            enabled=_env_flag("CAPX_OPENARM_PERCEPTION_ENABLED", True),
            health_path=os.getenv("CAPX_OPENARM_PERCEPTION_HEALTH_PATH", "/health"),
            tactile_health_path=os.getenv("CAPX_OPENARM_TACTILE_HEALTH_PATH", "/tactile/health"),
            tactile_read_path=os.getenv("CAPX_OPENARM_TACTILE_READ_PATH", "/tactile/read"),
            detect_path=os.getenv("CAPX_OPENARM_DETECT_PATH", "/detect_once"),
            describe_path=os.getenv("CAPX_OPENARM_DESCRIBE_PATH", "/describe_once"),
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
            zero_on_connect=self.config.left_arm.zero_on_connect,
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
            zero_on_connect=self.config.right_arm.zero_on_connect,
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
        obs = self.get_observation()
        return self._extract_arm_joint_positions(obs, arm)

    def move_arm_joints_blocking(
        self,
        arm: str,
        target_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
        tolerate_timeout_joints: set[str] | None = None,
    ) -> dict[str, float]:
        self.ensure_connected()
        timeout_s = timeout_s or self.config.command_timeout_s
        current = self.get_arm_joint_positions(arm)
        if not target_joints:
            return current

        target_joints = {joint: float(value) for joint, value in target_joints.items()}
        if self._compute_max_joint_delta(current, target_joints) <= 1e-6:
            return current

        arm_prefix = f"{arm}_"
        waypoints = self._build_interpolated_waypoints(
            current=current,
            target=target_joints,
            speed=speed,
            timeout_s=timeout_s,
        )
        started = time.monotonic()
        wait_targets = dict(target_joints)
        for step_index, step_targets in enumerate(waypoints):
            action = {
                f"{arm_prefix}{joint}.pos": float(step_targets[joint]) for joint in target_joints
            }
            sent_action = self.driver.send_action(action)
            wait_targets = self._extract_sent_targets(sent_action, arm)
            if step_index < len(waypoints) - 1:
                time.sleep(self._step_interval_s())
        remaining_timeout = max(self._step_interval_s(), timeout_s - (time.monotonic() - started))
        self._wait_until_arm_close(
            arm,
            wait_targets,
            timeout_s=remaining_timeout,
            tolerate_timeout_joints=tolerate_timeout_joints,
        )
        return self.get_arm_joint_positions(arm)

    def move_both_arms_blocking(
        self,
        left_joints: dict[str, float],
        right_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
        left_tolerate_timeout_joints: set[str] | None = None,
        right_tolerate_timeout_joints: set[str] | None = None,
    ) -> dict[str, dict[str, float]]:
        self.ensure_connected()
        timeout_s = timeout_s or self.config.command_timeout_s
        left_current = self.get_arm_joint_positions("left")
        right_current = self.get_arm_joint_positions("right")
        left_joints = {joint: float(value) for joint, value in left_joints.items()}
        right_joints = {joint: float(value) for joint, value in right_joints.items()}
        combined_max_delta = max(
            self._compute_max_joint_delta(left_current, left_joints),
            self._compute_max_joint_delta(right_current, right_joints),
        )
        if combined_max_delta <= 1e-6:
            return {"left": left_current, "right": right_current}

        steps = self._compute_trajectory_step_count(
            current_sets=(left_current, right_current),
            target_sets=(left_joints, right_joints),
            speed=speed,
            timeout_s=timeout_s,
        )
        started = time.monotonic()
        left_wait_targets = dict(left_joints)
        right_wait_targets = dict(right_joints)
        for step_index in range(1, steps + 1):
            alpha = self._interpolation_alpha(step_index / steps)
            left_step_targets = self._interpolate_joint_targets(left_current, left_joints, alpha)
            right_step_targets = self._interpolate_joint_targets(right_current, right_joints, alpha)
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
            sent_action = self.driver.send_action(action)
            left_wait_targets = self._extract_sent_targets(sent_action, "left")
            right_wait_targets = self._extract_sent_targets(sent_action, "right")
            if step_index < steps:
                time.sleep(self._step_interval_s())
        remaining_timeout = max(self._step_interval_s(), timeout_s - (time.monotonic() - started))
        self._wait_until_both_arms_close(
            left_target_joints=left_wait_targets,
            right_target_joints=right_wait_targets,
            timeout_s=remaining_timeout,
            left_tolerate_timeout_joints=left_tolerate_timeout_joints,
            right_tolerate_timeout_joints=right_tolerate_timeout_joints,
        )
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
        # OpenArm grippers are zeroed in the mechanically closed posture, so
        # larger opening commands move toward the negative limit.
        gripper_pos = -65.0 * fraction
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

    def describe_scene(self, prompt: str | None = None) -> dict[str, Any]:
        self._latest_detection = self.perception.describe_once(prompt)
        return dict(self._latest_detection)

    def _compute_step_count(
        self,
        current: dict[str, float],
        target: dict[str, float],
    ) -> int:
        max_delta = self._compute_max_joint_delta(current, target)
        step_count = int(np.ceil(max_delta / max(self.config.max_step_delta_deg, 1.0)))
        return max(1, step_count)

    def _compute_max_joint_delta(
        self,
        current: dict[str, float],
        target: dict[str, float],
    ) -> float:
        max_delta = 0.0
        for joint, target_value in target.items():
            max_delta = max(max_delta, abs(float(target_value) - float(current.get(joint, target_value))))
        return max_delta

    def _step_interval_s(self) -> float:
        return max(self.config.step_sleep_s, 0.001)

    def _resolve_speed_deg_per_s(self, speed: str) -> float:
        normalized = speed.strip().lower()
        default_speed = self.config.default_speed.strip().lower()
        table = {
            **_SPEED_TO_DEG_PER_S,
            "slow": self.config.slow_velocity_deg_s,
            "normal": self.config.normal_velocity_deg_s,
            "medium": self.config.medium_velocity_deg_s,
            "fast": self.config.fast_velocity_deg_s,
        }
        return float(table.get(normalized, table.get(default_speed, table["slow"])))

    def _resolve_trajectory_duration_s(
        self,
        max_delta_deg: float,
        *,
        speed: str,
        timeout_s: float,
    ) -> float:
        if max_delta_deg <= 1e-6:
            return self._step_interval_s()
        speed_deg_s = max(self._resolve_speed_deg_per_s(speed), 1.0)
        duration = max_delta_deg / speed_deg_s
        duration = max(duration, self.config.min_trajectory_duration_s)
        duration = min(duration, self.config.max_trajectory_duration_s)
        settle_budget = min(1.0, max(self._step_interval_s(), timeout_s * 0.2))
        trajectory_budget = max(self._step_interval_s(), timeout_s - settle_budget)
        return min(duration, trajectory_budget)

    def _compute_trajectory_step_count(
        self,
        *,
        current_sets: tuple[dict[str, float], ...],
        target_sets: tuple[dict[str, float], ...],
        speed: str,
        timeout_s: float,
    ) -> int:
        max_delta = max(
            self._compute_max_joint_delta(current, target)
            for current, target in zip(current_sets, target_sets, strict=True)
        )
        min_steps = max(
            self._compute_step_count(current, target)
            for current, target in zip(current_sets, target_sets, strict=True)
        )
        duration_s = self._resolve_trajectory_duration_s(max_delta, speed=speed, timeout_s=timeout_s)
        timed_steps = int(np.ceil(duration_s / self._step_interval_s()))
        return max(1, min_steps, timed_steps)

    def _interpolation_alpha(self, ratio: float) -> float:
        ratio = float(np.clip(ratio, 0.0, 1.0))
        if self.config.interpolation_profile.strip().lower() == "linear":
            return ratio
        return 10.0 * ratio**3 - 15.0 * ratio**4 + 6.0 * ratio**5

    def _interpolate_joint_targets(
        self,
        current: dict[str, float],
        target: dict[str, float],
        alpha: float,
    ) -> dict[str, float]:
        return {
            joint: float(current.get(joint, 0.0) + alpha * (target_value - current.get(joint, 0.0)))
            for joint, target_value in target.items()
        }

    def _build_interpolated_waypoints(
        self,
        *,
        current: dict[str, float],
        target: dict[str, float],
        speed: str,
        timeout_s: float,
    ) -> list[dict[str, float]]:
        steps = self._compute_trajectory_step_count(
            current_sets=(current,),
            target_sets=(target,),
            speed=speed,
            timeout_s=timeout_s,
        )
        return [
            self._interpolate_joint_targets(current, target, self._interpolation_alpha(step_index / steps))
            for step_index in range(1, steps + 1)
        ]

    def _wait_until_arm_close(
        self,
        arm: str,
        target_joints: dict[str, float],
        *,
        timeout_s: float,
        tolerate_timeout_joints: set[str] | None = None,
    ) -> None:
        tolerated = set(tolerate_timeout_joints or ())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            current = self.get_arm_joint_positions(arm)
            if self._joints_within_tolerance(
                current=current,
                target_joints=target_joints,
                tolerate_timeout_joints=tolerated,
            ):
                return
            time.sleep(self._step_interval_s())
        current = self.get_arm_joint_positions(arm)
        if self._joints_within_tolerance(
            current=current,
            target_joints=target_joints,
            tolerate_timeout_joints=tolerated,
        ):
            return
        raise TimeoutError(f"Timed out waiting for {arm} joints to reach target {target_joints}")

    def _wait_until_both_arms_close(
        self,
        *,
        left_target_joints: dict[str, float],
        right_target_joints: dict[str, float],
        timeout_s: float,
        left_tolerate_timeout_joints: set[str] | None = None,
        right_tolerate_timeout_joints: set[str] | None = None,
    ) -> None:
        left_tolerated = set(left_tolerate_timeout_joints or ())
        right_tolerated = set(right_tolerate_timeout_joints or ())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            obs = self.get_observation()
            left_current = self._extract_arm_joint_positions(obs, "left")
            right_current = self._extract_arm_joint_positions(obs, "right")
            if (
                self._joints_within_tolerance(
                    current=left_current,
                    target_joints=left_target_joints,
                    tolerate_timeout_joints=left_tolerated,
                )
                and self._joints_within_tolerance(
                    current=right_current,
                    target_joints=right_target_joints,
                    tolerate_timeout_joints=right_tolerated,
                )
            ):
                return
            time.sleep(self._step_interval_s())
        obs = self.get_observation()
        left_current = self._extract_arm_joint_positions(obs, "left")
        right_current = self._extract_arm_joint_positions(obs, "right")
        if (
            self._joints_within_tolerance(
                current=left_current,
                target_joints=left_target_joints,
                tolerate_timeout_joints=left_tolerated,
            )
            and self._joints_within_tolerance(
                current=right_current,
                target_joints=right_target_joints,
                tolerate_timeout_joints=right_tolerated,
            )
        ):
            return
        raise TimeoutError(
            "Timed out waiting for both arms to reach targets "
            f"left={left_target_joints} right={right_target_joints}"
        )

    def _joints_within_tolerance(
        self,
        *,
        current: dict[str, float],
        target_joints: dict[str, float],
        tolerate_timeout_joints: set[str] | None = None,
    ) -> bool:
        tolerated = set(tolerate_timeout_joints or ())
        failing = {
            joint
            for joint, target in target_joints.items()
            if abs(current.get(joint, target) - target) > self.config.move_tolerance_deg
        }
        if not failing:
            return True
        return failing.issubset(tolerated)

    def _extract_arm_joint_positions(self, obs: dict[str, Any], arm: str) -> dict[str, float]:
        arm_key = f"{arm}_arm"
        joints = obs.get(arm_key, {}).get("joint_pos", {})
        return {str(k): float(v) for k, v in joints.items()}

    def _extract_sent_targets(self, sent_action: dict[str, float], arm: str) -> dict[str, float]:
        prefix = f"{arm}_"
        targets: dict[str, float] = {}
        for key, value in sent_action.items():
            if not key.startswith(prefix) or not key.endswith(".pos"):
                continue
            joint = key[len(prefix) : -4]
            targets[joint] = float(value)
        return targets

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
