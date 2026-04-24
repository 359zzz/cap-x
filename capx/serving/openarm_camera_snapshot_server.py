"""Simple single-camera snapshot server for OpenArm perception.

This service exposes:

- ``GET /health``
- ``GET /snapshot``

It is intended to run on the robot-side Linux host and provide a single,
stable camera stream to ``capx.serving.openarm_perception_gateway`` via
``CAPX_OPENARM_CAMERA_SNAPSHOT_URL``.
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException, Response


@dataclass
class CameraSnapshotConfig:
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    jpeg_quality: int = 90
    fourcc: str | None = "MJPG"
    warmup_frames: int = 4
    refresh_reads: int = 2
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotate_deg: int = 0


class CameraSnapshotSource:
    def __init__(self, config: CameraSnapshotConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._capture: cv2.VideoCapture | None = None
        self._opened_at: float | None = None
        self._last_error: str | None = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def read_snapshot(self) -> bytes:
        with self._lock:
            frame = self._read_frame_locked()
        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self._config.jpeg_quality)],
        )
        if not success:
            raise RuntimeError("Failed to encode frame as JPEG.")
        return encoded.tobytes()

    def status(self) -> dict[str, Any]:
        with self._lock:
            is_open = self._capture is not None and self._capture.isOpened()
            return {
                "status": "ok",
                "device": self._config.device,
                "is_open": is_open,
                "width": self._config.width,
                "height": self._config.height,
                "fps": self._config.fps,
                "fourcc": self._config.fourcc,
                "opened_at": self._opened_at,
                "last_error": self._last_error,
            }

    def _read_frame_locked(self):  # type: ignore[no-untyped-def]
        capture = self._ensure_open_locked()
        frame = None
        ok = False
        attempts = max(int(self._config.refresh_reads), 1)
        for _ in range(attempts):
            ok, frame = capture.read()
        if not ok or frame is None:
            self._last_error = "Camera read failed."
            self._close_locked()
            raise RuntimeError(f"Failed to read frame from camera device {self._config.device}.")
        return self._transform_frame(frame)

    def _ensure_open_locked(self) -> cv2.VideoCapture:
        if self._capture is not None and self._capture.isOpened():
            return self._capture

        self._close_locked()
        capture = self._open_capture(self._config.device)
        if not capture.isOpened():
            capture.release()
            self._last_error = f"Cannot open camera device {self._config.device}."
            raise RuntimeError(self._last_error)

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._config.width))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._config.height))
        capture.set(cv2.CAP_PROP_FPS, float(self._config.fps))
        if self._config.fourcc:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self._config.fourcc))

        warmup_frames = max(int(self._config.warmup_frames), 0)
        for _ in range(warmup_frames):
            capture.read()

        self._capture = capture
        self._opened_at = time.time()
        self._last_error = None
        return capture

    def _open_capture(self, device: str) -> cv2.VideoCapture:
        backends: list[int | None] = []
        if hasattr(cv2, "CAP_V4L2"):
            backends.append(int(cv2.CAP_V4L2))
        backends.append(None)
        for backend in backends:
            capture = cv2.VideoCapture(device, backend) if backend is not None else cv2.VideoCapture(device)
            if capture.isOpened():
                return capture
            capture.release()
        return cv2.VideoCapture(device)

    def _close_locked(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _transform_frame(self, frame):  # type: ignore[no-untyped-def]
        if self._config.flip_horizontal:
            frame = cv2.flip(frame, 1)
        if self._config.flip_vertical:
            frame = cv2.flip(frame, 0)
        if self._config.rotate_deg == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self._config.rotate_deg == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self._config.rotate_deg == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame


def create_app(config: CameraSnapshotConfig | None = None) -> FastAPI:
    cfg = config or CameraSnapshotConfig()
    source = CameraSnapshotSource(cfg)
    app = FastAPI(
        title="cap-x OpenArm Camera Snapshot Server",
        description="Single-camera snapshot service for OpenArm perception.",
        version="1.0.0",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return source.status()

    @app.get("/snapshot")
    async def snapshot() -> Response:
        try:
            image_bytes = source.read_snapshot()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(content=image_bytes, media_type="image/jpeg")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        source.close()

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single-camera snapshot server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8011, help="Bind port.")
    parser.add_argument(
        "--device",
        default="/dev/video0",
        help="Camera device path, preferably a stable /dev/v4l/by-id symlink.",
    )
    parser.add_argument("--width", type=int, default=1280, help="Requested frame width.")
    parser.add_argument("--height", type=int, default=720, help="Requested frame height.")
    parser.add_argument("--fps", type=int, default=30, help="Requested FPS.")
    parser.add_argument("--jpeg-quality", type=int, default=90, help="JPEG quality 1-100.")
    parser.add_argument(
        "--fourcc",
        default="MJPG",
        help="Preferred FOURCC such as MJPG or YUYV. Use 'none' to skip.",
    )
    parser.add_argument("--warmup-frames", type=int, default=4, help="Frames to discard after open.")
    parser.add_argument("--refresh-reads", type=int, default=2, help="Frames to read per snapshot.")
    parser.add_argument("--flip-horizontal", action="store_true", help="Mirror the image horizontally.")
    parser.add_argument("--flip-vertical", action="store_true", help="Flip the image vertically.")
    parser.add_argument(
        "--rotate-deg",
        type=int,
        default=0,
        choices=(0, 90, 180, 270),
        help="Rotate output JPEG by 0/90/180/270 degrees.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    fourcc = None if str(args.fourcc).lower() == "none" else args.fourcc
    config = CameraSnapshotConfig(
        device=args.device,
        width=args.width,
        height=args.height,
        fps=args.fps,
        jpeg_quality=args.jpeg_quality,
        fourcc=fourcc,
        warmup_frames=args.warmup_frames,
        refresh_reads=args.refresh_reads,
        flip_horizontal=args.flip_horizontal,
        flip_vertical=args.flip_vertical,
        rotate_deg=args.rotate_deg,
    )
    uvicorn.run(create_app(config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
