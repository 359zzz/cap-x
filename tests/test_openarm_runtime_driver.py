from __future__ import annotations

from capx.integrations.openarm.runtime import InRepoBiOpenArmDriver, OpenArmRuntimeConfig


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
