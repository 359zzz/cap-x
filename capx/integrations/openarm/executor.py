from __future__ import annotations

from typing import Any

from .assets import ComboTemplateAsset, OpenArmMotionAssetRegistry, PrimitiveTemplateAsset
from .catalog import DEFAULT_COMBOS, DEFAULT_PRIMITIVES
from .runtime import OpenArmRuntime


class OpenArmMotionExecutor:
    def __init__(self, runtime: OpenArmRuntime, registry: OpenArmMotionAssetRegistry) -> None:
        self.runtime = runtime
        self.registry = registry
        self._last_motion_by_arm: dict[str, dict[str, Any]] = {}

    def get_motion_primitive_catalog(self) -> list[dict[str, object]]:
        return self.registry.get_motion_primitive_catalog()

    def get_motion_combo_catalog(self) -> list[dict[str, object]]:
        return self.registry.get_motion_combo_catalog()

    def get_robot_state(self) -> dict[str, Any]:
        return self.runtime.get_robot_state()

    def move_to_named_pose(self, name: str, *, speed: str = "slow") -> dict[str, Any]:
        with self.runtime.active_task(f"move_to_named_pose:{name}"):
            return self._move_to_named_pose_unlocked(name, speed=speed)

    def move_arm_joints_safe(
        self,
        arm: str,
        joints: dict[str, float],
        *,
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"move_arm_joints_safe:{arm}"):
            final = self.runtime.move_arm_joints_blocking(arm, joints, speed=speed)
            return {
                "success": True,
                "arm": arm,
                "final_joints": final,
            }

    def execute_motion_primitive(
        self,
        arm: str,
        primitive: str,
        magnitude: str = "medium",
        *,
        speed: str = "slow",
    ) -> dict[str, Any]:
        if primitive not in DEFAULT_PRIMITIVES:
            raise KeyError(f"Unknown primitive '{primitive}'")
        with self.runtime.active_task(f"primitive:{arm}:{primitive}:{magnitude}"):
            return self._execute_motion_primitive_unlocked(
                arm=arm,
                primitive=primitive,
                magnitude=magnitude,
                speed=speed,
            )

    def execute_bimanual_primitive(
        self,
        primitive: str,
        magnitude: str = "medium",
        *,
        symmetry: str = "mirror",
        speed: str = "slow",
    ) -> dict[str, Any]:
        if primitive not in DEFAULT_PRIMITIVES:
            raise KeyError(f"Unknown primitive '{primitive}'")
        del symmetry
        with self.runtime.active_task(f"bimanual_primitive:{primitive}:{magnitude}"):
            return self._execute_bimanual_primitive_unlocked(
                primitive=primitive,
                magnitude=magnitude,
                speed=speed,
            )

    def execute_motion_combo(
        self,
        name: str,
        *,
        arm: str | None = None,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        if name not in DEFAULT_COMBOS:
            raise KeyError(f"Unknown combo '{name}'")
        with self.runtime.active_task(f"combo:{name}:{arm}:{magnitude}"):
            return self._execute_motion_combo_unlocked(
                name=name,
                arm=arm,
                magnitude=magnitude,
                speed=speed,
            )

    def undo_last_motion(self, arm: str) -> dict[str, Any]:
        last = self._last_motion_by_arm.get(arm)
        if last is None:
            raise RuntimeError(f"No previous motion recorded for arm '{arm}'")
        inverse_primitive = DEFAULT_PRIMITIVES[last["primitive"]].inverse_primitive
        return self.execute_motion_primitive(
            arm=arm,
            primitive=inverse_primitive,
            magnitude=last["magnitude"],
            speed="slow",
        )

    def detect_target(self, target_name: str, *, top_k: int = 3) -> dict[str, Any]:
        return self.runtime.detect_target(target_name, top_k=top_k)

    def describe_scene(self, prompt: str | None = None) -> dict[str, Any]:
        return self.runtime.describe_scene(prompt)

    def get_target_pose(self, target_name: str) -> dict[str, Any]:
        detection = self.runtime.detect_target(target_name, top_k=1)
        detections = detection.get("detections", [])
        if not detections:
            return {"success": False, "target_name": target_name, "camera_xyz_m": None}
        best = detections[0]
        return {
            "success": True,
            "target_name": target_name,
            "camera_xyz_m": best.get("camera_xyz_m"),
            "depth_m": best.get("depth_m"),
            "pixel_center": best.get("pixel_center"),
        }

    def read_tactile(self) -> dict[str, Any]:
        return self.runtime.read_tactile()

    def get_tactile_health(self) -> dict[str, Any]:
        return self.runtime.get_tactile_health()

    def estimate_arm_region(self, arm: str) -> dict[str, Any]:
        current_joints = self.runtime.get_arm_joint_positions(arm)
        anchor, distance = self.registry.find_closest_anchor(
            arm=arm,
            current_joints=current_joints,
        )
        if anchor is None:
            return {
                "success": False,
                "arm": arm,
                "region": None,
                "anchor": None,
                "joint_distance": None,
            }
        return {
            "success": True,
            "arm": arm,
            "region": anchor.region,
            "anchor": anchor.name,
            "joint_distance": distance,
        }

    def align_to_target(
        self,
        arm: str,
        target_name: str,
        *,
        max_iterations: int = 3,
        lateral_tolerance_m: float = 0.05,
        vertical_tolerance_m: float = 0.05,
        depth_tolerance_m: float = 0.08,
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"align_to_target:{arm}:{target_name}"):
            return self._align_to_target_unlocked(
                arm=arm,
                target_name=target_name,
                max_iterations=max_iterations,
                lateral_tolerance_m=lateral_tolerance_m,
                vertical_tolerance_m=vertical_tolerance_m,
                depth_tolerance_m=depth_tolerance_m,
                speed=speed,
            )

    def approach_target(
        self,
        arm: str,
        target_name: str,
        *,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"approach_target:{arm}:{target_name}"):
            phase_results: list[dict[str, Any]] = []
            pose = self.get_target_pose(target_name)
            if not pose.get("success"):
                return {
                    "success": False,
                    "arm": arm,
                    "target_name": target_name,
                    "phase_results": phase_results,
                    "reason": "target_not_found",
                }

            phase_results.append(
                self._execute_motion_combo_unlocked(
                    name="hand_to_chest",
                    arm=arm,
                    magnitude=magnitude,
                    speed=speed,
                )
            )
            phase_results.append(
                self._execute_motion_combo_unlocked(
                    name="wrist_upright",
                    arm=arm,
                    magnitude="small",
                    speed=speed,
                )
            )

            camera_xyz = pose.get("camera_xyz_m") or [0.0, 0.0, 0.0]
            if camera_xyz[0] >= 0.18:
                phase_results.append(
                    self._execute_motion_combo_unlocked(
                        name="hand_forward_present",
                        arm=arm,
                        magnitude=magnitude,
                        speed=speed,
                    )
                )

            alignment = self._align_to_target_unlocked(
                arm=arm,
                target_name=target_name,
                max_iterations=2,
                lateral_tolerance_m=0.05,
                vertical_tolerance_m=0.05,
                depth_tolerance_m=0.10,
                speed=speed,
            )
            phase_results.append(alignment)
            final_pose = self.get_target_pose(target_name)
            return {
                "success": bool(alignment.get("success")),
                "arm": arm,
                "target_name": target_name,
                "phase_results": phase_results,
                "final_pose": final_pose,
            }

    def descend_until_contact(
        self,
        arm: str,
        *,
        primitive: str = "lower_forearm",
        magnitude: str = "slight",
        max_steps: int = 4,
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"descend_until_contact:{arm}:{primitive}:{magnitude}"):
            tactile_history: list[dict[str, Any]] = []
            phase_results: list[dict[str, Any]] = []
            for step_index in range(1, max_steps + 1):
                tactile = self.read_tactile()
                tactile_history.append(tactile)
                if self._tactile_contact_detected(tactile):
                    return {
                        "success": True,
                        "arm": arm,
                        "stopped_on_contact": True,
                        "steps_executed": step_index - 1,
                        "phase_results": phase_results,
                        "tactile_history": tactile_history,
                    }
                phase_results.append(
                    self._execute_motion_primitive_unlocked(
                        arm=arm,
                        primitive=primitive,
                        magnitude=magnitude,
                        speed=speed,
                    )
                )

            tactile = self.read_tactile()
            tactile_history.append(tactile)
            return {
                "success": self._tactile_contact_detected(tactile),
                "arm": arm,
                "stopped_on_contact": self._tactile_contact_detected(tactile),
                "steps_executed": len(phase_results),
                "phase_results": phase_results,
                "tactile_history": tactile_history,
            }

    def grasp_with_tactile_guard(
        self,
        arm: str,
        *,
        close_sequence: list[str] | None = None,
        stop_on_stable_grasp: bool = True,
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"grasp_with_tactile_guard:{arm}"):
            magnitudes = close_sequence or ["slight", "small", "medium", "large"]
            tactile_history: list[dict[str, Any]] = []
            phase_results: list[dict[str, Any]] = []

            for magnitude in magnitudes:
                phase_results.append(
                    self._execute_motion_primitive_unlocked(
                        arm=arm,
                        primitive="close_gripper",
                        magnitude=magnitude,
                        speed=speed,
                    )
                )
                tactile = self.read_tactile()
                tactile_history.append(tactile)
                if self._tactile_contact_detected(tactile):
                    stable = bool(tactile.get("stable_grasp", False))
                    return {
                        "success": True if (stable or not stop_on_stable_grasp) else False,
                        "arm": arm,
                        "contact_detected": True,
                        "stable_grasp": stable,
                        "phase_results": phase_results,
                        "tactile_history": tactile_history,
                    }

            return {
                "success": False,
                "arm": arm,
                "contact_detected": False,
                "stable_grasp": False,
                "phase_results": phase_results,
                "tactile_history": tactile_history,
            }

    def release_grasp(
        self,
        arm: str,
        *,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        with self.runtime.active_task(f"release_grasp:{arm}:{magnitude}"):
            result = self._execute_motion_primitive_unlocked(
                arm=arm,
                primitive="open_gripper",
                magnitude=magnitude,
                speed=speed,
            )
            result["released"] = True
            return result

    def handover_to_center(
        self,
        arm: str,
        *,
        receive_mode: bool = False,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        combo = "handover_receive_ready" if receive_mode else "handover_give_ready"
        with self.runtime.active_task(f"handover_to_center:{arm}:{combo}:{magnitude}"):
            result = self._execute_motion_combo_unlocked(
                name=combo,
                arm=arm,
                magnitude=magnitude,
                speed=speed,
            )
            result["receive_mode"] = receive_mode
            return result

    def stop_robot(self) -> dict[str, Any]:
        self.runtime.stop_motion()
        return {"success": True, "task_state": self.runtime.task_state}

    def set_gripper_fraction(self, arm: str, fraction: float) -> dict[str, Any]:
        position = self.runtime.set_gripper_fraction(arm, fraction)
        return {"success": True, "arm": arm, "gripper_position": position}

    def _execute_motion_primitive_unlocked(
        self,
        *,
        arm: str,
        primitive: str,
        magnitude: str,
        speed: str,
    ) -> dict[str, Any]:
        current_joints = self.runtime.get_arm_joint_positions(arm)
        if primitive in {"open_gripper", "close_gripper"}:
            position = self.runtime.set_gripper_by_magnitude(arm, primitive, magnitude)
            result = self._make_gripper_result(arm, primitive, magnitude, position)
            self._last_motion_by_arm[arm] = result
            return result

        template = self._load_primitive_template_for_current_state(
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            current_joints=current_joints,
        )
        current_joints = self._move_arm_to_template_start_if_needed(
            arm=arm,
            current_joints=current_joints,
            template=template,
        )

        target_joints = {
            joint: float(current_joints.get(joint, 0.0) + delta)
            for joint, delta in template.nominal_joint_delta_deg.items()
        }
        final_joints = self.runtime.move_arm_joints_blocking(arm, target_joints, speed=speed)
        result = {
            "success": True,
            "arm": arm,
            "primitive": primitive,
            "magnitude": magnitude,
            "start_anchor": template.start_anchor,
            "final_region": template.end_region_hint,
            "executed_steps": template.default_step_count,
            "joint_delta_deg": template.nominal_joint_delta_deg,
            "ee_delta_base": template.nominal_ee_delta_base,
            "safety_events": [],
            "recovery_used": False,
            "final_joints": final_joints,
        }
        self._last_motion_by_arm[arm] = result
        return result

    def _execute_bimanual_primitive_unlocked(
        self,
        *,
        primitive: str,
        magnitude: str,
        speed: str,
    ) -> dict[str, Any]:
        if primitive in {"open_gripper", "close_gripper"}:
            left_position = self.runtime.set_gripper_by_magnitude("left", primitive, magnitude)
            right_position = self.runtime.set_gripper_by_magnitude("right", primitive, magnitude)
            left = self._make_gripper_result("left", primitive, magnitude, left_position)
            right = self._make_gripper_result("right", primitive, magnitude, right_position)
            self._last_motion_by_arm["left"] = left
            self._last_motion_by_arm["right"] = right
            return {"success": True, "primitive": primitive, "magnitude": magnitude, "left": left, "right": right}

        left_current = self.runtime.get_arm_joint_positions("left")
        right_current = self.runtime.get_arm_joint_positions("right")
        left_template = self._load_primitive_template_for_current_state(
            arm="left",
            primitive=primitive,
            magnitude=magnitude,
            current_joints=left_current,
        )
        right_template = self._load_primitive_template_for_current_state(
            arm="right",
            primitive=primitive,
            magnitude=magnitude,
            current_joints=right_current,
        )
        left_start_target = self._start_anchor_target_if_needed("left", left_current, left_template)
        right_start_target = self._start_anchor_target_if_needed("right", right_current, right_template)
        if left_start_target and right_start_target:
            start_joints = self.runtime.move_both_arms_blocking(
                left_start_target,
                right_start_target,
                speed="slow",
            )
            left_current = start_joints["left"]
            right_current = start_joints["right"]
        elif left_start_target:
            left_current = self.runtime.move_arm_joints_blocking("left", left_start_target, speed="slow")
        elif right_start_target:
            right_current = self.runtime.move_arm_joints_blocking("right", right_start_target, speed="slow")

        left_target = {
            joint: float(left_current.get(joint, 0.0) + delta)
            for joint, delta in left_template.nominal_joint_delta_deg.items()
        }
        right_target = {
            joint: float(right_current.get(joint, 0.0) + delta)
            for joint, delta in right_template.nominal_joint_delta_deg.items()
        }
        final_joints = self.runtime.move_both_arms_blocking(left_target, right_target, speed=speed)
        left = {
            "success": True,
            "arm": "left",
            "primitive": primitive,
            "magnitude": magnitude,
            "start_anchor": left_template.start_anchor,
            "final_region": left_template.end_region_hint,
            "executed_steps": left_template.default_step_count,
            "joint_delta_deg": left_template.nominal_joint_delta_deg,
            "ee_delta_base": left_template.nominal_ee_delta_base,
            "safety_events": [],
            "recovery_used": False,
            "final_joints": final_joints["left"],
        }
        right = {
            "success": True,
            "arm": "right",
            "primitive": primitive,
            "magnitude": magnitude,
            "start_anchor": right_template.start_anchor,
            "final_region": right_template.end_region_hint,
            "executed_steps": right_template.default_step_count,
            "joint_delta_deg": right_template.nominal_joint_delta_deg,
            "ee_delta_base": right_template.nominal_ee_delta_base,
            "safety_events": [],
            "recovery_used": False,
            "final_joints": final_joints["right"],
        }
        self._last_motion_by_arm["left"] = left
        self._last_motion_by_arm["right"] = right
        return {"success": True, "primitive": primitive, "magnitude": magnitude, "left": left, "right": right}

    def _load_primitive_template_for_current_state(
        self,
        *,
        arm: str,
        primitive: str,
        magnitude: str,
        current_joints: dict[str, float],
    ) -> PrimitiveTemplateAsset:
        definition = DEFAULT_PRIMITIVES[primitive]
        matching_anchors = self._expand_anchor_patterns(arm, definition.allowed_start_anchors)
        if not matching_anchors:
            matching_anchors = [f"{arm}_neutral_ready"]
        nearest_anchor, _ = self.registry.find_closest_anchor(
            arm=arm,
            current_joints=current_joints,
            candidate_anchors=matching_anchors,
        )
        candidate_names = [nearest_anchor.name] if nearest_anchor is not None else matching_anchors
        try:
            return self.registry.find_primitive_template(
                primitive=primitive,
                arm=arm,
                magnitude=magnitude,
                candidate_start_anchors=candidate_names + matching_anchors,
            )
        except FileNotFoundError as exc:
            anchors = ", ".join(dict.fromkeys(candidate_names + matching_anchors))
            raise FileNotFoundError(
                "Missing OpenArm primitive template. "
                f"Record `{primitive}` for arm `{arm}` with magnitude `{magnitude}` "
                f"from one of these anchors: {anchors}."
            ) from exc

    def _load_or_build_combo_template(
        self,
        *,
        name: str,
        arm_mode: str,
        magnitude: str,
    ) -> ComboTemplateAsset:
        try:
            return self.registry.load_combo_template(name, arm_mode=arm_mode, magnitude=magnitude)
        except FileNotFoundError:
            definition = DEFAULT_COMBOS[name]
            return ComboTemplateAsset(
                id=f"combo.{arm_mode}.{name}.{magnitude}.v1",
                version="v1",
                combo=name,
                arm_mode=arm_mode,
                magnitude=magnitude,
                allowed_start_anchors=definition.allowed_start_anchors,
                goal_region=definition.goal_region,
                goal_pose_anchor=None,
                default_speed="slow",
                phases=[
                    self._phase_from_definition(phase)
                    for phase in definition.default_phases
                ],
                completion_rule={"goal_region": definition.goal_region},
                abort_rule={"on_guard_violation": True},
                recovery_anchor="safe_standby",
            )

    def _move_to_named_pose_unlocked(self, name: str, *, speed: str = "slow") -> dict[str, Any]:
        anchor = self.registry.load_anchor(name)
        if anchor.arm_mode == "single":
            arm, joints = next(iter(anchor.joints_by_arm.items()))
            final = self.runtime.move_arm_joints_blocking(arm, joints, speed=speed)
            return {
                "success": True,
                "anchor": name,
                "arm_mode": "single",
                "final_joints": {arm: final},
            }
        final = self.runtime.move_both_arms_blocking(
            anchor.joints_by_arm.get("left", {}),
            anchor.joints_by_arm.get("right", {}),
            speed=speed,
        )
        return {"success": True, "anchor": name, "arm_mode": "both", "final_joints": final}

    def _execute_motion_combo_unlocked(
        self,
        *,
        name: str,
        arm: str | None,
        magnitude: str,
        speed: str,
    ) -> dict[str, Any]:
        definition = DEFAULT_COMBOS[name]
        arm_mode = "both" if definition.arm_mode == "both" else "single"
        template = self._load_or_build_combo_template(
            name=name,
            arm_mode=arm_mode,
            magnitude=magnitude,
        )
        executed: list[dict[str, Any]] = []
        checkpoint_results: list[dict[str, Any]] = []
        safety_events: list[dict[str, Any]] = []
        recovery_used = False
        error_message: str | None = None

        try:
            if arm_mode == "both":
                for phase_index, phase in enumerate(template.phases):
                    if phase.abort_on_contact:
                        tactile = self.read_tactile()
                        if self._tactile_contact_detected(tactile):
                            raise RuntimeError(
                                f"contact detected before phase {phase_index}:{phase.primitive}"
                            )
                    result = self._execute_bimanual_primitive_unlocked(
                        primitive=phase.primitive,
                        magnitude=phase.magnitude,
                        speed=speed,
                    )
                    executed.append(result)
                    checkpoint_results.append(
                        {
                            "phase_index": phase_index,
                            "primitive": phase.primitive,
                            "expected_region": phase.expected_region_after_phase or None,
                            "matched": True,
                            "skipped": False,
                        }
                    )
            else:
                selected_arm = arm or "left"
                for phase_index, phase in enumerate(template.phases):
                    phase_arm = selected_arm if phase.arm == "selected" else phase.arm
                    expected_region = self._normalize_region(phase.expected_region_after_phase, phase_arm)
                    current_region = self.estimate_arm_region(phase_arm).get("region")
                    if (
                        phase.allow_skip_if_already_in_region
                        and expected_region
                        and current_region == expected_region
                    ):
                        checkpoint_results.append(
                            {
                                "phase_index": phase_index,
                                "primitive": phase.primitive,
                                "expected_region": expected_region,
                                "matched": True,
                                "skipped": True,
                            }
                        )
                        continue

                    if phase.abort_on_contact:
                        tactile = self.read_tactile()
                        if self._tactile_contact_detected(tactile):
                            raise RuntimeError(
                                f"contact detected before phase {phase_index}:{phase.primitive}"
                            )

                    result = self._execute_motion_primitive_unlocked(
                        arm=phase_arm,
                        primitive=phase.primitive,
                        magnitude=phase.magnitude,
                        speed=speed,
                    )
                    executed.append(result)
                    current_region = self.estimate_arm_region(phase_arm).get("region")
                    checkpoint_results.append(
                        {
                            "phase_index": phase_index,
                            "primitive": phase.primitive,
                            "expected_region": expected_region,
                            "matched": (current_region == expected_region) if expected_region else True,
                            "skipped": False,
                            "current_region": current_region,
                        }
                    )
                    if phase.abort_on_contact:
                        tactile = self.read_tactile()
                        if self._tactile_contact_detected(tactile):
                            raise RuntimeError(
                                f"contact detected after phase {phase_index}:{phase.primitive}"
                            )
        except Exception as exc:
            error_message = str(exc)
            safety_events.append({"type": "combo_abort", "message": error_message})
            if template.recovery_anchor:
                self._move_to_named_pose_unlocked(template.recovery_anchor, speed="slow")
                recovery_used = True

        success = (
            error_message is None
            and self._combo_completion_satisfied(
                template=template,
                arm=arm if arm_mode == "single" else None,
            )
        )
        if not success and error_message is None and template.abort_rule.get("recover_on_completion_failure", False):
            safety_events.append(
                {
                    "type": "completion_check_failed",
                    "message": f"goal region not satisfied for combo {name}",
                }
            )
            if template.recovery_anchor:
                self._move_to_named_pose_unlocked(template.recovery_anchor, speed="slow")
                recovery_used = True

        return {
            "success": success,
            "combo": name,
            "arm": arm if arm_mode == "single" else "both",
            "magnitude": magnitude,
            "final_region": template.goal_region,
            "executed_primitives": [
                item.get("primitive", item.get("left", {}).get("primitive"))
                for item in executed
            ],
            "phase_results": executed,
            "checkpoint_results": checkpoint_results,
            "safety_events": safety_events,
            "recovery_used": recovery_used,
            "error": error_message,
        }

    def _phase_from_definition(self, phase: dict[str, str]) -> Any:
        from .assets import ComboPhaseAsset

        return ComboPhaseAsset(
            primitive=phase["primitive"],
            magnitude=phase["magnitude"],
            arm="selected",
        )

    def _move_arm_to_template_start_if_needed(
        self,
        *,
        arm: str,
        current_joints: dict[str, float],
        template: PrimitiveTemplateAsset,
    ) -> dict[str, float]:
        start_target = self._start_anchor_target_if_needed(arm, current_joints, template)
        if not start_target:
            return current_joints
        return self.runtime.move_arm_joints_blocking(arm, start_target, speed="slow")

    def _start_anchor_target_if_needed(
        self,
        arm: str,
        current_joints: dict[str, float],
        template: PrimitiveTemplateAsset,
    ) -> dict[str, float] | None:
        nearest_anchor, distance = self.registry.find_closest_anchor(
            arm=arm,
            current_joints=current_joints,
            candidate_anchors=[template.start_anchor],
        )
        if nearest_anchor is None or distance <= template.guard_joint_margin_deg:
            return None
        start_anchor = self.registry.load_anchor(template.start_anchor)
        return start_anchor.joints_by_arm[arm]

    def _make_gripper_result(
        self,
        arm: str,
        primitive: str,
        magnitude: str,
        position: float,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "arm": arm,
            "primitive": primitive,
            "magnitude": magnitude,
            "start_anchor": None,
            "final_region": None,
            "executed_steps": 1,
            "joint_delta_deg": {"gripper": 0.0},
            "ee_delta_base": [0.0, 0.0, 0.0],
            "safety_events": [],
            "recovery_used": False,
            "final_joints": {"gripper": position},
        }

    def _align_to_target_unlocked(
        self,
        *,
        arm: str,
        target_name: str,
        max_iterations: int,
        lateral_tolerance_m: float,
        vertical_tolerance_m: float,
        depth_tolerance_m: float,
        speed: str,
    ) -> dict[str, Any]:
        phase_results: list[dict[str, Any]] = []
        pose_history: list[dict[str, Any]] = []
        for _ in range(max_iterations):
            pose = self.get_target_pose(target_name)
            pose_history.append(pose)
            if not pose.get("success"):
                return {
                    "success": False,
                    "arm": arm,
                    "target_name": target_name,
                    "reason": "target_not_found",
                    "phase_results": phase_results,
                    "pose_history": pose_history,
                }
            camera_xyz = pose.get("camera_xyz_m") or [0.0, 0.0, 0.0]
            depth_error = float(camera_xyz[0]) - 0.18
            lateral_error = float(camera_xyz[1])
            vertical_error = float(camera_xyz[2]) - 0.18
            if (
                abs(depth_error) <= depth_tolerance_m
                and abs(lateral_error) <= lateral_tolerance_m
                and abs(vertical_error) <= vertical_tolerance_m
            ):
                return {
                    "success": True,
                    "arm": arm,
                    "target_name": target_name,
                    "within_tolerance": True,
                    "phase_results": phase_results,
                    "pose_history": pose_history,
                }

            next_primitive = self._select_alignment_primitive(
                arm=arm,
                depth_error=depth_error,
                lateral_error=lateral_error,
                vertical_error=vertical_error,
                lateral_tolerance_m=lateral_tolerance_m,
                vertical_tolerance_m=vertical_tolerance_m,
                depth_tolerance_m=depth_tolerance_m,
            )
            if next_primitive is None:
                break
            phase_results.append(
                self._execute_motion_primitive_unlocked(
                    arm=arm,
                    primitive=next_primitive,
                    magnitude="small",
                    speed=speed,
                )
            )

        return {
            "success": False,
            "arm": arm,
            "target_name": target_name,
            "within_tolerance": False,
            "phase_results": phase_results,
            "pose_history": pose_history,
        }

    def _select_alignment_primitive(
        self,
        *,
        arm: str,
        depth_error: float,
        lateral_error: float,
        vertical_error: float,
        lateral_tolerance_m: float,
        vertical_tolerance_m: float,
        depth_tolerance_m: float,
    ) -> str | None:
        if abs(lateral_error) > lateral_tolerance_m:
            if arm == "left":
                return "open_upper_arm" if lateral_error > 0 else "close_upper_arm"
            return "close_upper_arm" if lateral_error > 0 else "open_upper_arm"
        if abs(vertical_error) > vertical_tolerance_m:
            return "lift_forearm" if vertical_error > 0 else "lower_forearm"
        if abs(depth_error) > depth_tolerance_m:
            return "lower_forearm" if depth_error > 0 else "lift_forearm"
        return None

    def _combo_completion_satisfied(
        self,
        *,
        template: ComboTemplateAsset,
        arm: str | None,
    ) -> bool:
        goal_region = template.completion_rule.get("goal_region") or template.goal_region
        if not goal_region:
            return True
        if template.arm_mode == "both":
            left_goal, right_goal = self._split_bimanual_goal(goal_region)
            left_status = self.estimate_arm_region("left")
            right_status = self.estimate_arm_region("right")
            return (
                left_status.get("region") == left_goal
                and right_status.get("region") == right_goal
            )

        selected_arm = arm or "left"
        target_region = self._normalize_region(goal_region, selected_arm)
        current_region = self.estimate_arm_region(selected_arm).get("region")
        return current_region == target_region

    def _split_bimanual_goal(self, goal_region: str) -> tuple[str | None, str | None]:
        if "+" not in goal_region:
            return goal_region, goal_region
        left_goal, right_goal = goal_region.split("+", 1)
        return left_goal.strip(), right_goal.strip()

    def _normalize_region(self, region: str | None, arm: str) -> str | None:
        if not region:
            return None
        return region.replace("*", arm)

    def _tactile_contact_detected(self, tactile: dict[str, Any] | None) -> bool:
        if not tactile:
            return False
        if bool(tactile.get("contact")):
            return True
        if bool(tactile.get("stable_grasp")):
            return True
        contact_count = tactile.get("contact_count")
        if isinstance(contact_count, (int, float)) and contact_count > 0:
            return True
        return False

    def _expand_anchor_patterns(self, arm: str, patterns: list[str]) -> list[str]:
        expanded: list[str] = []
        for pattern in patterns:
            if pattern == "*":
                return [anchor.name for anchor in self.registry.list_anchors()]
            if "*_" in pattern:
                expanded.append(pattern.replace("*", arm))
            else:
                expanded.append(pattern)
        return expanded
