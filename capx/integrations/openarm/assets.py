from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .catalog import DEFAULT_ANCHORS, DEFAULT_COMBOS, combo_catalog, primitive_catalog


@dataclass
class AnchorAsset:
    name: str
    arm_mode: str
    joints_by_arm: dict[str, dict[str, float]]
    region: str
    version: str = "v1"
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnchorAsset":
        return cls(
            name=str(payload["name"]),
            arm_mode=str(payload["arm_mode"]),
            joints_by_arm={
                str(arm): {str(k): float(v) for k, v in joints.items()}
                for arm, joints in dict(payload["joints_by_arm"]).items()
            },
            region=str(payload.get("region", payload["name"])),
            version=str(payload.get("version", "v1")),
            notes=str(payload.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PrimitiveTemplateAsset:
    id: str
    version: str
    arm: str
    primitive: str
    magnitude: str
    start_anchor: str
    allowed_start_anchors: list[str]
    primary_joint_group: str
    nominal_joint_delta_deg: dict[str, float]
    joint_delta_tolerance_deg: dict[str, float]
    nominal_ee_delta_base: list[float]
    nominal_ee_delta_local: list[float]
    end_region_hint: str
    default_step_count: int
    default_speed: str
    settle_time_ms: int
    timeout_ms: int
    guard_joint_margin_deg: float
    guard_max_step_delta_deg: float
    guard_max_ee_error_m: float
    guard_abort_on_tactile_contact: bool
    guard_abort_on_torque_spike: bool
    inverse_primitive: str
    recovery_anchor: str
    source_recording_id: str = ""
    operator: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PrimitiveTemplateAsset":
        return cls(
            id=str(payload["id"]),
            version=str(payload.get("version", "v1")),
            arm=str(payload["arm"]),
            primitive=str(payload["primitive"]),
            magnitude=str(payload["magnitude"]),
            start_anchor=str(payload["start_anchor"]),
            allowed_start_anchors=[str(item) for item in payload.get("allowed_start_anchors", [])],
            primary_joint_group=str(payload["primary_joint_group"]),
            nominal_joint_delta_deg={
                str(k): float(v) for k, v in dict(payload["nominal_joint_delta_deg"]).items()
            },
            joint_delta_tolerance_deg={
                str(k): float(v) for k, v in dict(payload.get("joint_delta_tolerance_deg", {})).items()
            },
            nominal_ee_delta_base=[float(v) for v in payload.get("nominal_ee_delta_base", [0.0, 0.0, 0.0])],
            nominal_ee_delta_local=[float(v) for v in payload.get("nominal_ee_delta_local", [0.0, 0.0, 0.0])],
            end_region_hint=str(payload.get("end_region_hint", "")),
            default_step_count=int(payload.get("default_step_count", 4)),
            default_speed=str(payload.get("default_speed", "slow")),
            settle_time_ms=int(payload.get("settle_time_ms", 120)),
            timeout_ms=int(payload.get("timeout_ms", 4000)),
            guard_joint_margin_deg=float(payload.get("guard_joint_margin_deg", 5.0)),
            guard_max_step_delta_deg=float(payload.get("guard_max_step_delta_deg", 10.0)),
            guard_max_ee_error_m=float(payload.get("guard_max_ee_error_m", 0.08)),
            guard_abort_on_tactile_contact=bool(payload.get("guard_abort_on_tactile_contact", False)),
            guard_abort_on_torque_spike=bool(payload.get("guard_abort_on_torque_spike", True)),
            inverse_primitive=str(payload["inverse_primitive"]),
            recovery_anchor=str(payload.get("recovery_anchor", payload["start_anchor"])),
            source_recording_id=str(payload.get("source_recording_id", "")),
            operator=str(payload.get("operator", "")),
            notes=str(payload.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComboPhaseAsset:
    primitive: str
    magnitude: str
    arm: str
    expected_region_after_phase: str = ""
    settle_time_ms: int = 100
    abort_on_contact: bool = False
    allow_skip_if_already_in_region: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ComboPhaseAsset":
        return cls(
            primitive=str(payload["primitive"]),
            magnitude=str(payload["magnitude"]),
            arm=str(payload.get("arm", "selected")),
            expected_region_after_phase=str(payload.get("expected_region_after_phase", "")),
            settle_time_ms=int(payload.get("settle_time_ms", 100)),
            abort_on_contact=bool(payload.get("abort_on_contact", False)),
            allow_skip_if_already_in_region=bool(
                payload.get("allow_skip_if_already_in_region", False)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComboTemplateAsset:
    id: str
    version: str
    combo: str
    arm_mode: str
    magnitude: str
    allowed_start_anchors: list[str]
    goal_region: str
    goal_pose_anchor: str | None
    default_speed: str
    phases: list[ComboPhaseAsset]
    phase_checkpoints: list[dict[str, Any]] = field(default_factory=list)
    completion_rule: dict[str, Any] = field(default_factory=dict)
    abort_rule: dict[str, Any] = field(default_factory=dict)
    recovery_anchor: str = ""
    source_recording_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ComboTemplateAsset":
        return cls(
            id=str(payload["id"]),
            version=str(payload.get("version", "v1")),
            combo=str(payload["combo"]),
            arm_mode=str(payload["arm_mode"]),
            magnitude=_infer_combo_magnitude(payload),
            allowed_start_anchors=[str(item) for item in payload.get("allowed_start_anchors", [])],
            goal_region=str(payload.get("goal_region", "")),
            goal_pose_anchor=payload.get("goal_pose_anchor"),
            default_speed=str(payload.get("default_speed", "slow")),
            phases=[ComboPhaseAsset.from_dict(item) for item in payload.get("phases", [])],
            phase_checkpoints=[dict(item) for item in payload.get("phase_checkpoints", [])],
            completion_rule=dict(payload.get("completion_rule", {})),
            abort_rule=dict(payload.get("abort_rule", {})),
            recovery_anchor=str(payload.get("recovery_anchor", "")),
            source_recording_ids=[str(item) for item in payload.get("source_recording_ids", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["phases"] = [phase.to_dict() for phase in self.phases]
        return payload


class OpenArmMotionAssetRegistry:
    def __init__(self, asset_root: Path | None = None) -> None:
        self.asset_root = asset_root or (Path(__file__).resolve().parents[2] / "assets" / "openarm")
        self.anchor_root = self.asset_root / "anchors"
        self.primitive_root = self.asset_root / "primitives"
        self.combo_root = self.asset_root / "combos"
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self.anchor_root.mkdir(parents=True, exist_ok=True)
        self.primitive_root.mkdir(parents=True, exist_ok=True)
        self.combo_root.mkdir(parents=True, exist_ok=True)

    def get_motion_primitive_catalog(self) -> list[dict[str, object]]:
        return primitive_catalog()

    def get_motion_combo_catalog(self) -> list[dict[str, object]]:
        return combo_catalog()

    def save_anchor(self, anchor: AnchorAsset) -> Path:
        path = self.anchor_root / f"{anchor.name}.{anchor.version}.yaml"
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(anchor.to_dict(), fh, sort_keys=False, allow_unicode=True)
        return path

    def load_anchor(self, name: str, version: str = "v1") -> AnchorAsset:
        path = self.anchor_root / f"{name}.{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Anchor asset not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return AnchorAsset.from_dict(yaml.safe_load(fh) or {})

    def list_anchors(self) -> list[AnchorAsset]:
        assets: list[AnchorAsset] = []
        for path in sorted(self.anchor_root.glob("*.yaml")):
            with path.open("r", encoding="utf-8") as fh:
                assets.append(AnchorAsset.from_dict(yaml.safe_load(fh) or {}))
        return assets

    def save_primitive_template(self, template: PrimitiveTemplateAsset) -> Path:
        path = self._primitive_template_path(
            primitive=template.primitive,
            arm=template.arm,
            start_anchor=template.start_anchor,
            magnitude=template.magnitude,
            version=template.version,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(template.to_dict(), fh, sort_keys=False, allow_unicode=True)
        return path

    def load_primitive_template(
        self,
        primitive: str,
        arm: str,
        start_anchor: str,
        magnitude: str,
        version: str = "v1",
    ) -> PrimitiveTemplateAsset:
        path = self._primitive_template_path(
            primitive=primitive,
            arm=arm,
            start_anchor=start_anchor,
            magnitude=magnitude,
            version=version,
        )
        if not path.exists():
            raise FileNotFoundError(f"Primitive template not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return PrimitiveTemplateAsset.from_dict(yaml.safe_load(fh) or {})

    def find_primitive_template(
        self,
        primitive: str,
        arm: str,
        magnitude: str,
        candidate_start_anchors: list[str],
        version: str = "v1",
    ) -> PrimitiveTemplateAsset:
        errors: list[str] = []
        for start_anchor in candidate_start_anchors:
            try:
                return self.load_primitive_template(
                    primitive=primitive,
                    arm=arm,
                    start_anchor=start_anchor,
                    magnitude=magnitude,
                    version=version,
                )
            except FileNotFoundError as exc:
                errors.append(str(exc))
        joined = "\n".join(errors) if errors else "No candidate anchors provided."
        raise FileNotFoundError(joined)

    def save_combo_template(self, template: ComboTemplateAsset) -> Path:
        path = self._combo_template_path(
            combo=template.combo,
            arm_mode=template.arm_mode,
            magnitude=template.magnitude,
            version=template.version,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(template.to_dict(), fh, sort_keys=False, allow_unicode=True)
        return path

    def load_combo_template(
        self,
        combo: str,
        arm_mode: str,
        magnitude: str,
        version: str = "v1",
    ) -> ComboTemplateAsset:
        path = self._combo_template_path(
            combo=combo,
            arm_mode=arm_mode,
            magnitude=magnitude,
            version=version,
        )
        if not path.exists():
            raise FileNotFoundError(f"Combo template not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return ComboTemplateAsset.from_dict(yaml.safe_load(fh) or {})

    def list_primitive_templates(self, primitive: str | None = None) -> list[PrimitiveTemplateAsset]:
        assets: list[PrimitiveTemplateAsset] = []
        paths = self._iter_asset_paths(self.primitive_root, primitive)
        for path in paths:
            with path.open("r", encoding="utf-8") as fh:
                assets.append(PrimitiveTemplateAsset.from_dict(yaml.safe_load(fh) or {}))
        return assets

    def list_combo_templates(self, combo: str | None = None) -> list[ComboTemplateAsset]:
        assets: list[ComboTemplateAsset] = []
        paths = self._iter_asset_paths(self.combo_root, combo)
        for path in paths:
            with path.open("r", encoding="utf-8") as fh:
                assets.append(ComboTemplateAsset.from_dict(yaml.safe_load(fh) or {}))
        return assets

    def bootstrap_combo_templates(
        self,
        *,
        magnitude: str = "medium",
        overwrite: bool = False,
    ) -> list[Path]:
        paths: list[Path] = []
        for combo_name, definition in DEFAULT_COMBOS.items():
            path = self._combo_template_path(
                combo=combo_name,
                arm_mode=definition.arm_mode,
                magnitude=magnitude,
                version="v1",
            )
            if path.exists() and not overwrite:
                continue
            template = ComboTemplateAsset(
                id=f"combo.{definition.arm_mode}.{combo_name}.{magnitude}.v1",
                version="v1",
                combo=combo_name,
                arm_mode=definition.arm_mode,
                magnitude=magnitude,
                allowed_start_anchors=definition.allowed_start_anchors,
                goal_region=definition.goal_region,
                goal_pose_anchor=None,
                default_speed="slow",
                phases=[
                    ComboPhaseAsset(
                        primitive=phase["primitive"],
                        magnitude=phase["magnitude"],
                        arm="selected" if definition.arm_mode == "single" else "both",
                    )
                    for phase in definition.default_phases
                ],
                completion_rule={"goal_region": definition.goal_region},
                abort_rule={"on_guard_violation": True},
                recovery_anchor="safe_standby",
            )
            paths.append(self.save_combo_template(template))
        return paths

    def get_recording_status(self) -> dict[str, Any]:
        anchors = self.list_anchors()
        primitives = self.list_primitive_templates()
        combos = self.list_combo_templates()
        anchor_names = {anchor.name for anchor in anchors}
        combo_keys = {
            f"{template.arm_mode}:{template.combo}:{template.magnitude}"
            for template in combos
        }
        expected_combo_keys = {
            f"{definition.arm_mode}:{combo_name}:medium"
            for combo_name, definition in DEFAULT_COMBOS.items()
        }
        return {
            "asset_root": str(self.asset_root),
            "anchor_count": len(anchors),
            "anchors_recorded": sorted(anchor_names),
            "anchors_missing": [name for name in DEFAULT_ANCHORS if name not in anchor_names],
            "primitive_template_count": len(primitives),
            "primitive_template_ids": sorted(template.id for template in primitives),
            "combo_template_count": len(combos),
            "combo_template_ids": sorted(template.id for template in combos),
            "combo_templates_missing": sorted(expected_combo_keys - combo_keys),
        }

    def find_closest_anchor(
        self,
        arm: str,
        current_joints: dict[str, float],
        candidate_anchors: list[str] | None = None,
    ) -> tuple[AnchorAsset | None, float]:
        candidates: list[tuple[AnchorAsset, float]] = []
        for anchor in self.list_anchors():
            if arm not in anchor.joints_by_arm:
                continue
            if candidate_anchors and anchor.name not in candidate_anchors:
                continue
            anchor_joints = anchor.joints_by_arm[arm]
            common_names = sorted(set(anchor_joints).intersection(current_joints))
            if not common_names:
                continue
            distance = float(
                np.linalg.norm(
                    np.array([current_joints[name] - anchor_joints[name] for name in common_names])
                )
            )
            candidates.append((anchor, distance))
        if not candidates:
            return None, float("inf")
        return min(candidates, key=lambda item: item[1])

    def _primitive_template_path(
        self,
        *,
        primitive: str,
        arm: str,
        start_anchor: str,
        magnitude: str,
        version: str,
    ) -> Path:
        folder = self.primitive_root / primitive
        filename = f"{arm}.{start_anchor}.{magnitude}.{version}.yaml"
        return folder / filename

    def _combo_template_path(
        self,
        *,
        combo: str,
        arm_mode: str,
        magnitude: str,
        version: str,
    ) -> Path:
        folder = self.combo_root / combo
        filename = f"{arm_mode}.{magnitude}.{version}.yaml"
        return folder / filename

    def _iter_asset_paths(self, root: Path, category: str | None = None) -> list[Path]:
        if category:
            target = root / category
            if not target.exists():
                return []
            return sorted(target.glob("*.yaml"))
        return sorted(root.glob("*/*.yaml"))


def _infer_combo_magnitude(payload: dict[str, Any]) -> str:
    if "magnitude" in payload:
        return str(payload["magnitude"])
    asset_id = payload.get("id")
    if isinstance(asset_id, str):
        parts = asset_id.split(".")
        if len(parts) >= 5:
            return parts[-2]
    phases = payload.get("phases", [])
    if phases:
        first = phases[0]
        if isinstance(first, dict) and "magnitude" in first:
            return str(first["magnitude"])
    return "medium"
