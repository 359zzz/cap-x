from __future__ import annotations

import logging
import time
from functools import cached_property
from pprint import pformat
from typing import Any

from .common import (
    CalibrationBackedDevice,
    Motor,
    MotorCalibration,
    MotorNormMode,
    RobotAction,
    RobotObservation,
    check_if_already_connected,
    check_if_not_connected,
)
from .config import (
    LEFT_DEFAULT_JOINT_LIMITS,
    RIGHT_DEFAULT_JOINT_LIMITS,
    BiOpenArmFollowerConfig,
    OpenArmFollowerConfig,
)
from .damiao_bus import DamiaoMotorsBus

logger = logging.getLogger(__name__)

OPENARM_MOTOR_ORDER = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "joint_7",
    "gripper",
)


def ensure_safe_goal_position(
    goal_present_pos: dict[str, tuple[float, float]],
    max_relative_target: float | dict[str, float],
) -> dict[str, float]:
    """Clamp relative target magnitude for safety before sending motor commands."""

    if isinstance(max_relative_target, (float, int)):
        diff_cap = dict.fromkeys(goal_present_pos, float(max_relative_target))
    elif isinstance(max_relative_target, dict):
        if set(goal_present_pos) != set(max_relative_target):
            raise ValueError("max_relative_target keys must match goal_present_pos keys.")
        diff_cap = {name: float(value) for name, value in max_relative_target.items()}
    else:
        raise TypeError(max_relative_target)

    warnings: dict[str, dict[str, float]] = {}
    safe_goal_positions: dict[str, float] = {}
    for key, (goal_pos, present_pos) in goal_present_pos.items():
        max_diff = diff_cap[key]
        safe_diff = min(goal_pos - present_pos, max_diff)
        safe_diff = max(safe_diff, -max_diff)
        safe_goal_pos = present_pos + safe_diff
        safe_goal_positions[key] = safe_goal_pos
        if abs(safe_goal_pos - goal_pos) > 1e-4:
            warnings[key] = {"original_goal_pos": goal_pos, "safe_goal_pos": safe_goal_pos}

    if warnings:
        logger.warning(
            "OpenArm relative target had to be clamped for safety:\n%s",
            pformat(warnings, indent=4),
        )
    return safe_goal_positions


