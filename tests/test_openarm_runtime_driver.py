from __future__ import annotations

from types import SimpleNamespace

from capx.integrations.openarm.runtime import InRepoBiOpenArmDriver, OpenArmRuntimeConfig
from capx.integrations.openarm.runtime import OpenArmRuntime


def test_in_repo_openarm_driver_builds_embedded_robot_graph() -> None:
    cfg = OpenArmRuntimeConfig()
    cfg.left_arm.port = "can-left"
    cfg.right_arm.port = "can-right"

    driver = InRepoBiOpenArmDriver(cfg)
    driver._ensure_robot()

    assert driver._robot is not None
    assert driver._robot.__class__.__name__ == "BiOpenArmFollower"
    assert driver._robot.left_arm.config.port == "can-left"
    assert driver._robot.right_arm.config.port == "can-right"


def test_in_repo_openarm_driver_propagates_zero_on_connect_flags() -> None:
    cfg = OpenArmRuntimeConfig()
    cfg.left_arm.port = "can-left"
    cfg.right_arm.port = "can-right"
    cfg.left_arm.zero_on_connect = True
    cfg.right_arm.zero_on_connect = False

    driver = InRepoBiOpenArmDriver(cfg)
    driver._ensure_robot()

    assert driver._robot is not None
    assert driver._robot.left_arm.config.zero_on_connect is True
    assert driver._robot.right_arm.config.zero_on_connect is False


def test_openarm_runtime_maps_gripper_fraction_with_closed_zero() -> None:
    runtime = OpenArmRuntime(
        driver=SimpleNamespace(),
        perception=SimpleNamespace(),
    )
    runtime.config.step_sleep_s = 0.0
    recorded: list[tuple[str, dict[str, float], str]] = []

    def _capture(
        arm: str,
        target_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
    ) -> dict[str, float]:
        del timeout_s
        recorded.append((arm, dict(target_joints), speed))
        return dict(target_joints)

    runtime.move_arm_joints_blocking = _capture  # type: ignore[method-assign]

    closed = runtime.set_gripper_fraction("left", 0.0)
    opened = runtime.set_gripper_fraction("right", 1.0)

    assert closed == 0.0
    assert opened == -65.0
    assert recorded == [
        ("left", {"gripper": 0.0}, "slow"),
        ("right", {"gripper": -65.0}, "slow"),
    ]
