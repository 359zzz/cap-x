"""OpenArm v2.0 forward kinematics using an off-the-shelf URDF.

This module does **not** depend on ROS2. It loads the OpenArm description
(`enactic/openarm_description`) and uses Pinocchio for fast, accurate FK.
If Pinocchio is not installed, FK calls return a clear error telling the user
how to install it, but the rest of the runtime keeps working.

Coordinate frames:
  * world/base = ``openarm_body_link0`` (the torso frame in the URDF).
  * arm base   = ``openarm_{side}_base_link`` (mounted on the torso).
  * ee flange  = ``openarm_{side}_ee_base_link`` (after the 7th joint).
  * camera     = a frame attached to the wrist, calibrated eye-in-hand.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


_JOINT_ORDER = [f"joint_{i}" for i in range(1, 8)]


def _find_default_urdf_path() -> Path | None:
    """Return a sensible default URDF path if one exists on this machine."""
    candidates = [
        Path(os.environ.get("CAPX_OPENARM_URDF", "")),
        Path.home() / ".capx" / "openarm" / "urdf" / "openarm_v20.urdf",
        Path.home() / "robot_workspace" / "cap-x" / "third_party" / "openarm_description" / "output.urdf",
        Path(__file__).resolve().parents[3] / "third_party" / "openarm_description" / "output.urdf",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


@dataclass
class OpenArmKinematicsConfig:
    """Configuration for OpenArm FK.

    Attributes:
        urdf_path: Path to the OpenArm URDF. If None, a default search is performed.
        base_link_name: Name of the world/torso frame in the URDF.
        side: "left" or "right".
        ee_link_name: Override the default end-effector link name.
        arm_base_link_name: Override the default arm base link name.
    """

    urdf_path: Path | str | None = None
    base_link_name: str = "openarm_body_link0"
    side: str = "left"
    ee_link_name: str | None = None
    arm_base_link_name: str | None = None

    def __post_init__(self) -> None:
        if self.urdf_path is None:
            self.urdf_path = _find_default_urdf_path()
        elif isinstance(self.urdf_path, str):
            self.urdf_path = Path(self.urdf_path)

        side = self.side.lower()
        if side not in {"left", "right"}:
            raise ValueError(f"side must be 'left' or 'right', got {self.side!r}")
        self.side = side

        if self.ee_link_name is None:
            self.ee_link_name = f"openarm_{self.side}_ee_base_link"
        if self.arm_base_link_name is None:
            self.arm_base_link_name = f"openarm_{self.side}_base_link"


@dataclass
class ArmFKSolution:
    """Result of a single-arm FK query."""

    side: str
    joint_positions_deg: dict[str, float]
    T_base_ee: np.ndarray  # (4,4) homogeneous transform, base_link -> ee_link
    T_world_ee: np.ndarray  # alias; same as T_base_ee when base_link is the torso
    ee_position: np.ndarray  # (3,) meters
    ee_quaternion_xyzw: np.ndarray  # (4,) [x, y, z, w], unit quaternion


class OpenArmKinematics:
    """Forward kinematics for one OpenArm arm.

    Usage:
        kin = OpenArmKinematics(OpenArmKinematicsConfig(side="left"))
        sol = kin.solve_fk({"joint_1": 0.0, ..., "joint_7": 0.0})
        print(sol.ee_position)
    """

    def __init__(self, config: OpenArmKinematicsConfig | None = None) -> None:
        self.config = config or OpenArmKinematicsConfig()
        self._model: Any = None
        self._data: Any = None
        self._joint_ids: list[int] = []
        self._ee_frame_id: int | None = None
        self._base_frame_id: int | None = None
        self._arm_base_frame_id: int | None = None
        self._available = False
        self._init()

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        """True if Pinocchio loaded the URDF successfully."""
        return self._available

    @property
    def urdf_path(self) -> Path | None:
        if isinstance(self.config.urdf_path, Path):
            return self.config.urdf_path
        return None

    def check_available(self) -> None:
        """Raise a helpful error if FK is not available."""
        if self._available:
            return
        msg = [
            "OpenArm FK is not available.  To enable it:",
            "  1. Install Pinocchio:  pip install pinocchio",
            "  2. Provide a URDF via CAPX_OPENARM_URDF=... or run scripts/setup_openarm_urdf.sh",
        ]
        if self.config.urdf_path is not None:
            msg.append(f"  Current URDF path: {self.config.urdf_path}")
        raise RuntimeError("\n".join(msg))

    # ------------------------------------------------------------------
    # FK API
    # ------------------------------------------------------------------
    def solve_fk(self, joint_positions_deg: dict[str, float]) -> ArmFKSolution:
        """Compute end-effector pose from arm joint positions (degrees).

        Args:
            joint_positions_deg: Mapping with keys ``joint_1`` ... ``joint_7``.
                Missing keys are treated as 0.0.  ``gripper`` is ignored for FK.

        Returns:
            ArmFKSolution with position, quaternion, and 4x4 transforms.
        """
        self.check_available()
        q = self._joint_vector_from_deg(joint_positions_deg)
        return self._solve_fk_from_rad(q)

    def solve_camera_pose(
        self,
        joint_positions_deg: dict[str, float],
        T_ee_cam: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Compute camera pose in the world/base frame.

        Args:
            joint_positions_deg: Arm joint positions in degrees.
            T_ee_cam: (4,4) homogeneous transform from ee flange to camera frame.

        Returns:
            Dictionary with ``T_base_cam``, ``position``, ``quaternion_xyzw``.
        """
        self.check_available()
        fk = self.solve_fk(joint_positions_deg)
        T_base_cam = fk.T_base_ee @ np.asarray(T_ee_cam, dtype=np.float64)
        return {
            "T_base_cam": T_base_cam,
            "T_world_cam": T_base_cam,
            "position": T_base_cam[:3, 3].copy(),
            "quaternion_xyzw": _rotation_matrix_to_quaternion_xyzw(T_base_cam[:3, :3]),
        }

    def get_joint_limits_rad(self) -> dict[str, tuple[float, float]]:
        """Return lower/upper joint limits in radians."""
        self.check_available()
        limits: dict[str, tuple[float, float]] = {}
        for name, jid in zip(_JOINT_ORDER, self._joint_ids):
            jmodel = self._model.joints[jid]
            lo = self._model.lowerPositionLimit[jmodel.idx_q : jmodel.idx_q + jmodel.nq]
            hi = self._model.upperPositionLimit[jmodel.idx_q : jmodel.idx_q + jmodel.nq]
            limits[name] = (float(lo[0]), float(hi[0]))
        return limits

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init(self) -> None:
        try:
            import pinocchio as pin
        except ImportError as exc:
            self._available = False
            self._import_error = str(exc)
            return

        urdf_path = self.config.urdf_path
        if urdf_path is None or not Path(urdf_path).is_file():
            self._available = False
            self._import_error = f"URDF not found: {urdf_path}"
            return

        try:
            self._model = pin.buildModelFromUrdf(str(urdf_path))
            self._data = self._model.createData()
        except Exception as exc:
            self._available = False
            self._import_error = f"Failed to build Pinocchio model from {urdf_path}: {exc}"
            return

        side = self.config.side
        expected_joints = [f"openarm_{side}_joint{i}" for i in range(1, 8)]
        self._joint_ids = []
        for jname in expected_joints:
            jid = self._model.getJointId(jname)
            if jid >= len(self._model.joints):
                self._available = False
                self._import_error = f"Joint '{jname}' not found in URDF {urdf_path}"
                return
            self._joint_ids.append(jid)

        self._ee_frame_id = self._model.getFrameId(self.config.ee_link_name)
        if self._ee_frame_id >= len(self._model.frames):
            self._available = False
            self._import_error = f"Frame '{self.config.ee_link_name}' not found in URDF"
            return

        self._base_frame_id = self._model.getFrameId(self.config.base_link_name)
        self._arm_base_frame_id = self._model.getFrameId(self.config.arm_base_link_name)

        self._available = True

    def _joint_vector_from_deg(self, joint_positions_deg: dict[str, float]) -> np.ndarray:
        q = np.zeros(self._model.nq, dtype=np.float64)
        for name, jid in zip(_JOINT_ORDER, self._joint_ids):
            deg = float(joint_positions_deg.get(name, 0.0))
            q[self._model.joints[jid].idx_q] = np.deg2rad(deg)
        return q

    def _solve_fk_from_rad(self, q: np.ndarray) -> ArmFKSolution:
        import pinocchio as pin

        pin.forwardKinematics(self._model, self._data, q)
        pin.updateFramePlacements(self._model, self._data)

        T_world_ee = self._data.oMf[self._ee_frame_id].homogeneous
        T_base_ee = T_world_ee
        if self._base_frame_id is not None and self._base_frame_id < len(self._model.frames):
            T_world_base = self._data.oMf[self._base_frame_id].homogeneous
            T_base_ee = np.linalg.inv(T_world_base) @ T_world_ee

        pos = T_base_ee[:3, 3].copy()
        quat_xyzw = _rotation_matrix_to_quaternion_xyzw(T_base_ee[:3, :3])

        joint_positions_deg = {
            name: float(np.rad2deg(q[self._model.joints[jid].idx_q]))
            for name, jid in zip(_JOINT_ORDER, self._joint_ids)
        }

        return ArmFKSolution(
            side=self.config.side,
            joint_positions_deg=joint_positions_deg,
            T_base_ee=T_base_ee.astype(np.float64),
            T_world_ee=T_world_ee.astype(np.float64),
            ee_position=pos,
            ee_quaternion_xyzw=quat_xyzw,
        )


