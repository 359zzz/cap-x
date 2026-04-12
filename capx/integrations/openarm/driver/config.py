from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LEFT_DEFAULT_JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "joint_1": (-75.0, 75.0),
    "joint_2": (-90.0, 9.0),
    "joint_3": (-85.0, 85.0),
    "joint_4": (0.0, 135.0),
    "joint_5": (-85.0, 85.0),
    "joint_6": (-40.0, 40.0),
    "joint_7": (-80.0, 80.0),
    "gripper": (-65.0, 0.0),
}

RIGHT_DEFAULT_JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "joint_1": (-75.0, 75.0),
    "joint_2": (-9.0, 90.0),
    "joint_3": (-85.0, 85.0),
    "joint_4": (0.0, 135.0),
    "joint_5": (-85.0, 85.0),
    "joint_6": (-40.0, 40.0),
    "joint_7": (-80.0, 80.0),
    "gripper": (-65.0, 0.0),
}


def _default_motor_config() -> dict[str, tuple[int, int, str]]:
    return {
        "joint_1": (0x01, 0x11, "dm8009"),
        "joint_2": (0x02, 0x12, "dm8009"),
        "joint_3": (0x03, 0x13, "dm4340"),
        "joint_4": (0x04, 0x14, "dm4340"),
        "joint_5": (0x05, 0x15, "dm4310"),
        "joint_6": (0x06, 0x16, "dm4310"),
        "joint_7": (0x07, 0x17, "dm4310"),
        "gripper": (0x08, 0x18, "dm4310"),
    }


def _safe_joint_limits() -> dict[str, tuple[float, float]]:
    return {
        "joint_1": (-5.0, 5.0),
        "joint_2": (-5.0, 5.0),
        "joint_3": (-5.0, 5.0),
        "joint_4": (0.0, 5.0),
        "joint_5": (-5.0, 5.0),
        "joint_6": (-5.0, 5.0),
        "joint_7": (-5.0, 5.0),
        "gripper": (-5.0, 0.0),
    }


@dataclass
class OpenArmFollowerConfig:
    """Configuration for one OpenArm follower arm using the in-repo Damiao driver."""

    port: str
    id: str | None = None
    calibration_dir: Path | None = None
    side: str | None = None
    can_interface: str = "socketcan"
    use_can_fd: bool = True
    can_bitrate: int = 1_000_000
    can_data_bitrate: int = 5_000_000
    disable_torque_on_disconnect: bool = True
    max_relative_target: float | dict[str, float] | None = None
    cameras: dict[str, Any] = field(default_factory=dict)
    motor_config: dict[str, tuple[int, int, str]] = field(default_factory=_default_motor_config)
    position_kp: list[float] = field(
        default_factory=lambda: [240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0]
    )
    position_kd: list[float] = field(
        default_factory=lambda: [5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3]
    )
    joint_limits: dict[str, tuple[float, float]] = field(default_factory=_safe_joint_limits)


@dataclass
class BiOpenArmFollowerConfig:
    """Configuration for a bimanual OpenArm follower setup."""

    left_arm_config: OpenArmFollowerConfig
    right_arm_config: OpenArmFollowerConfig
    id: str | None = None
    calibration_dir: Path | None = None
