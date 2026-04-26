#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/capx_env.sh" ]]; then
  source "$HOME/capx_env.sh"
fi

CAPX_REPO_DIR="${CAPX_REPO_DIR:-$HOME/cap-x}"
HOST="${CAPX_OPENARM_PERCEPTION_HOST:-127.0.0.1}"
PORT="${CAPX_OPENARM_PERCEPTION_PORT:-8000}"

export CAPX_OPENARM_CAMERA_SNAPSHOT_URL="${CAPX_OPENARM_CAMERA_SNAPSHOT_URL:-http://127.0.0.1:8011/snapshot}"
export CAPX_OPENARM_VISION_MODEL="${CAPX_OPENARM_VISION_MODEL:-qwen3.6-plus}"
export CAPX_OPENARM_VISION_SERVER_URL="${CAPX_OPENARM_VISION_SERVER_URL:-${CAPX_LLM_SERVER_URL:-http://127.0.0.1:8110/chat/completions}}"

PYTHON_BIN="$(command -v python)"
LOG_PREFIX="[8000-gateway]"

echo "$LOG_PREFIX repo=$CAPX_REPO_DIR"
echo "$LOG_PREFIX bind=$HOST:$PORT"
echo "$LOG_PREFIX snapshot=$CAPX_OPENARM_CAMERA_SNAPSHOT_URL"
echo "$LOG_PREFIX model=$CAPX_OPENARM_VISION_MODEL"
echo "$LOG_PREFIX server=$CAPX_OPENARM_VISION_SERVER_URL"
echo "$LOG_PREFIX python=$PYTHON_BIN"

if [[ ! -f "$CAPX_REPO_DIR/capx/serving/openarm_perception_gateway.py" ]]; then
  echo "$LOG_PREFIX ERROR: missing capx repo or gateway file: $CAPX_REPO_DIR" >&2
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
  echo "$LOG_PREFIX Hint: choose another CAPX_OPENARM_PERCEPTION_PORT or stop the conflicting process." >&2
  exit 1
fi

cd "$CAPX_REPO_DIR"

exec "$PYTHON_BIN" -m capx.serving.openarm_perception_gateway \
  --host "$HOST" \
  --port "$PORT" \
  --model "$CAPX_OPENARM_VISION_MODEL" \
  --server-url "$CAPX_OPENARM_VISION_SERVER_URL" \
  --camera-snapshot-url "$CAPX_OPENARM_CAMERA_SNAPSHOT_URL"
