#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/capx_env.sh" ]]; then
  source "$HOME/capx_env.sh"
fi

CAPX_REPO_DIR="${CAPX_REPO_DIR:-$HOME/cap-x}"
HOST="${CAPX_OPENARM_CAMERA_HOST:-127.0.0.1}"
PORT="${CAPX_OPENARM_CAMERA_PORT:-8001}"
DEVICE="${CAPX_OPENARM_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Dabai_DC1_CC1T35300ED-video-index0}"
WIDTH="${CAPX_OPENARM_CAMERA_WIDTH:-1280}"
HEIGHT="${CAPX_OPENARM_CAMERA_HEIGHT:-720}"
FPS="${CAPX_OPENARM_CAMERA_FPS:-30}"
JPEG_QUALITY="${CAPX_OPENARM_CAMERA_JPEG_QUALITY:-90}"
FOURCC="${CAPX_OPENARM_CAMERA_FOURCC:-MJPG}"
ROTATE_DEG="${CAPX_OPENARM_CAMERA_ROTATE_DEG:-0}"

echo "[8001-camera] repo=$CAPX_REPO_DIR"
echo "[8001-camera] bind=$HOST:$PORT"
echo "[8001-camera] device=$DEVICE"
echo "[8001-camera] resolution=${WIDTH}x${HEIGHT}"
echo "[8001-camera] fps=$FPS"
echo "[8001-camera] fourcc=$FOURCC"
echo "[8001-camera] rotate=$ROTATE_DEG"
echo "[8001-camera] python=$(command -v python)"

if [[ ! -f "$CAPX_REPO_DIR/capx/serving/openarm_camera_snapshot_server.py" ]]; then
  echo "[8001-camera] ERROR: 找不到 capx 仓库: $CAPX_REPO_DIR" >&2
  exit 1
fi

cd "$CAPX_REPO_DIR"

exec python -m capx.serving.openarm_camera_snapshot_server \
  --host "$HOST" \
  --port "$PORT" \
  --device "$DEVICE" \
  --width "$WIDTH" \
  --height "$HEIGHT" \
  --fps "$FPS" \
  --jpeg-quality "$JPEG_QUALITY" \
  --fourcc "$FOURCC" \
  --rotate-deg "$ROTATE_DEG"
