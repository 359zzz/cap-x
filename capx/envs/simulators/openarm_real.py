from __future__ import annotations

import os
from typing import Any

import numpy as np

from capx.envs.base import BaseEnv
from capx.integrations.openarm.assets import OpenArmMotionAssetRegistry
from capx.integrations.openarm.recording import ManualOpenArmRecorder
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


class OpenArmRealLowLevel(BaseEnv):
    """Low-level OpenArm environment compatible with CaP-X code execution.

    The environment wraps the physical OpenArm runtime and exposes an
    observation format similar to Robosuite environments so that higher-level
    visual APIs (SAM3, Contact-Graspnet, Pyroki) can be reused with minimal
    changes.

    Observations contain:
      * ``robot_joint_pos``: (16,) concatenated left/right [7 joints + gripper].
      * ``left_arm`` / ``right_arm``: structured joint pos/vel/torque dicts.
      * ``left_ee_pose`` / ``right_ee_pose``: FK end-effector poses from URDF.
      * ``cameras``: raw per-camera RGB/depth/intrinsics/extrinsics.
      * ``robot0_robotview``: Robosuite-style camera entry used by vision APIs.
    """

    def __init__(
        self,
        seed: int | None = None,
        privileged: bool = False,
        enable_render: bool = False,
        viser_debug: bool = False,
    ) -> None:
        del seed, privileged, enable_render, viser_debug
        super().__init__()
        self.runtime = OpenArmRuntime(OpenArmRuntimeConfig())
        self.asset_registry = OpenArmMotionAssetRegistry()
        self.recorder = ManualOpenArmRecorder(self.runtime, self.asset_registry)
        self._record_frames = False
        self._frame_buffer: list[np.ndarray] = []
        self._robotview_camera = os.getenv("CAPX_OPENARM_ROBOTVIEW_CAMERA", "left")
        self._robotview_fallbacks = ["left", "right", "head"]

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        del seed, options
        self.runtime.connect()
        obs = self.get_observation()
        return obs, {}

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        del action
        obs = self.get_observation()
        return obs, 0.0, False, False, {}

    def get_observation(self) -> dict[str, Any]:
        """Return a Robosuite-compatible observation with fresh camera frames."""
        obs = self.runtime.get_observation_with_cameras()
        obs["robot_joint_pos"] = self._build_robot_joint_pos(obs)
        obs["robot0_robotview"] = self._build_robotview(obs)
        if self._record_frames:
            frame = self._extract_first_rgb_frame(obs)
            if frame is not None:
                self._frame_buffer.append(frame.copy())
        return obs

    def compute_reward(self) -> float:
        return 0.0

    def task_completed(self) -> bool:
        return False

    def render(self, mode: str = "rgb_array") -> np.ndarray:  # type: ignore[override]
        del mode
        frame = self._extract_first_rgb_frame(self.get_observation())
        if frame is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        return frame

    def close(self) -> None:
        self.runtime.disconnect()

    def enable_video_capture(self, enabled: bool = True, *, clear: bool = True) -> None:
        self._record_frames = enabled
        if clear:
            self._frame_buffer.clear()
        if enabled:
            frame = self._extract_first_rgb_frame(self.get_observation())
            if frame is not None:
                self._frame_buffer.append(frame.copy())

    def get_video_frames(self, *, clear: bool = False) -> list[np.ndarray]:
        frames = [frame.copy() for frame in self._frame_buffer]
        if clear:
            self._frame_buffer.clear()
        return frames

    def get_video_frame_count(self) -> int:
        return len(self._frame_buffer)

    def get_video_frames_range(self, start: int, end: int) -> list[np.ndarray]:
        return [frame.copy() for frame in self._frame_buffer[start:end]]

    # ------------------------------------------------------------------
    # Robosuite-compatible view builder
    # ------------------------------------------------------------------
    def _build_robot_joint_pos(self, obs: dict[str, Any]) -> np.ndarray:
        """Build (16,) [left 7 joints + gripper, right 7 joints + gripper]."""
        left = obs.get("left_arm", {}).get("joint_pos", {})
        right = obs.get("right_arm", {}).get("joint_pos", {})

        def extract(arm_joints: dict[str, float]) -> list[float]:
            vals: list[float] = []
            for i in range(1, 8):
                vals.append(float(arm_joints.get(f"joint_{i}", 0.0)))
            vals.append(float(arm_joints.get("gripper", 0.0)))
            return vals

        return np.asarray(extract(left) + extract(right), dtype=np.float32)

    def _build_robotview(self, obs: dict[str, Any]) -> dict[str, Any]:
        """Build a ``robot0_robotview`` entry from the selected camera."""
        cameras = obs.get("cameras", {})
        cam = cameras.get(self._robotview_camera)
        if cam is None or (isinstance(cam, dict) and "error" in cam):
            # Fallback through left, right, head.
            for key in self._robotview_fallbacks:
                value = cameras.get(key)
                if isinstance(value, dict) and "rgb" in value and "error" not in value:
                    cam = value
                    break
            # Final fallback: any camera with rgb.
            if cam is None:
                for value in cameras.values():
                    if isinstance(value, dict) and "rgb" in value and "error" not in value:
                        cam = value
                        break

        robotview: dict[str, Any] = {}
        if cam is None or not isinstance(cam, dict) or "rgb" not in cam:
            return robotview

        images: dict[str, Any] = {"rgb": cam["rgb"]}
        if cam.get("depth") is not None:
            # Robosuite convention: depth is (H, W, 1) in meters.
            depth = np.asarray(cam["depth"], dtype=np.float32)
            if depth.ndim == 2:
                depth = depth[:, :, None]
            images["depth"] = depth

        robotview["images"] = images

        intrinsics = cam.get("intrinsics")
        if intrinsics is not None:
            robotview["intrinsics"] = np.asarray(intrinsics, dtype=np.float32)

        T_base_cam = cam.get("T_base_cam")
        if T_base_cam is not None:
            robotview["pose_mat"] = np.asarray(T_base_cam, dtype=np.float64)
            robotview["pose"] = np.concatenate(
                [
                    np.asarray(T_base_cam, dtype=np.float64)[:3, 3],
                    _mat_to_quat_wxyz(np.asarray(T_base_cam, dtype=np.float64)[:3, :3]),
                ]
            )

        return robotview

    def _extract_first_rgb_frame(self, obs: dict[str, Any]) -> np.ndarray | None:
        robotview = obs.get("robot0_robotview", {})
        rgb = robotview.get("images", {}).get("rgb")
        if isinstance(rgb, np.ndarray) and rgb.ndim == 3 and rgb.shape[-1] in {3, 4}:
            return rgb[..., :3]
        for value in obs.get("cameras", {}).values():
            if isinstance(value, dict):
                rgb = value.get("rgb")
                if isinstance(rgb, np.ndarray) and rgb.ndim == 3 and rgb.shape[-1] in {3, 4}:
                    return rgb[..., :3]
        return None


def _mat_to_quat_wxyz(R: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to [w, x, y, z] quaternion."""
    R = np.asarray(R, dtype=np.float64)
    m00, m01, m02 = R[0]
    m10, m11, m12 = R[1]
    m20, m21, m22 = R[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (m21 - m12) * s
        y = (m02 - m20) * s
        z = (m10 - m01) * s
    elif m00 > m11 and m00 > m22:
        s = 2.0 * np.sqrt(1.0 + m00 - m11 - m22)
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = 2.0 * np.sqrt(1.0 + m11 - m00 - m22)
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = 2.0 * np.sqrt(1.0 + m22 - m00 - m11)
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    q = np.array([w, x, y, z], dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    return q / norm


__all__ = ["OpenArmRealLowLevel"]
