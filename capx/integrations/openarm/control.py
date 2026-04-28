from __future__ import annotations

from typing import Any

from capx.integrations.base_api import ApiBase

from .assets import OpenArmMotionAssetRegistry
from .executor import OpenArmMotionExecutor
from .recording import ManualOpenArmRecorder


class OpenArmControlApi(ApiBase):
    def __init__(self, env) -> None:
        super().__init__(env)
        if not hasattr(env, "runtime"):
            raise TypeError("OpenArmControlApi requires a low-level env with a 'runtime' attribute.")
        self._registry: OpenArmMotionAssetRegistry = getattr(env, "asset_registry")
        self._executor = OpenArmMotionExecutor(env.runtime, self._registry)

    def functions(self) -> dict[str, Any]:
        return {
            "get_robot_state": self.get_robot_state,
            "get_observation": self.get_observation,
            "describe_scene": self.describe_scene,
            "read_tactile": self.read_tactile,
            "get_tactile_health": self.get_tactile_health,
            "detect_target": self.detect_target,
            "get_target_pose": self.get_target_pose,
            "estimate_arm_region": self.estimate_arm_region,
            "align_to_target": self.align_to_target,
            "approach_target": self.approach_target,
            "descend_until_contact": self.descend_until_contact,
            "grasp_with_tactile_guard": self.grasp_with_tactile_guard,
            "release_grasp": self.release_grasp,
            "handover_to_center": self.handover_to_center,
            "get_motion_primitive_catalog": self.get_motion_primitive_catalog,
            "get_motion_combo_catalog": self.get_motion_combo_catalog,
            "execute_motion_primitive": self.execute_motion_primitive,
            "execute_bimanual_primitive": self.execute_bimanual_primitive,
            "execute_motion_combo": self.execute_motion_combo,
            "undo_last_motion": self.undo_last_motion,
            "move_to_named_pose": self.move_to_named_pose,
            "move_arm_joints_safe": self.move_arm_joints_safe,
            "open_gripper": self.open_gripper,
            "close_gripper": self.close_gripper,
            "go_home": self.go_home,
            "go_safe_standby": self.go_safe_standby,
            "stop_robot": self.stop_robot,
        }

    def get_robot_state(self) -> dict[str, Any]:
        """Return a structured summary of robot connectivity, joint state, and task state."""
        self._log_step("get_robot_state", "Reading OpenArm runtime state ...")
        result = self._executor.get_robot_state()
        self._log_step_update(text=f"Task state: {result['task_state']}")
        return result

    def get_observation(self) -> dict[str, Any]:
        """Return the latest structured OpenArm observation including joint state and cameras."""
        self._log_step("get_observation", "Capturing OpenArm observation ...")
        obs = self._env.get_observation()
        image = next(iter(obs.get("cameras", {}).values()), None)
        self._log_step_update(images=image if image is not None else None)
        return obs

    def describe_scene(self, prompt: str | None = None) -> dict[str, Any]:
        """Capture and describe the current camera image through the perception adapter.

        Args:
            prompt: Optional natural-language focus for the visual description, such as
                "what objects are on the table?".

        Returns:
            A perception payload that may include a text description, detections, and
            an image_base64/images field for UI and nanobot forwarding.
        """
        self._log_step("describe_scene", "Capturing and describing the current scene ...")
        result = self._executor.describe_scene(prompt)
        description = result.get("description") or result.get("content") or result.get("summary")
        self._log_step_update(
            text=str(description or result.get("status", "scene description complete")),
            images=self._extract_result_images(result),
        )
        return result

    def read_tactile(self, arm: str | None = None) -> dict[str, Any]:
        """Read tactile information from the local perception adapter.

        Args:
            arm: Reserved for future multi-sensor setups. Use None for the shared tactile channel.

        Returns:
            A dictionary with tactile contact, stability, and force summaries.
        """
        del arm
        self._log_step("read_tactile", "Reading tactile signal ...")
        result = self._executor.read_tactile()
        self._log_step_update(text=f"contact={result.get('contact')} stable={result.get('stable_grasp')}")
        return result

    def get_tactile_health(self) -> dict[str, Any]:
        """Return the current tactile service health summary."""
        self._log_step("get_tactile_health", "Checking tactile service health ...")
        result = self._executor.get_tactile_health()
        self._log_step_update(text=f"status={result.get('status', 'unknown')}")
        return result

    def detect_target(self, target_name: str) -> dict[str, Any]:
        """Detect a target using the OpenClaw perception adapter.

        Args:
            target_name: Natural-language label such as "tomato".

        Returns:
            Detection payload from the local perception service.
        """
        self._log_step("detect_target", f"Detecting target '{target_name}' ...")
        result = self._executor.detect_target(target_name)
        summary = f"detections={len(result.get('detections', []))}"
        description = result.get("description") or result.get("content")
        if description:
            summary = f"{summary}\n{description}"
        self._log_step_update(text=summary, images=self._extract_result_images(result))
        return result

    def get_target_pose(self, target_name: str) -> dict[str, Any]:
        """Get the best available camera-frame target pose estimate from the perception adapter."""
        self._log_step("get_target_pose", f"Estimating target pose for '{target_name}' ...")
        result = self._executor.get_target_pose(target_name)
        self._log_step_update(text=f"success={result.get('success')}")
        return result

    def estimate_arm_region(self, arm: str) -> dict[str, Any]:
        """Estimate the current semantic region for one arm from the nearest anchor."""
        self._log_step("estimate_arm_region", f"Estimating current region for {arm} arm ...")
        result = self._executor.estimate_arm_region(arm)
        self._log_step_update(text=f"region={result.get('region')} anchor={result.get('anchor')}")
        return result

    def align_to_target(
        self,
        arm: str,
        target_name: str,
        max_iterations: int = 3,
        lateral_tolerance_m: float = 0.05,
        vertical_tolerance_m: float = 0.05,
        depth_tolerance_m: float = 0.08,
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Use small motion primitives to align one arm with the detected target pose."""
        self._log_step("align_to_target", f"Aligning {arm} arm to target '{target_name}' ...")
        result = self._executor.align_to_target(
            arm=arm,
            target_name=target_name,
            max_iterations=max_iterations,
            lateral_tolerance_m=lateral_tolerance_m,
            vertical_tolerance_m=vertical_tolerance_m,
            depth_tolerance_m=depth_tolerance_m,
            speed=speed,
        )
        self._log_step_update(text=f"success={result.get('success')} phases={len(result.get('phase_results', []))}")
        return result

    def approach_target(
        self,
        arm: str,
        target_name: str,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Move one arm into a near-target working pose using combos plus alignment."""
        self._log_step("approach_target", f"Approaching target '{target_name}' with {arm} arm ...")
        result = self._executor.approach_target(
            arm=arm,
            target_name=target_name,
            magnitude=magnitude,
            speed=speed,
        )
        self._log_step_update(text=f"success={result.get('success')} phases={len(result.get('phase_results', []))}")
        return result

    def descend_until_contact(
        self,
        arm: str,
        primitive: str = "lower_forearm",
        magnitude: str = "slight",
        max_steps: int = 4,
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Step downward or forward until tactile contact is detected or the step budget is reached."""
        self._log_step("descend_until_contact", f"Descending {arm} arm until tactile contact ...")
        result = self._executor.descend_until_contact(
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            max_steps=max_steps,
            speed=speed,
        )
        self._log_step_update(
            text=(
                f"contact={result.get('stopped_on_contact')} "
                f"steps={result.get('steps_executed')}"
            )
        )
        return result

    def grasp_with_tactile_guard(
        self,
        arm: str,
        close_sequence: list[str] | None = None,
        stop_on_stable_grasp: bool = True,
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Close the gripper progressively and stop when tactile contact or stable grasp is detected."""
        self._log_step("grasp_with_tactile_guard", f"Closing {arm} gripper with tactile guard ...")
        result = self._executor.grasp_with_tactile_guard(
            arm=arm,
            close_sequence=close_sequence,
            stop_on_stable_grasp=stop_on_stable_grasp,
            speed=speed,
        )
        self._log_step_update(
            text=(
                f"contact={result.get('contact_detected')} "
                f"stable={result.get('stable_grasp')}"
            )
        )
        return result

    def release_grasp(
        self,
        arm: str,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Open the gripper to release a previously grasped object."""
        self._log_step("release_grasp", f"Releasing grasp on {arm} arm ...")
        result = self._executor.release_grasp(
            arm=arm,
            magnitude=magnitude,
            speed=speed,
        )
        self._log_step_update(text=f"released={result.get('released')}")
        return result

    def handover_to_center(
        self,
        arm: str,
        receive_mode: bool = False,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Move one hand to the handover center, optionally in receiving posture."""
        mode = "receive" if receive_mode else "give"
        self._log_step("handover_to_center", f"Moving {arm} arm to {mode} handover pose ...")
        result = self._executor.handover_to_center(
            arm=arm,
            receive_mode=receive_mode,
            magnitude=magnitude,
            speed=speed,
        )
        self._log_step_update(text=f"success={result.get('success')} final_region={result.get('final_region')}")
        return result

    def get_motion_primitive_catalog(self) -> list[dict[str, object]]:
        """List the supported OpenArm motion primitives and their spatial semantics."""
        return self._executor.get_motion_primitive_catalog()

    def get_motion_combo_catalog(self) -> list[dict[str, object]]:
        """List the supported OpenArm motion combos and their default phase sequences."""
        return self._executor.get_motion_combo_catalog()

    def execute_motion_primitive(
        self,
        arm: str,
        primitive: str,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Execute one named motion primitive on the selected arm."""
        self._log_step("execute_motion_primitive", f"{arm}:{primitive}:{magnitude}")
        result = self._executor.execute_motion_primitive(
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            speed=speed,
        )
        self._log_step_update(text=f"final_region={result.get('final_region')}")
        return result

    def execute_bimanual_primitive(
        self,
        primitive: str,
        magnitude: str = "medium",
        symmetry: str = "mirror",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Execute the same primitive on both arms in one active task."""
        self._log_step("execute_bimanual_primitive", f"{primitive}:{magnitude}:{symmetry}")
        result = self._executor.execute_bimanual_primitive(
            primitive=primitive,
            magnitude=magnitude,
            symmetry=symmetry,
            speed=speed,
        )
        self._log_step_update(text=f"success={result.get('success')}")
        return result

    def execute_motion_combo(
        self,
        name: str,
        arm: str | None = None,
        magnitude: str = "medium",
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Execute one named motion combo."""
        self._log_step("execute_motion_combo", f"{name}:{arm}:{magnitude}")
        result = self._executor.execute_motion_combo(
            name=name,
            arm=arm,
            magnitude=magnitude,
            speed=speed,
        )
        self._log_step_update(text=f"final_region={result.get('final_region')}")
        return result

    def undo_last_motion(self, arm: str) -> dict[str, Any]:
        """Undo the most recent recorded primitive on the selected arm."""
        self._log_step("undo_last_motion", f"Undoing last motion on {arm} ...")
        result = self._executor.undo_last_motion(arm)
        self._log_step_update(text=f"primitive={result.get('primitive')}")
        return result

    def move_to_named_pose(
        self,
        name: str,
        speed: str = "slow",
        ignore_gripper: bool = False,
        ignore_gripper_when_closing: bool = False,
    ) -> dict[str, Any]:
        """Move to a recorded named anchor pose such as `home` or `safe_standby`.

        Args:
            name: Anchor asset name to execute.
            speed: Named runtime speed profile.
            ignore_gripper: When True, do not command the anchor gripper target. This is
                useful when the gripper is already holding an object and should not block
                the rest of the arm from reaching the anchor.
            ignore_gripper_when_closing: When True, keep the current gripper state only for
                anchor targets that would close further than the current gripper position.
                Anchor targets that open the gripper will still be executed.
        """
        step_text = f"Moving to anchor '{name}' ..."
        if ignore_gripper:
            step_text = f"Moving to anchor '{name}' while holding current gripper state ..."
        elif ignore_gripper_when_closing:
            step_text = (
                f"Moving to anchor '{name}' while allowing blocked close to hold current "
                "gripper state ..."
            )
        self._log_step("move_to_named_pose", step_text)
        result = self._executor.move_to_named_pose(
            name,
            speed=speed,
            ignore_gripper=ignore_gripper,
            ignore_gripper_when_closing=ignore_gripper_when_closing,
        )
        summary = f"arm_mode={result.get('arm_mode')}"
        if result.get("ignored_joints"):
            summary = f"{summary} ignored={','.join(result['ignored_joints'])}"
        self._log_step_update(text=summary)
        return result

    def move_arm_joints_safe(
        self,
        arm: str,
        joints: dict[str, float],
        speed: str = "slow",
    ) -> dict[str, Any]:
        """Move one arm to explicit joint targets using conservative runtime limits."""
        self._log_step("move_arm_joints_safe", f"Moving {arm} with explicit joint targets ...")
        result = self._executor.move_arm_joints_safe(arm=arm, joints=joints, speed=speed)
        self._log_step_update(text=f"success={result.get('success')}")
        return result

    def open_gripper(self, arm: str, width: str | float = "full") -> dict[str, Any]:
        """Directly open the gripper."""
        fraction = self._width_to_fraction(width, closing=False)
        self._log_step("open_gripper", f"Opening {arm} gripper to fraction {fraction:.2f} ...")
        result = self._executor.set_gripper_fraction(arm, fraction)
        self._log_step_update(text=f"gripper_position={result.get('gripper_position'):.2f}")
        return result

    def close_gripper(self, arm: str, force: str | float = "full") -> dict[str, Any]:
        """Directly close the gripper."""
        fraction = self._width_to_fraction(force, closing=True)
        self._log_step("close_gripper", f"Closing {arm} gripper to fraction {fraction:.2f} ...")
        result = self._executor.set_gripper_fraction(arm, fraction)
        self._log_step_update(text=f"gripper_position={result.get('gripper_position'):.2f}")
        return result

    def go_home(self) -> dict[str, Any]:
        """Convenience wrapper for `move_to_named_pose('home')`."""
        return self.move_to_named_pose("home", speed="slow")

    def go_safe_standby(self) -> dict[str, Any]:
        """Convenience wrapper for `move_to_named_pose('safe_standby')`."""
        return self.move_to_named_pose("safe_standby", speed="slow")

    def stop_robot(self) -> dict[str, Any]:
        """Stop the robot by holding the current observed joint state."""
        self._log_step("stop_robot", "Stopping robot and holding current state ...", highlight=True)
        result = self._executor.stop_robot()
        self._log_step_update(text=f"task_state={result.get('task_state')}")
        return result

    def _width_to_fraction(self, value: str | float, *, closing: bool) -> float:
        if isinstance(value, (int, float)):
            fraction = float(value)
        else:
            mapping = {
                "slight": 0.10,
                "small": 0.25,
                "medium": 0.50,
                "full": 1.00,
                "large": 1.00,
            }
            if value not in mapping:
                raise ValueError(f"Unsupported gripper width keyword: {value}")
            fraction = mapping[value]
        fraction = max(0.0, min(1.0, fraction))
        return 1.0 - fraction if closing else fraction

    def _extract_result_images(self, result: dict[str, Any]) -> list[str]:
        images: list[str] = []
        for key in ("image_base64", "image", "annotated_image_base64", "annotated_image"):
            value = result.get(key)
            if isinstance(value, str) and value:
                images.append(value)
        raw_images = result.get("images")
        if isinstance(raw_images, list):
            images.extend(item for item in raw_images if isinstance(item, str) and item)
        return images


class OpenArmRecordingApi(ApiBase):
    def __init__(self, env) -> None:
        super().__init__(env)
        if not hasattr(env, "runtime"):
            raise TypeError("OpenArmRecordingApi requires a low-level env with a 'runtime' attribute.")
        self._registry: OpenArmMotionAssetRegistry = getattr(env, "asset_registry")
        self._recorder = ManualOpenArmRecorder(env.runtime, self._registry)

    def functions(self) -> dict[str, Any]:
        return {
            "record_anchor": self.record_anchor,
            "record_primitive_template": self.record_primitive_template,
            "record_combo_template": self.record_combo_template,
            "list_recorded_anchors": self.list_recorded_anchors,
            "list_recorded_primitive_templates": self.list_recorded_primitive_templates,
            "list_recorded_combo_templates": self.list_recorded_combo_templates,
            "get_recording_status": self.get_recording_status,
            "bootstrap_combo_templates": self.bootstrap_combo_templates,
        }

    def record_anchor(
        self,
        name: str,
        arm_mode: str = "both",
        arm: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Record the current arm joint state as a named anchor asset."""
        self._log_step("record_anchor", f"Recording anchor '{name}' ...")
        result = self._recorder.record_anchor(name, arm_mode=arm_mode, arm=arm, notes=notes)
        self._log_step_update(text=result.path)
        return {"success": True, **result.details, "path": result.path}

    def record_primitive_template(
        self,
        arm: str,
        primitive: str,
        magnitude: str,
        start_anchor: str,
        end_region_hint: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Record a primitive template by comparing the current joint state to a start anchor."""
        self._log_step("record_primitive_template", f"Recording {arm}:{primitive}:{magnitude} ...")
        result = self._recorder.record_primitive_template(
            arm=arm,
            primitive=primitive,
            magnitude=magnitude,
            start_anchor=start_anchor,
            end_region_hint=end_region_hint,
            notes=notes,
        )
        self._log_step_update(text=result.path)
        return {"success": True, **result.details, "path": result.path}

    def record_combo_template(
        self,
        combo: str,
        arm_mode: str = "single",
        magnitude: str = "medium",
        recovery_anchor: str = "safe_standby",
    ) -> dict[str, Any]:
        """Record a combo template using the built-in phase definition as a starting point."""
        self._log_step("record_combo_template", f"Recording combo '{combo}' ...")
        result = self._recorder.record_combo_template(
            combo=combo,
            arm_mode=arm_mode,
            magnitude=magnitude,
            recovery_anchor=recovery_anchor,
        )
        self._log_step_update(text=result.path)
        return {"success": True, **result.details, "path": result.path}

    def list_recorded_anchors(self) -> list[dict[str, Any]]:
        """List all recorded anchor assets currently stored under the OpenArm asset root."""
        return [anchor.to_dict() for anchor in self._registry.list_anchors()]

    def list_recorded_primitive_templates(self) -> list[dict[str, Any]]:
        """List all recorded primitive templates currently stored under the OpenArm asset root."""
        return [template.to_dict() for template in self._registry.list_primitive_templates()]

    def list_recorded_combo_templates(self) -> list[dict[str, Any]]:
        """List all recorded combo templates currently stored under the OpenArm asset root."""
        return [template.to_dict() for template in self._registry.list_combo_templates()]

    def get_recording_status(self) -> dict[str, Any]:
        """Return a summary of recorded OpenArm assets and the remaining default v1 gaps."""
        return self._registry.get_recording_status()

    def bootstrap_combo_templates(
        self,
        magnitude: str = "medium",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create editable combo template YAMLs from the built-in v1 combo catalog."""
        self._log_step("bootstrap_combo_templates", "Creating combo template skeletons ...")
        paths = self._registry.bootstrap_combo_templates(magnitude=magnitude, overwrite=overwrite)
        self._log_step_update(text=f"created={len(paths)}")
        return {
            "success": True,
            "created_count": len(paths),
            "paths": [str(path) for path in paths],
        }
