from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from capx.integrations.openarm.assets import (
    AnchorAsset,
    ComboPhaseAsset,
    ComboTemplateAsset,
    OpenArmMotionAssetRegistry,
    PrimitiveTemplateAsset,
)
from capx.integrations.openarm.catalog import DEFAULT_PRIMITIVES
from capx.integrations.openarm.control import OpenArmControlApi
from capx.integrations.openarm.executor import OpenArmMotionExecutor
from capx.integrations.openarm.recording import ManualOpenArmRecorder


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


def _zero_joints(**overrides: float) -> dict[str, float]:
    joints = {name: 0.0 for name in _ARM_JOINTS}
    joints.update(overrides)
    return joints


class FakeRuntime:
    def __init__(self) -> None:
        self.task_state = "IDLE"
        self.joints = {
            "left": _zero_joints(),
            "right": _zero_joints(),
        }
        self.tactile_reads: list[dict[str, object]] = []
        self.detection_reads: list[dict[str, object]] = []
        self.tactile_health_payload = {"status": "ok", "sensor_count": 1}

    @contextmanager
    def active_task(self, name: str):
        del name
        prev = self.task_state
        self.task_state = "RUNNING"
        try:
            yield
        finally:
            self.task_state = prev if prev != "RUNNING" else "IDLE"

    def ensure_connected(self) -> None:
        return None

    def get_robot_state(self) -> dict[str, object]:
        return {"task_state": self.task_state, "connected": True, "calibrated": True}

    def get_observation(self) -> dict[str, object]:
        return {
            "left_arm": {"joint_pos": dict(self.joints["left"])},
            "right_arm": {"joint_pos": dict(self.joints["right"])},
            "cameras": {},
        }

    def get_arm_joint_positions(self, arm: str) -> dict[str, float]:
        return dict(self.joints[arm])

    def move_arm_joints_blocking(
        self,
        arm: str,
        target_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
    ) -> dict[str, float]:
        del speed, timeout_s
        self.joints[arm].update(target_joints)
        return dict(self.joints[arm])

    def move_both_arms_blocking(
        self,
        left_joints: dict[str, float],
        right_joints: dict[str, float],
        *,
        speed: str = "slow",
        timeout_s: float | None = None,
    ) -> dict[str, dict[str, float]]:
        del speed, timeout_s
        self.joints["left"].update(left_joints)
        self.joints["right"].update(right_joints)
        return {"left": dict(self.joints["left"]), "right": dict(self.joints["right"])}

    def set_gripper_fraction(self, arm: str, fraction: float) -> float:
        self.joints[arm]["gripper"] = fraction
        return fraction

    def set_gripper_by_magnitude(self, arm: str, primitive: str, magnitude: str) -> float:
        mapping = {"slight": 0.10, "small": 0.25, "medium": 0.50, "large": 1.00}
        fraction = mapping[magnitude]
        if primitive == "close_gripper":
            fraction = 1.0 - fraction
        self.joints[arm]["gripper"] = fraction
        return self.joints[arm]["gripper"]

    def stop_motion(self) -> None:
        self.task_state = "IDLE"

    def read_tactile(self) -> dict[str, object]:
        if self.tactile_reads:
            return dict(self.tactile_reads.pop(0))
        return {"contact": False, "stable_grasp": False}

    def get_tactile_health(self) -> dict[str, object]:
        return dict(self.tactile_health_payload)

    def detect_target(self, target_name: str | None, *, top_k: int = 3) -> dict[str, object]:
        del top_k
        if self.detection_reads:
            payload = dict(self.detection_reads.pop(0))
        else:
            payload = {"detections": [{"label": target_name, "camera_xyz_m": [0.1, 0.0, 0.2]}]}
        detections = []
        for detection in payload.get("detections", []):
            item = dict(detection)
            if target_name and not item.get("label"):
                item["label"] = target_name
            detections.append(item)
        return {"detections": detections}

    def describe_scene(self, prompt: str | None = None) -> dict[str, object]:
        return {
            "description": prompt or "test scene",
            "detections": [],
            "image_base64": "data:image/png;base64,abc123",
        }