class BiOpenArmKinematics:
    """Convenience wrapper holding left + right FK solvers."""

    def __init__(self, urdf_path: Path | str | None = None) -> None:
        self.urdf_path = urdf_path
        self.left = OpenArmKinematics(
            OpenArmKinematicsConfig(urdf_path=urdf_path, side="left")
        )
        self.right = OpenArmKinematics(
            OpenArmKinematicsConfig(urdf_path=urdf_path, side="right")
        )

    @property
    def is_available(self) -> bool:
        return self.left.is_available and self.right.is_available

    def check_available(self) -> None:
        if not self.is_available:
            errors = []
            if not self.left.is_available:
                errors.append(f"left: {getattr(self.left, '_import_error', 'unknown')}")
            if not self.right.is_available:
                errors.append(f"right: {getattr(self.right, '_import_error', 'unknown')}")
            raise RuntimeError("OpenArm FK not available:\n" + "\n".join(errors))


def _rotation_matrix_to_quaternion_xyzw(R: np.ndarray) -> np.ndarray:
    """Convert a 3x3 rotation matrix to a unit quaternion [x, y, z, w]."""
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

    q = np.array([x, y, z, w], dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    return q / norm


__all__ = [
    "ArmFKSolution",
    "BiOpenArmKinematics",
    "OpenArmKinematics",
    "OpenArmKinematicsConfig",
]
