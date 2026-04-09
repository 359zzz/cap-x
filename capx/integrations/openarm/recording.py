from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .assets import (
    AnchorAsset,
    ComboPhaseAsset,
    ComboTemplateAsset,
    OpenArmMotionAssetRegistry,
    PrimitiveTemplateAsset,
)
from .catalog import DEFAULT_COMBOS, DEFAULT_PRIMITIVES
from .runtime import OpenArmRuntime


@dataclass
class RecordingResult:
    path: str
    asset_id: str
    details: dict[str, Any]


class ManualOpenArmRecorder:
    def __init__(self, runtime: OpenArmRuntime, registry: OpenArmMotionAssetRegistry) -> None:
        self.runtime = runtime
        self.registry = registry

    def record_anchor(
        self,
        name: str,
        *,
        arm_mode: str = "both",
        arm: str | None = None,
        notes: str = "",
    ) -> RecordingResult:
        self.runtime.ensure_connected()
        if arm_mode == "single":
            if arm is None:
                raise ValueError("arm must be provided when arm_mode='single'")
            joints_by_arm = {arm: self.runtime.get_arm_joint_positions(arm)}
        else:
            joints_by_arm = {
                "left": self.runtime.get_arm_joint_positions("left"),
                "right": self.runtime.get_arm_joint_positions("right"),
            }
        asset = AnchorAsset(
            name=name,
            arm_mode=arm_mode,
            joints_by_arm=joints_by_arm,
            region=name,
            notes=notes,
        )
        path = self.registry.save_anchor(asset)
        return RecordingResult(path=str(path), asset_id=name, details=asset.to_dict())

    def record_primitive_template(
        self,
        *,
        arm: str,
        primitive: str,
        magnitude: str,
        start_anchor: str,
        end_region_hint: str = "",
        notes: str = "",
    ) -> RecordingResult:
        self.runtime.ensure_connected()
        if primitive not in DEFAULT_PRIMITIVES:
            raise KeyError(f"Unknown primitive '{primitive}'")
        start = self.registry.load_anchor(start_anchor)
        if arm not in start.joints_by_arm:
            raise KeyError(f"Anchor '{start_anchor}' does not contain arm '{arm}'")
        current = self.runtime.get_arm_joint_positions(arm)
        start_joints = start.joints_by_arm[arm]
        delta = {
            joint: float(current.get(joint, start_value) - start_value)
            for joint, start_value in start_joints.items()
            if joint in current
        }
        definition = DEFAULT_PRIMITIVES[primitive]
        template = PrimitiveTemplateAsset(
            id=f"primitive.{arm}.{start_anchor}.{primitive}.{magnitude}.v1",
            version="v1",
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            start_anchor=start_anchor,
            allowed_start_anchors=[start_anchor],
            primary_joint_group=definition.primary_joint_group,
            nominal_joint_delta_deg=delta,
            joint_delta_tolerance_deg={joint: 3.0 for joint in delta},
            nominal_ee_delta_base=[0.0, 0.0, 0.0],
            nominal_ee_delta_local=[0.0, 0.0, 0.0],
            end_region_hint=end_region_hint or start_anchor,
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
            notes=notes,
        )
        path = self.registry.save_primitive_template(template)
        return RecordingResult(path=str(path), asset_id=template.id, details=template.to_dict())

    def record_combo_template(
        self,
        *,
        combo: str,
        arm_mode: str,
        magnitude: str,
        recovery_anchor: str,
        arm: str = "selected",
    ) -> RecordingResult:
        if combo not in DEFAULT_COMBOS:
            raise KeyError(f"Unknown combo '{combo}'")
        definition = DEFAULT_COMBOS[combo]
        template = ComboTemplateAsset(
            id=f"combo.{arm_mode}.{combo}.{magnitude}.v1",
            version="v1",
            combo=combo,
            arm_mode=arm_mode,
            magnitude=magnitude,
            allowed_start_anchors=definition.allowed_start_anchors,
            goal_region=definition.goal_region,
            goal_pose_anchor=None,
            default_speed="slow",
            phases=[
                ComboPhaseAsset(
                    primitive=phase["primitive"],
                    magnitude=phase["magnitude"],
                    arm=arm,
                )
                for phase in definition.default_phases
            ],
            completion_rule={"goal_region": definition.goal_region},
            abort_rule={"on_guard_violation": True},
            recovery_anchor=recovery_anchor,
        )
        path = self.registry.save_combo_template(template)
        return RecordingResult(path=str(path), asset_id=template.id, details=template.to_dict())