def _make_registry(tmp_path: Path) -> OpenArmMotionAssetRegistry:
    registry = OpenArmMotionAssetRegistry(asset_root=tmp_path / "openarm")
    for anchor in [
        AnchorAsset(
            name="left_neutral_relaxed",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints()},
            region="left_neutral_relaxed",
        ),
        AnchorAsset(
            name="right_neutral_relaxed",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints()},
            region="right_neutral_relaxed",
        ),
        AnchorAsset(
            name="left_neutral_ready",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints()},
            region="left_neutral_ready",
        ),
        AnchorAsset(
            name="right_neutral_ready",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints()},
            region="right_neutral_ready",
        ),
        AnchorAsset(
            name="left_chest_front",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints()},
            region="left_chest_front",
        ),
        AnchorAsset(
            name="right_chest_front",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints()},
            region="right_chest_front",
        ),
        AnchorAsset(
            name="left_front_mid",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints(joint_1=18.0)},
            region="left_front_mid",
        ),
        AnchorAsset(
            name="right_front_mid",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints(joint_1=16.0)},
            region="right_front_mid",
        ),
        AnchorAsset(
            name="left_side_open",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints(joint_2=20.0)},
            region="left_side_open",
        ),
        AnchorAsset(
            name="right_side_open",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints(joint_2=20.0)},
            region="right_side_open",
        ),
        AnchorAsset(
            name="left_wrist_upright",
            arm_mode="single",
            joints_by_arm={"left": _zero_joints(joint_7=12.0)},
            region="left_wrist_upright",
        ),
        AnchorAsset(
            name="right_wrist_upright",
            arm_mode="single",
            joints_by_arm={"right": _zero_joints(joint_7=12.0)},
            region="right_wrist_upright",
        ),
        AnchorAsset(
            name="home",
            arm_mode="both",
            joints_by_arm={"left": _zero_joints(), "right": _zero_joints()},
            region="home",
        ),
        AnchorAsset(
            name="safe_standby",
            arm_mode="both",
            joints_by_arm={"left": _zero_joints(), "right": _zero_joints()},
            region="safe_standby",
        ),
        AnchorAsset(
            name="handover_center",
            arm_mode="both",
            joints_by_arm={
                "left": _zero_joints(joint_1=8.0, joint_4=10.0),
                "right": _zero_joints(joint_1=8.0, joint_4=10.0),
            },
            region="handover_center",
        ),
    ]:
        registry.save_anchor(anchor)
    return registry


def _save_primitive(
    registry: OpenArmMotionAssetRegistry,
    *,
    arm: str,
    primitive: str,
    magnitude: str,
    start_anchor: str,
    joint_delta_deg: dict[str, float],
    end_region_hint: str,
) -> None:
    definition = DEFAULT_PRIMITIVES[primitive]
    registry.save_primitive_template(
        PrimitiveTemplateAsset(
            id=f"primitive.{arm}.{start_anchor}.{primitive}.{magnitude}.v1",
            version="v1",
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            start_anchor=start_anchor,
            allowed_start_anchors=[start_anchor],
            primary_joint_group=definition.primary_joint_group,
            nominal_joint_delta_deg=joint_delta_deg,
            joint_delta_tolerance_deg={joint: 3.0 for joint in joint_delta_deg},
            nominal_ee_delta_base=[0.0, 0.0, 0.0],
            nominal_ee_delta_local=[0.0, 0.0, 0.0],
            end_region_hint=end_region_hint,
            default_step_count=4,
            default_speed="slow",
            settle_time_ms=120,
            timeout_ms=4000,
            guard_joint_margin_deg=5.0,
            guard_max_step_delta_deg=10.0,
            guard_max_ee_error_m=0.08,
            guard_abort_on_tactile_contact=False,
            guard_abort_on_torque_spike=True,
            inverse_primitive=definition.inverse_primitive,
            recovery_anchor=start_anchor,
        )
    )


