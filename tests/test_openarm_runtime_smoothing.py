from __future__ import annotations

from typing import Any

from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


_ARM_JOINTS = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
    "joint_7",
    "gripper",
)


def _zero_arm() -> dict[str, float]:
    return {joint: 0.0 for joint in _ARM_JOINTS}


class DummyPerception:
    def tactile_read(self) -> dict[str, Any]:
        return {"contact": False, "stable_grasp": False}

    def tactile_health(self) -> dict[str, Any]:
        return {"status": "ok"}

    def detect_once(self, target_name: str | None, *, top_k: int = 3) -> dict[str, Any]:
        del target_name, top_k
        return {"detections": []}


class ImmediateDriver:
    def __init__(self) -> None:
        self.is_connected = True
        self.is_calibrated = True
        self.positions = {"left": _zero_arm(), "right": _zero_arm()}
        self.sent_actions: list[dict[str, float]] = []

    def connect(self, *, calibrate: bool) -> None:
        del calibrate
        self.is_connected = True

    def disconnect(self) -> None:
        self.is_connected = False

    def get_observation(self) -> dict[str, float]:
        obs: dict[str, float] = {}
        for arm, joints in self.positions.items():
            for joint, value in joints.items():
                obs[f"{arm}_{joint}.pos"] = float(value)
                obs[f"{arm}_{joint}.vel"] = 0.0
                obs[f"{arm}_{joint}.torque"] = 0.0
        return obs

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        self.sent_actions.append(dict(action))
        for key, value in action.items():
            arm, suffix = key.split("_", 1)
            joint = suffix.removesuffix(".pos")
            self.positions[arm][joint] = float(value)
        return dict(action)


class ClampingImmediateDriver(ImmediateDriver):
    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        actual = dict(action)
        for key, value in list(actual.items()):
            if key.endswith("gripper.pos"):
                actual[key] = min(0.0, float(value))
        return super().send_action(actual)


def _runtime_for_smoothing(driver: ImmediateDriver) -> OpenArmRuntime:
    cfg = OpenArmRuntimeConfig()
    cfg.step_sleep_s = 0.001
    cfg.min_trajectory_duration_s = 0.004
    cfg.max_trajectory_duration_s = 0.02
    cfg.move_tolerance_deg = 0.01
    return OpenArmRuntime(cfg, driver=driver, perception=DummyPerception())


def test_single_arm_motion_uses_multiple_interpolated_waypoints() -> None:
    driver = ImmediateDriver()
    runtime = _runtime_for_smoothing(driver)

    final = runtime.move_arm_joints_blocking("left", {"joint_1": 12.0}, speed="slow", timeout_s=0.2)

    assert final["joint_1"] == 12.0
    assert len(driver.sent_actions) > 1
    first = driver.sent_actions[0]["left_joint_1.pos"]
    last = driver.sent_actions[-1]["left_joint_1.pos"]
    assert 0.0 < first < 12.0
    assert last == 12.0
    assert [step["left_joint_1.pos"] for step in driver.sent_actions] == sorted(
        step["left_joint_1.pos"] for step in driver.sent_actions
    )


def test_bimanual_motion_keeps_both_arms_on_the_same_interpolation_progress() -> None:
    driver = ImmediateDriver()
    runtime = _runtime_for_smoothing(driver)

    final = runtime.move_both_arms_blocking(
        {"joint_1": 10.0, "joint_4": 4.0},
        {"joint_1": -8.0},
        speed="medium",
        timeout_s=0.2,
    )

    assert final["left"]["joint_1"] == 10.0
    assert final["left"]["joint_4"] == 4.0
    assert final["right"]["joint_1"] == -8.0
    assert len(driver.sent_actions) > 1
    assert all("left_joint_1.pos" in action for action in driver.sent_actions)
    assert all("right_joint_1.pos" in action for action in driver.sent_actions)
    assert all("left_joint_4.pos" in action for action in driver.sent_actions)


def test_bimanual_motion_waits_for_actual_sent_targets_after_clamping() -> None:
    driver = ClampingImmediateDriver()
    driver.positions["left"]["gripper"] = 12.0
    driver.positions["right"]["gripper"] = 11.0
    runtime = _runtime_for_smoothing(driver)

    final = runtime.move_both_arms_blocking(
        {"gripper": 5.0},
        {"gripper": 3.0},
        speed="slow",
        timeout_s=0.2,
    )

    assert final["left"]["gripper"] == 0.0
    assert final["right"]["gripper"] == 0.0
