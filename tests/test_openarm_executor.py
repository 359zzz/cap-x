from __future__ import annotations

from contextlib import contextmanager

from capx.integrations.openarm.assets import AnchorAsset
from capx.integrations.openarm.executor import OpenArmMotionExecutor


class FakeRuntime:
    def __init__(self) -> None:
        self.single_calls: list[tuple[str, dict[str, float], str]] = []
        self.both_calls: list[tuple[dict[str, float], dict[str, float], str]] = []

    @contextmanager
    def active_task(self, name: str):
        del name
        yield

    def move_arm_joints_blocking(
        self,
        arm: str,
        joints: dict[str, float],
        *,
        speed: str = "slow",
    ) -> dict[str, float]:
        payload = dict(joints)
        self.single_calls.append((arm, payload, speed))
        return payload

    def move_both_arms_blocking(
        self,
        left_joints: dict[str, float],
        right_joints: dict[str, float],
        *,
        speed: str = "slow",
    ) -> dict[str, dict[str, float]]:
        left_payload = dict(left_joints)
        right_payload = dict(right_joints)
        self.both_calls.append((left_payload, right_payload, speed))
        return {"left": left_payload, "right": right_payload}


class FakeRegistry:
    def __init__(self, anchor: AnchorAsset) -> None:
        self.anchor = anchor

    def load_anchor(self, name: str) -> AnchorAsset:
        assert name == self.anchor.name
        return self.anchor


def test_move_to_named_pose_can_ignore_gripper_for_bimanual_anchor() -> None:
    runtime = FakeRuntime()
    registry = FakeRegistry(
        AnchorAsset(
            name="tomato_dual_grasp_sync",
            arm_mode="both",
            joints_by_arm={
                "left": {"joint_1": 10.0, "gripper": -55.0},
                "right": {"joint_2": -8.0, "gripper": -57.0},
            },
            region="front",
        )
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.move_to_named_pose(
        "tomato_dual_grasp_sync",
        ignore_gripper=True,
    )

    assert runtime.both_calls == [
        ({"joint_1": 10.0}, {"joint_2": -8.0}, "slow")
    ]
    assert result["ignored_joints"] == ["gripper"]
    assert result["final_joints"]["left"] == {"joint_1": 10.0}
    assert result["final_joints"]["right"] == {"joint_2": -8.0}


def test_move_to_named_pose_keeps_gripper_when_not_ignored() -> None:
    runtime = FakeRuntime()
    registry = FakeRegistry(
        AnchorAsset(
            name="right_front_mid",
            arm_mode="single",
            joints_by_arm={
                "right": {"joint_1": 5.0, "gripper": -30.0},
            },
            region="front",
        )
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.move_to_named_pose("right_front_mid")

    assert runtime.single_calls == [
        ("right", {"joint_1": 5.0, "gripper": -30.0}, "slow")
    ]
    assert result["ignored_joints"] == []
