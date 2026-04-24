#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/capx_env.sh" ]]; then
  source "$HOME/capx_env.sh"
fi

CAPX_REPO_DIR="${CAPX_REPO_DIR:-$HOME/cap-x}"
HOST="${CAPX_OPENARM_CAMERA_HOST:-127.0.0.1}"
PORT="${CAPX_OPENARM_CAMERA_PORT:-8011}"
DEVICE="${CAPX_OPENARM_CAMERA_DEVICE:-/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Dabai_DC1_CC1T35300ED-video-index0}"
WIDTH="${CAPX_OPENARM_CAMERA_WIDTH:-1280}"
HEIGHT="${CAPX_OPENARM_CAMERA_HEIGHT:-720}"
FPS="${CAPX_OPENARM_CAMERA_FPS:-30}"
JPEG_QUALITY="${CAPX_OPENARM_CAMERA_JPEG_QUALITY:-90}"
FOURCC="${CAPX_OPENARM_CAMERA_FOURCC:-MJPG}"
ROTATE_DEG="${CAPX_OPENARM_CAMERA_ROTATE_DEG:-0}"
PYTHON_BIN="$(command -v python)"
LOG_PREFIX="[dabai-camera]"

echo "$LOG_PREFIX repo=$CAPX_REPO_DIR"
echo "$LOG_PREFIX bind=$HOST:$PORT"
echo "$LOG_PREFIX device=$DEVICE"
echo "$LOG_PREFIX resolution=${WIDTH}x${HEIGHT}"
echo "$LOG_PREFIX fps=$FPS"
echo "$LOG_PREFIX fourcc=$FOURCC"
echo "$LOG_PREFIX rotate=$ROTATE_DEG"
echo "$LOG_PREFIX python=$PYTHON_BIN"

if [[ ! -f "$CAPX_REPO_DIR/capx/serving/openarm_camera_snapshot_server.py" ]]; then
  echo "$LOG_PREFIX ERROR: capx repo not found: $CAPX_REPO_DIR" >&2
  exit 1
fi

port_in_use() {
  "$PYTHON_BIN" - "$HOST" "$PORT" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sock.connect((host, port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()

raise SystemExit(0)
PY
}

detect_existing_service() {
  "$PYTHON_BIN" - "$HOST" "$PORT" <<'PY'
import json
import sys
import urllib.error
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])
base = f"http://{host}:{port}"

service = "unknown"
try:
    with urllib.request.urlopen(base + "/health", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
        if isinstance(payload, dict):
            service = str(payload.get("service") or payload.get("status") or service)
except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
    pass

print(service)
PY
}

if port_in_use; then
  EXISTING_SERVICE="$(detect_existing_service)"
  echo "$LOG_PREFIX ERROR: $HOST:$PORT is already in use, service=$EXISTING_SERVICE" >&2
  echo "$LOG_PREFIX Hint: choose another CAPX_OPENARM_CAMERA_PORT or stop the conflicting process." >&2
  echo "$LOG_PREFIX Hint: update CAPX_OPENARM_CAMERA_SNAPSHOT_URL to http://$HOST:$PORT/snapshot." >&2
  exit 1
fi

cd "$CAPX_REPO_DIR"

exec "$PYTHON_BIN" -m capx.serving.openarm_camera_snapshot_server \
  --host "$HOST" \
  --port "$PORT" \
  --device "$DEVICE" \
  --width "$WIDTH" \
  --height "$HEIGHT" \
  --fps "$FPS" \
  --jpeg-quality "$JPEG_QUALITY" \
  --fourcc "$FOURCC" \
  --rotate-deg "$ROTATE_DEG"