class OpenArmFollower(CalibrationBackedDevice):
    """One OpenArm follower arm backed by the in-repo Damiao CAN driver."""

    name = "openarm_follower"

    def __init__(self, config: OpenArmFollowerConfig) -> None:
        super().__init__(device_id=config.id, calibration_dir=config.calibration_dir)
        self.config = config

        motors: dict[str, Motor] = {}
        for motor_name, (send_id, recv_id, motor_type) in config.motor_config.items():
            motors[motor_name] = Motor(
                id=send_id,
                model=motor_type,
                norm_mode=MotorNormMode.DEGREES,
                motor_type_str=motor_type,
                recv_id=recv_id,
            )

        if config.side == "left":
            config.joint_limits = dict(LEFT_DEFAULT_JOINT_LIMITS)
        elif config.side == "right":
            config.joint_limits = dict(RIGHT_DEFAULT_JOINT_LIMITS)
        elif config.side is not None:
            raise ValueError("OpenArm side must be 'left', 'right', or None.")

        self.bus = DamiaoMotorsBus(
            port=config.port,
            motors=motors,
            calibration=self.calibration,
            can_interface=config.can_interface,
            use_can_fd=config.use_can_fd,
            bitrate=config.can_bitrate,
            data_bitrate=config.can_data_bitrate if config.use_can_fd else None,
        )
        self.cameras: dict[str, Any] = {}
        if config.cameras:
            logger.warning(
                "Local OpenArm camera configs are ignored by the in-repo driver. "
                "Use the OpenClaw perception HTTP adapter for vision/tactile data."
            )

    @property
    def _motors_ft(self) -> dict[str, type]:
        features: dict[str, type] = {}
        for motor in self.bus.motors:
            features[f"{motor}.pos"] = float
            features[f"{motor}.vel"] = float
            features[f"{motor}.torque"] = float
        return features

    @property
    def _cameras_ft(self) -> dict[str, tuple[int, int, int]]:
        return {}

    @cached_property
    def observation_features(self) -> dict[str, type | tuple[int, int, int]]:
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        return self.bus.is_connected

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        logger.info("Connecting OpenArm %s arm on %s...", self.config.side or "unknown", self.config.port)
        self.bus.connect()
        if not self.is_calibrated and calibrate:
            self.calibrate()
        self.configure()
        if self.is_calibrated and self.config.zero_on_connect:
            logger.warning(
                "OpenArm %s is zeroing all motors on connect. "
                "Use this only when the arm is already in the intended zero posture.",
                self.config.side or "unknown",
            )
            self.bus.set_zero_position()
        self.bus.enable_torque()
        logger.info("%s connected.", self)

    @property
    def is_calibrated(self) -> bool:
        return self.bus.is_calibrated

    def calibrate(self) -> None:
        if self.calibration:
            user_input = input(
                f"Press ENTER to use calibration file for {self.id}, "
                "or type 'c' and press ENTER to run calibration: "
            )
            if user_input.strip().lower() != "c":
                self.bus.write_calibration(self.calibration)
                return

        logger.info("Running OpenArm calibration for %s.", self)
        self.bus.disable_torque()
        input(
            "\nCalibration: place the arm in a safe hanging zero posture "
            "with the gripper closed, then press ENTER..."
        )
        self.bus.set_zero_position()
        for motor_name, motor in self.bus.motors.items():
            min_limit, max_limit = self.config.joint_limits.get(motor_name, (-90.0, 90.0))
            self.calibration[motor_name] = MotorCalibration(
                id=motor.id,
                drive_mode=0,
                homing_offset=0,
                range_min=int(round(min_limit)),
                range_max=int(round(max_limit)),
            )
        self.bus.write_calibration(self.calibration)
        self._save_calibration()
        logger.info("OpenArm calibration saved to %s.", self.calibration_fpath)

    def configure(self) -> None:
        with self.bus.torque_disabled():
            self.bus.configure_motors()

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        start = time.perf_counter()
        states = self.bus.sync_read_all_states()
        obs: dict[str, Any] = {}
        for motor in self.bus.motors:
            state = states.get(motor, {})
            obs[f"{motor}.pos"] = state.get("position", 0.0)
            obs[f"{motor}.vel"] = state.get("velocity", 0.0)
            obs[f"{motor}.torque"] = state.get("torque", 0.0)
        logger.debug("%s get_observation took %.1fms", self, (time.perf_counter() - start) * 1e3)
        return obs

    @check_if_not_connected
    def send_action(
        self,
        action: RobotAction,
        custom_kp: dict[str, float] | None = None,
        custom_kd: dict[str, float] | None = None,
    ) -> RobotAction:
        goal_pos = {
            key.removesuffix(".pos"): float(value)
            for key, value in action.items()
            if key.endswith(".pos")
        }

        for motor_name, position in list(goal_pos.items()):
            if motor_name in self.config.joint_limits:
                min_limit, max_limit = self.config.joint_limits[motor_name]
                goal_pos[motor_name] = max(min_limit, min(max_limit, position))

        if self.config.max_relative_target is not None and goal_pos:
            present_pos = self.bus.sync_read("Present_Position", list(goal_pos))
            goal_present_pos = {
                key: (goal, float(present_pos[key]))
                for key, goal in goal_pos.items()
                if key in present_pos
            }
            goal_pos = ensure_safe_goal_position(goal_present_pos, self.config.max_relative_target)

        motor_index = {name: index for index, name in enumerate(OPENARM_MOTOR_ORDER)}
        commands: dict[str, tuple[float, float, float, float, float]] = {}
        for motor_name, position_degrees in goal_pos.items():
            idx = motor_index.get(motor_name, 0)
            kp = (
                custom_kp[motor_name]
                if custom_kp is not None and motor_name in custom_kp
                else self.config.position_kp[idx]
            )
            kd = (
                custom_kd[motor_name]
                if custom_kd is not None and motor_name in custom_kd
                else self.config.position_kd[idx]
            )
            commands[motor_name] = (float(kp), float(kd), position_degrees, 0.0, 0.0)

        self.bus._mit_control_batch(commands)
        return {f"{motor}.pos": value for motor, value in goal_pos.items()}

    @check_if_not_connected
    def disconnect(self) -> None:
        self.bus.disconnect(self.config.disable_torque_on_disconnect)
        logger.info("%s disconnected.", self)


