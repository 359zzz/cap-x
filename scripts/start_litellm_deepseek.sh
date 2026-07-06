#!/usr/bin/env bash
set -euo pipefail

# Start a LiteLLM proxy on the IPC that forwards cap-x LLM requests to DeepSeek API.
#
# Usage:
#   export DEEPSEEK_API_KEY="sk-..."
#   export CAPX_LITELLM_PORT="4000"
#   export CAPX_LITELLM_MODEL="deepseek/deepseek-chat"
#   ./scripts/start_litellm_deepseek.sh
#
# Then point cap-x to:
#   server_url: http://127.0.0.1:4000/v1/chat/completions
#   model: deepseek-chat

if [[ -f "$HOME/capx_env.sh" ]]; then
  source "$HOME/capx_env.sh"
fi

PORT="${CAPX_LITELLM_PORT:-4000}"
MODEL="${CAPX_LITELLM_MODEL:-deepseek/deepseek-chat}"
LOG_PREFIX="[litellm-deepseek]"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "$LOG_PREFIX ERROR: DEEPSEEK_API_KEY is not set." >&2
  exit 1
fi

if ! command -v litellm >/dev/null 2>&1; then
  echo "$LOG_PREFIX ERROR: litellm CLI not found. Install with:" >&2
  echo "  uv pip install litellm" >&2
  exit 1
fi

echo "$LOG_PREFIX bind=0.0.0.0:$PORT"
echo "$LOG_PREFIX model=$MODEL"
echo "$LOG_PREFIX target=https://api.deepseek.com"
echo "$LOG_PREFIX cap-x endpoint=http://127.0.0.1:${PORT}/v1/chat/completions"
echo "$LOG_PREFIX cap-x model=deepseek/deepseek-chat"

exec litellm \
  --model "$MODEL" \
  --api_key "$DEEPSEEK_API_KEY" \
  --port "$PORT" \
  --host "0.0.0.0"
