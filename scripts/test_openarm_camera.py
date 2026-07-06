#!/usr/bin/env python3
"""Minimal OpenArm camera test.

Run this on the IPC to capture one frame and save it to disk.
You can then scp the file to your laptop to visually verify focus/exposure.

Usage (direct V4L device):
    python scripts/test_openarm_camera.py --device /dev/video0 --output /tmp/openarm_cam.jpg

Usage (snapshot server already running):
    python scripts/test_openarm_camera.py --snapshot-url http://127.0.0.1:8011/snapshot --output /tmp/openarm_cam.jpg
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path
from typing import Any

import requests


def capture_from_snapshot(url: str) -> bytes:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.content


def capture_from_v4l(device: str, width: int, height: int, fps: int) -> bytes:
    import cv2

    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera device {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    cap.set(cv2.CAP_PROP_FPS, float(fps))

    # Discard a few frames for auto-exposure/white-balance to settle.
    for _ in range(5):
        cap.read()

    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        raise RuntimeError(f"Failed to read frame from {device}")

    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")

    return encoded.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal OpenArm camera test")
    parser.add_argument(
        "--device",
        default="/dev/video0",
        help="V4L camera device path (default: /dev/video0)",
    )
    parser.add_argument(
        "--snapshot-url",
        default=None,
        help="If set, fetch image from an existing snapshot server instead of opening V4L directly",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Requested capture width",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Requested capture height",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Requested capture FPS",
    )
    parser.add_argument(
        "--output",
        default="/tmp/openarm_camera_test.jpg",
        help="Where to save the captured JPEG",
    )
    args = parser.parse_args()

    print(f"Capturing image...")
    if args.snapshot_url:
        print(f"  source: snapshot server {args.snapshot_url}")
        image_bytes = capture_from_snapshot(args.snapshot_url)
    else:
        print(f"  source: V4L device {args.device} ({args.width}x{args.height}@{args.fps})")
        image_bytes = capture_from_v4l(args.device, args.width, args.height, args.fps)

    output_path = Path(args.output)
    output_path.write_bytes(image_bytes)
    print(f"Saved {len(image_bytes)} bytes to {output_path.resolve()}")

    # Also print a tiny base64 preview so the user can sanity-check without scp.
    preview = base64.b64encode(image_bytes[:64]).decode("ascii")
    print(f"JPEG header (base64): {preview}...")

    print("\nTo view on your laptop:")
    print(f"  scp <ipc_user>@<IPC_IP>:{output_path.resolve()} ./openarm_cam.jpg")
    print("  # Then open openarm_cam.jpg locally")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