class BiOpenArmFollower(CalibrationBackedDevice):
    """Bimanual OpenArm wrapper with the same flat action/observation schema as the old adapter."""

    name = "bi_openarm_follower"

    def __init__(self, config: BiOpenArmFollowerConfig) -> None:
        super().__init__(device_id=config.id, calibration_dir=config.calibration_dir)
        self.config = config

        left_cfg = OpenArmFollowerConfig(
            id=f"{config.id}_left" if config.id else config.left_arm_config.id,
            calibration_dir=config.calibration_dir,
            port=config.left_arm_config.port,
            disable_torque_on_disconnect=config.left_arm_config.disable_torque_on_disconnect,
            max_relative_target=config.left_arm_config.max_relative_target,
            cameras=config.left_arm_config.cameras,
            side=config.left_arm_config.side,
            zero_on_connect=config.left_arm_config.zero_on_connect,
            can_interface=config.left_arm_config.can_interface,
            use_can_fd=config.left_arm_config.use_can_fd,
            can_bitrate=config.left_arm_config.can_bitrate,
            can_data_bitrate=config.left_arm_config.can_data_bitrate,
            motor_config=config.left_arm_config.motor_config,
            position_kd=config.left_arm_config.position_kd,
            position_kp=config.left_arm_config.position_kp,
            joint_limits=config.left_arm_config.joint_limits,
        )
        right_cfg = OpenArmFollowerConfig(
            id=f"{config.id}_right" if config.id else config.right_arm_config.id,
            calibration_dir=config.calibration_dir,
            port=config.right_arm_config.port,
            disable_torque_on_disconnect=config.right_arm_config.disable_torque_on_disconnect,
            max_relative_target=config.right_arm_config.max_relative_target,
            cameras=config.right_arm_config.cameras,
            side=config.right_arm_config.side,
            zero_on_connect=config.right_arm_config.zero_on_connect,
            can_interface=config.right_arm_config.can_interface,
            use_can_fd=config.right_arm_config.use_can_fd,
            can_bitrate=config.right_arm_config.can_bitrate,
            can_data_bitrate=config.right_arm_config.can_data_bitrate,
            motor_config=config.right_arm_config.motor_config,
            position_kd=config.right_arm_config.position_kd,
            position_kp=config.right_arm_config.position_kp,
            joint_limits=config.right_arm_config.joint_limits,
        )
        self.left_arm = OpenArmFollower(left_cfg)
        self.right_arm = OpenArmFollower(right_cfg)
        self.cameras: dict[str, Any] = {}

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {
            **{f"left_{key}": value for key, value in self.left_arm._motors_ft.items()},
            **{f"right_{key}": value for key, value in self.right_arm._motors_ft.items()},
        }

    @property
    def _cameras_ft(self) -> dict[str, tuple[int, int, int]]:
        return {}

    @cached_property
    def observation_features(self) -> dict[str, type | tuple[int, int, int]]:
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def is_connected(self) -> bool:
        return self.left_arm.is_connected and self.right_arm.is_connected

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        self.left_arm.connect(calibrate=calibrate)
        self.right_arm.connect(calibrate=calibrate)

    @property
    def is_calibrated(self) -> bool:
        return self.left_arm.is_calibrated and self.right_arm.is_calibrated

    def calibrate(self) -> None:
        self.left_arm.calibrate()
        self.right_arm.calibrate()

    def configure(self) -> None:
        self.left_arm.configure()
        self.right_arm.configure()

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        obs: dict[str, Any] = {}
        obs.update({f"left_{key}": value for key, value in self.left_arm.get_observation().items()})
        obs.update({f"right_{key}": value for key, value in self.right_arm.get_observation().items()})
        return obs

    @check_if_not_connected
    def send_action(
        self,
        action: RobotAction,
        custom_kp: dict[str, float] | None = None,
        custom_kd: dict[str, float] | None = None,
    ) -> RobotAction:
        left_action = {
            key.removeprefix("left_"): value for key, value in action.items() if key.startswith("left_")
        }
        right_action = {
            key.removeprefix("right_"): value
            for key, value in action.items()
            if key.startswith("right_")
        }
        sent_left = self.left_arm.send_action(left_action, custom_kp, custom_kd) if left_action else {}
        sent_right = self.right_arm.send_action(right_action, custom_kp, custom_kd) if right_action else {}
        return {
            **{f"left_{key}": value for key, value in sent_left.items()},
            **{f"right_{key}": value for key, value in sent_right.items()},
        }

    @check_if_not_connected
    def disconnect(self) -> None:
        self.left_arm.disconnect()
        self.right_arm.disconnect()
