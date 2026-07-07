#!/usr/bin/env python3
"""Eye-in-hand calibration for OpenArm wrist-mounted RealSense cameras.

Run this on the IPC. It captures RGB-D frames from a RealSense wrist camera,
detects a chessboard, and uses the robot's joint encoders + OpenArm URDF FK to
calibrate the camera-to-end-effector transform.

Usage:
    export CAPX_OPENARM_LEFT_PORT=can0
    export CAPX_OPENARM_RIGHT_PORT=can1
    export CAPX_OPENARM_URDF=$HOME/robot_workspace/cap-x/third_party/openarm_description/output.urdf
    python scripts/calibrate_openarm_handeye.py --arm left --camera serial_number_or_index --square-size 0.02

Safety:
    The script does **not** move the robot. You manually jog the arm to ~10-15
    diverse poses covering different wrist orientations, then press ENTER to
    capture each pose. Keep the chessboard visible and stationary in front of
    the wrist camera.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def import_pyrealsense2() -> Any:
    try:
        import pyrealsense2 as rs
        return rs
    except ImportError as exc:
        raise RuntimeError(
            "pyrealsense2 is required for calibration. Install it with:\n"
            "  pip install pyrealsense2\n"
            "or build from source if your Python version is not covered by wheels."
        ) from exc


def import_opencv() -> Any:
    try:
        import cv2
        return cv2
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python is required for calibration. Install it with:\n"
            "  pip install opencv-python-headless"
        ) from exc


def import_pinocchio() -> Any:
    try:
        import pinocchio as pin
        return pin
    except ImportError as exc:
        raise RuntimeError(
            "pinocchio is required for FK during calibration. Install it with:\n"
            "  pip install pinocchio"
        ) from exc


def import_runtime() -> Any:
    from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig
    return OpenArmRuntime, OpenArmRuntimeConfig


def import_kinematics() -> Any:
    from capx.integrations.openarm.kinematics import OpenArmKinematics, OpenArmKinematicsConfig
    return OpenArmKinematics, OpenArmKinematicsConfig


class RealSenseCalibrator:
    """Capture aligned RGB-D from a RealSense camera."""

    def __init__(self, camera_id: str | None = None, width: int = 1280, height: int = 720, fps: int = 30) -> None:
        self.rs = import_pyrealsense2()
        self.cv2 = import_opencv()
        self.width = width
        self.height = height
        self.fps = fps
        self.camera_id = camera_id
        self._pipeline = self.rs.pipeline()
        self._cfg = self.rs.config()
        self._profile: Any = None

    def start(self) -> None:
        self._cfg.enable_stream(self.rs.stream.depth, self.width, self.height, self.rs.format.z16, self.fps)
        self._cfg.enable_stream(self.rs.stream.color, self.width, self.height, self.rs.format.bgr8, self.fps)

        if self.camera_id is not None:
            try:
                serial = self.camera_id
                self._cfg.enable_device(serial)
            except Exception:
                # camera_id may be an index; try enabling by context index instead.
                pass

        self._profile = self._pipeline.start(self._cfg)
        align = self.rs.align(self.rs.stream.color)
        self._align = align

        # Let auto-exposure settle.
        for _ in range(30):
            frames = self._pipeline.wait_for_frames()
            self._align.process(frames)
            time.sleep(0.03)

    def stop(self) -> None:
        self._pipeline.stop()

    def capture(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (rgb, depth, intrinsics_matrix)."""
        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)

        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            raise RuntimeError("Failed to capture aligned RGB-D frame")

        depth = np.asanyarray(depth_frame.get_data())  # uint16 mm
        color = np.asanyarray(color_frame.get_data())  # BGR uint8
        rgb = self.cv2.cvtColor(color, self.cv2.COLOR_BGR2RGB)

        intr = color_frame.profile.as_video_stream_profile().intrinsics
        K = np.array([
            [intr.fx, 0.0, intr.ppx],
            [0.0, intr.fy, intr.ppy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

        return rgb, depth, K


class HandEyeCalibration:
    def __init__(self, square_size_m: float, pattern_size: tuple[int, int]) -> None:
        self.cv2 = import_opencv()
        self.square_size_m = square_size_m
        self.pattern_size = pattern_size  # (cols, rows) internal corners
        self.obj_points = self._create_object_points()

    def _create_object_points(self) -> np.ndarray:
        cols, rows = self.pattern_size
        objp = np.zeros((cols * rows, 3), dtype=np.float64)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * self.square_size_m
        return objp

    def detect_pose(self, rgb: np.ndarray, K: np.ndarray) -> tuple[bool, np.ndarray | None, np.ndarray | None]:
        """Return (found, rvec, tvec) for the chessboard in the camera frame."""
        gray = self.cv2.cvtColor(rgb, self.cv2.COLOR_RGB2GRAY)
        found, corners = self.cv2.findChessboardCorners(
            gray, self.pattern_size,
            flags=self.cv2.CALIB_CB_ADAPTIVE_THRESH | self.cv2.CALIB_CB_NORMALIZE_IMAGE,
        )
        if not found:
            return False, None, None

        corners2 = self.cv2.cornerSubPix(
            gray, corners, (11, 11), (-1, -1),
            (self.cv2.TERM_CRITERIA_EPS + self.cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
        )
        ret, rvec, tvec = self.cv2.solvePnP(
            self.obj_points, corners2, K, None,
            flags=self.cv2.SOLVEPNP_ITERATIVE,
        )
        if not ret:
            return False, None, None
        return True, rvec, tvec

    def calibrate(
        self,
        T_base_ee_list: list[np.ndarray],
        rvec_cam_marker_list: list[np.ndarray],
        tvec_cam_marker_list: list[np.ndarray],
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return (R_ee_cam, t_ee_cam)."""
        if len(T_base_ee_list) < 5:
            raise ValueError(f"Need at least 5 poses, got {len(T_base_ee_list)}")

        R_gripper2base = []
        t_gripper2base = []
        for T_base_ee in T_base_ee_list:
            T_ee_base = np.linalg.inv(T_base_ee)
            R_gripper2base.append(T_ee_base[:3, :3])
            t_gripper2base.append(T_ee_base[:3, 3])

        R_target2cam = []
        t_target2cam = []
        for rvec, tvec in zip(rvec_cam_marker_list, tvec_cam_marker_list):
            R_target2cam.append(self.cv2.Rodrigues(rvec)[0])
            t_target2cam.append(tvec.reshape(3))

        R_cam2gripper, t_cam2gripper = self.cv2.calibrateHandEye(
            R_gripper2base, t_gripper2base,
            R_target2cam, t_target2cam,
            method=self.cv2.CALIB_HAND_EYE_TSAI,
        )
        return R_cam2gripper, t_cam2gripper.reshape(3)


def prompt_continue() -> bool:
    try:
        response = input("Press ENTER to capture this pose (or 'q' + ENTER to finish): ")
    except EOFError:
        return False
    return response.strip().lower() != "q"


def main() -> int:
    parser = argparse.ArgumentParser(description="Eye-in-hand calibration for OpenArm wrist camera")
    parser.add_argument("--arm", choices=["left", "right"], required=True, help="Arm to calibrate")
    parser.add_argument("--camera", default=None, help="RealSense serial number (or leave empty for first available)")
    parser.add_argument("--square-size", type=float, default=0.02, help="Chessboard square size in meters (default 0.02)")
    parser.add_argument("--pattern-cols", type=int, default=9, help="Internal chessboard corners per row (default 9)")
    parser.add_argument("--pattern-rows", type=int, default=6, help="Internal chessboard corners per column (default 6)")
    parser.add_argument("--output-dir", type=Path, default=Path("env_configs/openarm/camera_extrinsics"), help="Where to write the YAML")
    parser.add_argument("--urdf", default=None, help="Override CAPX_OPENARM_URDF")
    args = parser.parse_args()

    OpenArmRuntime, OpenArmRuntimeConfig = import_runtime()
    OpenArmKinematics, OpenArmKinematicsConfig = import_kinematics()

    urdf_path = args.urdf or OpenArmKinematicsConfig().urdf_path
    if urdf_path is None:
        print("ERROR: No URDF found. Run scripts/setup_openarm_urdf.sh or set CAPX_OPENARM_URDF.")
        return 1
    urdf_path = Path(urdf_path)
    print(f"Using URDF: {urdf_path}")

    kin = OpenArmKinematics(OpenArmKinematicsConfig(urdf_path=urdf_path, side=args.arm))
    if not kin.is_available:
        print("ERROR: OpenArm FK is not available. Install pinocchio and check the URDF.")
        return 1

    print("Connecting to OpenArm runtime...")
    runtime = OpenArmRuntime(OpenArmRuntimeConfig())
    runtime.connect()
    if not runtime.driver.is_connected:
        print("ERROR: Could not connect to OpenArm.")
        return 1

    print("Starting RealSense camera...")
    camera = RealSenseCalibrator(camera_id=args.camera)
    camera.start()

    calib = HandEyeCalibration(square_size_m=args.square_size, pattern_size=(args.pattern_cols, args.pattern_rows))

    T_base_ee_list: list[np.ndarray] = []
    rvec_list: list[np.ndarray] = []
    tvec_list: list[np.ndarray] = []

    print("\nMove the arm so the chessboard is clearly visible in the wrist camera.")
    print("Capture ~10-15 diverse wrist orientations. Type 'q' when done.\n")

    try:
        while True:
            rgb, depth, K = camera.capture()
            found, rvec, tvec = calib.detect_pose(rgb, K)
            if not found:
                print("  Chessboard not detected. Adjust pose/ lighting and try again.")
                time.sleep(0.5)
                continue

            if not prompt_continue():
                break

            obs = runtime.get_observation()
            joints = obs[f"{args.arm}_arm"]["joint_pos"]
            fk = kin.solve_fk(joints)

            T_base_ee_list.append(fk.T_base_ee)
            rvec_list.append(rvec)
            tvec_list.append(tvec)

            print(f"  Captured pose #{len(T_base_ee_list)}: joints={ {k: round(v,2) for k,v in joints.items()} }")
    finally:
        camera.stop()
        runtime.disconnect()

    if len(T_base_ee_list) < 5:
        print(f"ERROR: Only {len(T_base_ee_list)} poses captured; need at least 5.")
        return 1

    print(f"\nCalibrating T_ee_cam from {len(T_base_ee_list)} poses...")
    R_ee_cam, t_ee_cam = calib.calibrate(T_base_ee_list, rvec_list, tvec_list)
    T_ee_cam = np.eye(4, dtype=np.float64)
    T_ee_cam[:3, :3] = R_ee_cam
    T_ee_cam[:3, 3] = t_ee_cam

    print("T_ee_cam (homogeneous):")
    print(T_ee_cam)

    # Save YAML.
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.arm}_wrist.yaml"

    payload = {
        "side": args.arm,
        "camera_mount": "wrist",
        "parent_link": f"openarm_{args.arm}_ee_base_link",
        "T_ee_cam": T_ee_cam.tolist(),
        "translation_m": t_ee_cam.tolist(),
        "rotation_matrix": R_ee_cam.tolist(),
        "calibration_poses": len(T_base_ee_list),
        "square_size_m": args.square_size,
        "pattern_size": [args.pattern_cols, args.pattern_rows],
    }
    with output_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)

    print(f"\nSaved camera extrinsics to: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