def test_asset_registry_round_trip(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    primitive = PrimitiveTemplateAsset(
        id="primitive.left.left_neutral_ready.raise_upper_arm.medium.v1",
        version="v1",
        arm="left",
        primitive="raise_upper_arm",
        magnitude="medium",
        start_anchor="left_neutral_ready",
        allowed_start_anchors=["left_neutral_ready"],
        primary_joint_group="upper_arm",
        nominal_joint_delta_deg={"joint_1": 18.0},
        joint_delta_tolerance_deg={"joint_1": 3.0},
        nominal_ee_delta_base=[0.1, 0.0, 0.1],
        nominal_ee_delta_local=[0.1, 0.0, 0.1],
        end_region_hint="left_front_mid",
        default_step_count=4,
        default_speed="slow",
        settle_time_ms=120,
        timeout_ms=4000,
        guard_joint_margin_deg=5.0,
        guard_max_step_delta_deg=10.0,
        guard_max_ee_error_m=0.08,
        guard_abort_on_tactile_contact=False,
        guard_abort_on_torque_spike=True,
        inverse_primitive="lower_upper_arm",
        recovery_anchor="left_neutral_ready",
    )
    combo = ComboTemplateAsset(
        id="combo.single.hand_to_chest.medium.v1",
        version="v1",
        combo="hand_to_chest",
        arm_mode="single",
        magnitude="medium",
        allowed_start_anchors=["left_neutral_ready"],
        goal_region="left_chest_front",
        goal_pose_anchor=None,
        default_speed="slow",
        phases=[ComboPhaseAsset(primitive="raise_upper_arm", magnitude="medium", arm="selected")],
        recovery_anchor="left_neutral_ready",
    )
    registry.save_primitive_template(primitive)
    registry.save_combo_template(combo)

    loaded_primitive = registry.load_primitive_template(
        primitive="raise_upper_arm",
        arm="left",
        start_anchor="left_neutral_ready",
        magnitude="medium",
    )
    loaded_combo = registry.load_combo_template(
        combo="hand_to_chest",
        arm_mode="single",
        magnitude="medium",
    )

    assert loaded_primitive.nominal_joint_delta_deg["joint_1"] == 18.0
    assert loaded_combo.phases[0].primitive == "raise_upper_arm"
    assert registry.load_anchor("left_neutral_ready").region == "left_neutral_ready"


def test_manual_recorder_builds_primitive_delta(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.joints["left"]["joint_1"] = 12.0
    registry = _make_registry(tmp_path)
    recorder = ManualOpenArmRecorder(runtime, registry)

    result = recorder.record_primitive_template(
        arm="left",
        primitive="raise_upper_arm",
        magnitude="small",
        start_anchor="left_neutral_ready",
        end_region_hint="left_front_mid",
    )

    template = registry.load_primitive_template(
        primitive="raise_upper_arm",
        arm="left",
        start_anchor="left_neutral_ready",
        magnitude="small",
    )
    assert result.asset_id.startswith("primitive.left")
    assert template.nominal_joint_delta_deg["joint_1"] == 12.0


def test_executor_executes_primitive_and_combo(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    registry = _make_registry(tmp_path)
    _save_primitive(
        registry,
        arm="left",
        primitive="raise_upper_arm",
        magnitude="medium",
        start_anchor="left_neutral_ready",
        joint_delta_deg={"joint_1": 18.0},
        end_region_hint="left_front_mid",
    )
    registry.save_combo_template(
        ComboTemplateAsset(
            id="combo.single.hand_to_chest.medium.v1",
            version="v1",
            combo="hand_to_chest",
            arm_mode="single",
            magnitude="medium",
            allowed_start_anchors=["left_neutral_ready"],
            goal_region="left_front_mid",
            goal_pose_anchor=None,
            default_speed="slow",
            phases=[ComboPhaseAsset(primitive="raise_upper_arm", magnitude="medium", arm="selected")],
            completion_rule={"goal_region": "left_front_mid"},
            recovery_anchor="left_neutral_ready",
        )
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    primitive_result = executor.execute_motion_primitive("left", "raise_upper_arm", "medium")
    combo_result = executor.execute_motion_combo("hand_to_chest", arm="left", magnitude="medium")

    assert primitive_result["success"] is True
    assert runtime.joints["left"]["joint_1"] == 18.0
    assert combo_result["success"] is True
    assert combo_result["combo"] == "hand_to_chest"


def test_registry_bootstraps_combo_templates_with_explicit_magnitude(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)

    created = registry.bootstrap_combo_templates(magnitude="large")
    template = registry.load_combo_template("hand_to_chest", arm_mode="single", magnitude="large")

    assert created
    assert template.magnitude == "large"
    assert template.id == "combo.single.hand_to_chest.large.v1"


def test_executor_executes_bimanual_primitive(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    registry = _make_registry(tmp_path)
    _save_primitive(
        registry,
        arm="left",
        primitive="raise_upper_arm",
        magnitude="medium",
        start_anchor="left_neutral_ready",
        joint_delta_deg={"joint_1": 18.0},
        end_region_hint="left_front_mid",
    )
    _save_primitive(
        registry,
        arm="right",
        primitive="raise_upper_arm",
        magnitude="medium",
        start_anchor="right_neutral_ready",
        joint_delta_deg={"joint_1": 16.0},
        end_region_hint="right_front_mid",
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.execute_bimanual_primitive("raise_upper_arm", "medium")

    assert result["success"] is True
    assert runtime.joints["left"]["joint_1"] == 18.0
    assert runtime.joints["right"]["joint_1"] == 16.0


def test_executor_combo_skips_phase_when_already_in_region(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.joints["left"]["joint_1"] = 18.0
    registry = _make_registry(tmp_path)
    _save_primitive(
        registry,
        arm="left",
        primitive="raise_upper_arm",
        magnitude="medium",
        start_anchor="left_neutral_ready",
        joint_delta_deg={"joint_1": 18.0},
        end_region_hint="left_front_mid",
    )
    registry.save_combo_template(
        ComboTemplateAsset(
            id="combo.single.hand_forward_present.medium.v1",
            version="v1",
            combo="hand_forward_present",
            arm_mode="single",
            magnitude="medium",
            allowed_start_anchors=["left_neutral_ready"],
            goal_region="*_front_mid",
            goal_pose_anchor=None,
            default_speed="slow",
            phases=[
                ComboPhaseAsset(
                    primitive="raise_upper_arm",
                    magnitude="medium",
                    arm="selected",
                    expected_region_after_phase="*_front_mid",
                    allow_skip_if_already_in_region=True,
                )
            ],
            completion_rule={"goal_region": "*_front_mid"},
            recovery_anchor="safe_standby",
        )
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.execute_motion_combo("hand_forward_present", arm="left", magnitude="medium")

    assert result["success"] is True
    assert result["phase_results"] == []
    assert result["checkpoint_results"][0]["skipped"] is True
    assert runtime.joints["left"]["joint_1"] == 18.0


def test_executor_combo_recovers_on_contact_abort(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.joints["left"]["joint_1"] = 14.0
    runtime.tactile_reads = [{"contact": True, "stable_grasp": False}]
    registry = _make_registry(tmp_path)
    registry.save_combo_template(
        ComboTemplateAsset(
            id="combo.single.hand_to_chest.medium.v1",
            version="v1",
            combo="hand_to_chest",
            arm_mode="single",
            magnitude="medium",
            allowed_start_anchors=["left_neutral_ready"],
            goal_region="*_chest_front",
            goal_pose_anchor=None,
            default_speed="slow",
            phases=[
                ComboPhaseAsset(
                    primitive="raise_upper_arm",
                    magnitude="medium",
                    arm="selected",
                    abort_on_contact=True,
                )
            ],
            recovery_anchor="safe_standby",
        )
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.execute_motion_combo("hand_to_chest", arm="left", magnitude="medium")

    assert result["success"] is False
    assert result["recovery_used"] is True
    assert result["safety_events"][0]["type"] == "combo_abort"
    assert runtime.joints["left"]["joint_1"] == 0.0


def test_executor_aligns_to_target_with_small_primitives(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.detection_reads = [
        {"detections": [{"camera_xyz_m": [0.18, -0.12, 0.18]}]},
        {"detections": [{"camera_xyz_m": [0.18, 0.0, 0.18]}]},
    ]
    registry = _make_registry(tmp_path)
    _save_primitive(
        registry,
        arm="left",
        primitive="close_upper_arm",
        magnitude="small",
        start_anchor="left_neutral_ready",
        joint_delta_deg={"joint_2": -10.0},
        end_region_hint="left_neutral_ready",
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.align_to_target("left", "tomato", max_iterations=2)

    assert result["success"] is True
    assert result["phase_results"][0]["primitive"] == "close_upper_arm"
    assert runtime.joints["left"]["joint_2"] == -10.0


def test_executor_descends_until_contact(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.tactile_reads = [
        {"contact": False, "stable_grasp": False},
        {"contact": False, "stable_grasp": False},
        {"contact": True, "stable_grasp": False},
    ]
    registry = _make_registry(tmp_path)
    _save_primitive(
        registry,
        arm="left",
        primitive="lower_forearm",
        magnitude="slight",
        start_anchor="left_chest_front",
        joint_delta_deg={"joint_4": -5.0},
        end_region_hint="left_front_mid",
    )
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.descend_until_contact("left", primitive="lower_forearm", magnitude="slight")

    assert result["success"] is True
    assert result["stopped_on_contact"] is True
    assert result["steps_executed"] == 2
    assert len(result["phase_results"]) == 2


def test_executor_grasps_with_tactile_guard(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    runtime.tactile_reads = [
        {"contact": False, "stable_grasp": False},
        {"contact": True, "stable_grasp": True},
    ]
    registry = _make_registry(tmp_path)
    executor = OpenArmMotionExecutor(runtime, registry)

    result = executor.grasp_with_tactile_guard("left")

    assert result["success"] is True
    assert result["contact_detected"] is True
    assert result["stable_grasp"] is True
    assert len(result["phase_results"]) == 2


def test_openarm_control_api_exposes_new_high_level_functions(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    registry = _make_registry(tmp_path)
    env = SimpleNamespace(
        runtime=runtime,
        asset_registry=registry,
        get_observation=runtime.get_observation,
    )
    api = OpenArmControlApi(env)
    functions = api.functions()

    for name in [
        "describe_scene",
        "get_tactile_health",
        "estimate_arm_region",
        "align_to_target",
        "approach_target",
        "descend_until_contact",
        "grasp_with_tactile_guard",
        "release_grasp",
        "handover_to_center",
    ]:
        assert name in functions
