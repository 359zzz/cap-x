"""Configuration and capture helpers for OpenArm wrist-mounted cameras.

This module is ROS2-free. It supports:
  * V4L2 capture via OpenCV (lightweight, no RealSense SDK required).
  * Native RealSense capture via pyrealsense2 (aligned depth + intrinsics).
  * Loading eye-in-hand extrinsics from YAML files written by the calibration
    script ``scripts/calibrate_openarm_handeye.py``.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass
class OpenArmCameraConfig:
    """Configuration for one OpenArm wrist camera."""

    name: str = "wrist"
    side: str = "left"  # "left" or "right"
    device: str = "/dev/video0"  # V4L path or RealSense serial number
    backend: str = "auto"  # "auto", "realsense", "v4l"
    width: int = 1280
    height: int = 720
    fps: int = 30
    intrinsics: np.ndarray | None = None  # (3,3) camera matrix for V4L fallback
    distortion: np.ndarray | None = None  # (5,) or None
    T_ee_cam: np.ndarray | None = None  # (4,4) eye-in-hand extrinsics
    # Optional marker size for depth-based point-cloud processing.
    depth_scale: float = 0.001  # RealSense depth in mm by default

    def __post_init__(self) -> None:
        if self.intrinsics is not None:
            self.intrinsics = np.asarray(self.intrinsics, dtype=np.float64)
        if self.distortion is not None:
            self.distortion = np.asarray(self.distortion, dtype=np.float64)
        if self.T_ee_cam is not None:
            self.T_ee_cam = np.asarray(self.T_ee_cam, dtype=np.float64)


def _default_extrinsics_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "env_configs" / "openarm" / "camera_extrinsics"


def load_camera_extrinsics(side: str, extrinsics_dir: Path | str | None = None) -> np.ndarray | None:
    """Load T_ee_cam for a wrist camera from a YAML calibration file.

    Args:
        side: "left" or "right".
        extrinsics_dir: Directory containing ``{side}_wrist.yaml``.

    Returns:
        (4,4) homogeneous transform, or None if the file does not exist.
    """
    if extrinsics_dir is None:
        extrinsics_dir = _default_extrinsics_dir()
    else:
        extrinsics_dir = Path(extrinsics_dir)

    path = extrinsics_dir / f"{side}_wrist.yaml"
    if not path.is_file():
        return None

    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}

    T = payload.get("T_ee_cam")
    if T is None:
        return None
    return np.asarray(T, dtype=np.float64)


def camera_config_from_env(side: str) -> OpenArmCameraConfig:
    """Build a camera config from environment variables.

    Environment variables read:
      * CAPX_OPENARM_{SIDE}_CAMERA_DEVICE
      * CAPX_OPENARM_{SIDE}_CAMERA_BACKEND  (realsense/v4l)
      * CAPX_OPENARM_{SIDE}_CAMERA_WIDTH
      * CAPX_OPENARM_{SIDE}_CAMERA_HEIGHT
      * CAPX_OPENARM_{SIDE}_CAMERA_FPS
      * CAPX_OPENARM_CAMERA_EXTRINSICS_DIR
    """
    prefix = f"CAPX_OPENARM_{side.upper()}_CAMERA"
    device = os.getenv(f"{prefix}_DEVICE", f"/dev/video{2 if side == 'left' else 8}")
    backend = os.getenv(f"{prefix}_BACKEND", "auto")
    width = int(os.getenv(f"{prefix}_WIDTH", "1280"))
    height = int(os.getenv(f"{prefix}_HEIGHT", "720"))
    fps = int(os.getenv(f"{prefix}_FPS", "30"))

    extrinsics_dir = os.getenv("CAPX_OPENARM_CAMERA_EXTRINSICS_DIR")
    T_ee_cam = load_camera_extrinsics(side, extrinsics_dir)

    # A simple V4L fallback intrinsics for 1280x720 RealSense D405/D435 RGB streams.
    intrinsics = None
    if width == 1280 and height == 720:
        intrinsics = np.array([
            [920.0, 0.0, 640.0],
            [0.0, 920.0, 360.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

    return OpenArmCameraConfig(
        name=f"{side}_wrist",
        side=side,
        device=device,
        backend=backend,
        width=width,
        height=height,
        fps=fps,
        intrinsics=intrinsics,
        distortion=None,
        T_ee_cam=T_ee_cam,
    )


class OpenArmCameraCapture:
    """ROS2-free camera capture for one wrist camera."""

    def __init__(self, config: OpenArmCameraConfig) -> None:
        self.config = config
        self._cv2: Any | None = None
        self._rs: Any | None = None
        self._pipeline: Any | None = None
        self._align: Any | None = None
        self._cap: Any | None = None
        self._backend: str = "v4l"

    def start(self) -> None:
        backend = self.config.backend.lower()
        if backend in ("auto", "realsense"):
            try:
                import pyrealsense2 as rs
                self._rs = rs
                self._start_realsense()
                self._backend = "realsense"
                return
            except Exception:
                if backend == "realsense":
                    raise
                # Fall through to V4L.

        self._start_v4l()
        self._backend = "v4l"

    def stop(self) -> None:
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            except Exception:
                pass
            self._pipeline = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def capture(self) -> dict[str, Any]:
        """Capture one frame and return an observation dict.

        Returns a dict with keys:
          * rgb: (H, W, 3) uint8
          * depth: (H, W) float32 meters, or None if unavailable
          * intrinsics: (3, 3) camera matrix
          * T_ee_cam: (4, 4) extrinsics, or None
          * width, height
        """
        if self._backend == "realsense":
            return self._capture_realsense()
        return self._capture_v4l()

    def _start_realsense(self) -> None:
        rs = self._rs
        cfg = rs.config()
        cfg.enable_stream(rs.stream.depth, self.config.width, self.config.height, rs.format.z16, self.config.fps)
        cfg.enable_stream(rs.stream.color, self.config.width, self.config.height, rs.format.bgr8, self.config.fps)
        if self.config.device and not self.config.device.startswith("/dev"):
            cfg.enable_device(self.config.device)
        self._pipeline = rs.pipeline()
        self._pipeline.start(cfg)
        self._align = rs.align(rs.stream.color)
        for _ in range(15):
            frames = self._pipeline.wait_for_frames()
            self._align.process(frames)

    def _capture_realsense(self) -> dict[str, Any]:
        rs = self._rs
        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            raise RuntimeError("RealSense capture failed")

        color = np.asanyarray(color_frame.get_data())
        depth = np.asanyarray(depth_frame.get_data()) * self.config.depth_scale
        rgb = self._cv2.cvtColor(color, self._cv2.COLOR_BGR2RGB)

        intr = color_frame.profile.as_video_stream_profile().intrinsics
        K = np.array([
            [intr.fx, 0.0, intr.ppx],
            [0.0, intr.fy, intr.ppy],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

        return {
            "rgb": rgb,
            "depth": depth.astype(np.float32),
            "intrinsics": K,
            "T_ee_cam": self.config.T_ee_cam,
            "width": rgb.shape[1],
            "height": rgb.shape[0],
        }

    def _start_v4l(self) -> None:
        import cv2
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(self.config.device)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open V4L device {self.config.device}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.config.width))
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.config.height))
        self._cap.set(cv2.CAP_PROP_FPS, float(self.config.fps))
        for _ in range(5):
            self._cap.read()

    def _capture_v4l(self) -> dict[str, Any]:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"Failed to read frame from {self.config.device}")
        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        return {
            "rgb": rgb,
            "depth": None,
            "intrinsics": self.config.intrinsics,
            "T_ee_cam": self.config.T_ee_cam,
            "width": rgb.shape[1],
            "height": rgb.shape[0],
        }


def encode_rgb_to_base64_jpeg(rgb: np.ndarray, quality: int = 90) -> str:
    """Encode an RGB image to a base64 JPEG string for web UI / JSON payloads."""
    import cv2
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("Failed to encode image as JPEG")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


__all__ = [
    "OpenArmCameraConfig",
    "OpenArmCameraCapture",
    "camera_config_from_env",
    "encode_rgb_to_base64_jpeg",
    "load_camera_extrinsics",
]
