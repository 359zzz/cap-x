# OpenArm + Nanobot QuickStart

This guide covers the current `cap-x` integration for:

- `OpenArm` dual-arm real robot control
- in-repo `OpenArm` low-level CAN driver
- `openclaw_realsense_agent` perception/tactile service reuse
- `nanobot`-style provider, relay, shell, and HTTP app gateway integration
- `cap-x` web UI as the execution surface

Current code status:

- `cap-x` now contains an internal OpenArm runtime, motion asset registry, executor, recording flow, and control API
- `cap-x` now exposes nanobot relay endpoints under `/api/nanobot/...`
- `cap-x` now provides an embedded nanobot console shell and an embedded HTTP gateway for app-side integration
- `cap-x` now provides an `openarm_doctor` self-check CLI for embedded driver, dependency, asset, perception, and relay validation
- the remaining work is now mainly app-specific protocol adaptation and real robot asset calibration, not core architecture bring-up

Companion design docs now committed in-repo:

- [../.codex/plans/README.md](../.codex/plans/README.md)

The index page above links to the detailed motion-vocabulary, API/recording, and nanobot architecture plans.

## 0. Recommended Bring-Up Order

If you want the shortest path to a stable real-robot bring-up, use this order:

1. set environment variables
2. start `openclaw_realsense_agent`
3. run `python -m capx.cli.openarm_doctor`
4. start the `cap-x` web server with `env_configs/openarm/openarm_motion_real.yaml`
5. choose one outer shell:
   - local debugging: `python -m capx.cli.nanobot_console`
   - app integration: `python -m capx.cli.nanobot_http_gateway`

Recommended first smoke test:

1. `python -m capx.cli.openarm_doctor`
2. `python -m capx.cli.nanobot_task health`
3. start one task with `python -m capx.cli.nanobot_task start ...`
4. confirm task progress from web UI or relay status

Important runtime assumptions:

- only one active robot task is allowed at a time
- the HTTP app gateway is a polling bridge, not a websocket stream
- the main execution path is motion primitives plus combo expansion, not long trajectory replay

Current limitations you should assume on a fresh clone:

- the overall `cap-x` repository still contains many GPU-oriented simulator and perception dependencies; only the OpenArm path is intentionally CPU-oriented
- `capx/assets/openarm/` ships without calibrated real-robot motion assets, so you must record anchors / primitive templates / combo templates before expecting meaningful real motion

## 1. Environment Variables

PowerShell example:

```powershell
$env:CAPX_OPENARM_LEFT_PORT = 'YOUR_LEFT_ARM_PORT'
$env:CAPX_OPENARM_RIGHT_PORT = 'YOUR_RIGHT_ARM_PORT'
$env:CAPX_OPENARM_LEFT_CAN_INTERFACE = 'socketcan'
$env:CAPX_OPENARM_RIGHT_CAN_INTERFACE = 'socketcan'
$env:CAPX_OPENARM_PERCEPTION_ENABLED = 'true'
$env:CAPX_OPENARM_PERCEPTION_BASE_URL = 'http://127.0.0.1:8000'
$env:CAPX_WEB_BASE_URL = 'http://127.0.0.1:8200'

# nanobot-compatible provider base URL
$env:LLM_BASE_URL = 'http://127.0.0.1:8110'
$env:LLM_MODEL_NAME = 'openai/gpt-5.4'
$env:LLM_API_KEY = 'no-key'

# cap-x expects a chat-completions endpoint
$env:CAPX_LLM_SERVER_URL = 'http://127.0.0.1:8110/chat/completions'
```

Notes:

- `CAPX_OPENARM_LEFT_PORT` and `CAPX_OPENARM_RIGHT_PORT` should point at the CAN channels or interfaces used by your left/right OpenArm arms
- `python-can` is now a direct `cap-x` dependency for the embedded OpenArm low-level driver; no separate `Evo-RL` checkout is required
- if your OpenAI-compatible upstream already supports both styles, keep `LLM_BASE_URL` and `CAPX_LLM_SERVER_URL` pointed at the same service family

## 2. Start the Perception Service

From your `openclaw_realsense_agent` project:

```powershell
$env:OPENCLAW_AGENT_DIR = 'E:\path\to\openclaw_realsense_agent'
Set-Location $env:OPENCLAW_AGENT_DIR
uvicorn app.service.main:app --host 127.0.0.1 --port 8000
```

The adapter inside `cap-x` currently expects:

- `GET /health`
- `GET /tactile/health`
- `POST /tactile/read`
- `POST /detect_once`

If the external `openclaw_realsense_agent` cannot start on port `8000`, you can use the
in-repo Qwen/OpenAI-compatible fallback gateway instead. It exposes the same core
OpenClaw-compatible routes plus `POST /describe_once`, and returns both visual text
results and the image it analyzed so Nanobot can forward the image back to the app:

```powershell
# Start the local OpenAI-compatible proxy on 8110 against DashScope/Qwen.
python -m capx.serving.openrouter_server `
  --api-key $env:DASHSCOPE_API_KEY `
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 `
  --port 8110

# Start the in-repo OpenArm perception gateway on 8000.
# Use either a camera snapshot URL or a test image path as the image source.
$env:CAPX_OPENARM_CAMERA_SNAPSHOT_URL = 'http://127.0.0.1:8001/snapshot'
python -m capx.serving.openarm_perception_gateway `
  --port 8000 `
  --model qwen-vl-max-latest `
  --server-url http://127.0.0.1:8110/chat/completions
```

If you do not already have a camera service on `8001`, you can start the
in-repo single-camera snapshot server on the robot-side Linux host and point it
at one explicit V4L2 device:

```bash
python -m capx.serving.openarm_camera_snapshot_server \
  --host 127.0.0.1 \
  --port 8001 \
  --device /dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._Dabai_DC1_CC1T35300ED-video-index0

curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/snapshot --output snapshot.jpg
```

If `8000` is already occupied or still unreliable, run the gateway on another port and
point the OpenArm adapter at it:

```powershell
python -m capx.serving.openarm_perception_gateway --port 8010
$env:CAPX_OPENARM_PERCEPTION_BASE_URL = 'http://127.0.0.1:8010'
```

For a quick non-camera smoke test:

```powershell
python -m capx.serving.openarm_perception_gateway `
  --port 8000 `
  --camera-image-path C:\path\to\test_scene.png `
  --model qwen-vl-max-latest `
  --server-url http://127.0.0.1:8110/chat/completions
```

The OpenArm code API now includes `describe_scene(...)`. For a command such as
“先看看桌上有什么，再决定抓哪个物体”, the model can call `describe_scene()` or
`detect_target(...)`; returned `image_base64` / `images` are logged as execution
step media and relayed through Nanobot status/outbound messages.

## 3. Check Provider Wiring

Use the embedded nanobot-compatible provider wrapper:

```powershell
Set-Location C:\Users\zhang\Desktop\cap-x
python -m capx.cli.nanobot_provider ping --api-base $env:LLM_BASE_URL --model $env:LLM_MODEL_NAME
python -m capx.cli.nanobot_provider chat --api-base $env:LLM_BASE_URL --model $env:LLM_MODEL_NAME "Reply with the word READY"
```

## 4. Start cap-x Web UI and Relay

```powershell
Set-Location C:\Users\zhang\Desktop\cap-x
uv run --no-sync --active capx/envs/launch.py `
  --config-path env_configs/openarm/openarm_motion_real.yaml `
  --model $env:LLM_MODEL_NAME `
  --server-url $env:CAPX_LLM_SERVER_URL
```

Then open:

```text
http://127.0.0.1:8200
```

The config used above is:

- [env_configs/openarm/openarm_motion_real.yaml](../env_configs/openarm/openarm_motion_real.yaml)

## 5. Drive Tasks Through the Nanobot Relay

Health check:

```powershell
python -m capx.cli.nanobot_task health
```

Start a task:

```powershell
python -m capx.cli.nanobot_task start `
  --config-path env_configs/openarm/openarm_motion_real.yaml `
  --model $env:LLM_MODEL_NAME `
  --llm-server-url $env:CAPX_LLM_SERVER_URL `
  "把左手抬到胸前并等待下一步指令"
```

Read the returned `session_id`, then poll status:

```powershell
python -m capx.cli.nanobot_task status <SESSION_ID>
```

Inject a follow-up instruction when the task is in `awaiting_user_input`:

```powershell
python -m capx.cli.nanobot_task inject <SESSION_ID> "改为轻微张开左腕，并再次等待"
```

Stop the task:

```powershell
python -m capx.cli.nanobot_task stop <SESSION_ID>
```

The relay endpoints exposed by `cap-x` are:

- `GET /api/nanobot/health`
- `POST /api/nanobot/tasks/start`
- `GET /api/nanobot/tasks/{session_id}`
- `POST /api/nanobot/tasks/{session_id}/inject`
- `POST /api/nanobot/tasks/{session_id}/stop`

Main implementation files:

- [capx/web/server.py](../capx/web/server.py)
- [capx/web/nanobot_relay.py](../capx/web/nanobot_relay.py)
- [capx/cli/nanobot_task.py](../capx/cli/nanobot_task.py)
- [capx/cli/nanobot_provider.py](../capx/cli/nanobot_provider.py)

## 6. Run the Embedded Nanobot Console Shell

This is the first in-repo nanobot-style outer shell inside `cap-x`.

It does not depend on the external `nanobot-main` runtime. Instead it:

- consumes natural-language messages from a local console channel
- starts a task through the cap-x nanobot relay
- watches task status
- injects follow-up guidance automatically when the task enters `awaiting_user_input`

Start the console shell after the web server is already running:

```powershell
python -m capx.cli.nanobot_console `
  --server http://127.0.0.1:8200 `
  --config-path env_configs/openarm/openarm_motion_real.yaml `
  --model $env:LLM_MODEL_NAME `
  --llm-server-url $env:CAPX_LLM_SERVER_URL
```

Then type:

```text
把左手抬到胸前
/status
改成轻微张开左腕
/stop
```

Main shell files:

- [capx/nanobot/robot_shell.py](../capx/nanobot/robot_shell.py)
- [capx/nanobot/task_client.py](../capx/nanobot/task_client.py)
- [capx/cli/nanobot_console.py](../capx/cli/nanobot_console.py)

## 7. Run the Embedded Nanobot Gateway

There are now two gateway entry modes inside `cap-x`.

### 7.1 Console Gateway Runtime

This mode is useful for local bring-up and debugging. It exposes:

- channel base classes
- channel manager
- runtime bundle
- gateway-style startup path

Start it with the built-in console channel:

```powershell
python -m capx.cli.nanobot_gateway `
  --server http://127.0.0.1:8200 `
  --config-path env_configs/openarm/openarm_motion_real.yaml `
  --model $env:LLM_MODEL_NAME `
  --llm-server-url $env:CAPX_LLM_SERVER_URL
```

### 7.2 HTTP App Gateway

This mode is the in-repo replacement for the “external app shell” layer. It keeps the nanobot shell inside `cap-x`, and exposes a simple HTTP polling bridge for your app or any custom front-end.

Start it:

```powershell
python -m capx.cli.nanobot_http_gateway `
  --host 127.0.0.1 `
  --port 8300 `
  --server http://127.0.0.1:8200 `
  --config-path env_configs/openarm/openarm_motion_real.yaml `
  --model $env:LLM_MODEL_NAME `
  --llm-server-url $env:CAPX_LLM_SERVER_URL
```

Gateway endpoints:

- `GET /health`
- `GET /channels/status`
- `POST /channels/http/inbound`
- `GET /channels/http/outbound?chat_id=<CHAT_ID>&wait_ms=2000`

Recommended app-side contract:

- your app keeps one stable `chat_id` per conversation or operator session
- your app posts user text to `/channels/http/inbound`
- your app polls `/channels/http/outbound` with the same `chat_id`
- when the current robot task enters `awaiting_user_input`, sending another natural-language message with the same `chat_id` will inject a follow-up instruction instead of starting a second task
- if another `chat_id` sends a new task while one task is active, it will receive a busy reply instead of preempting the running task

PowerShell example:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8300/channels/http/inbound `
  -ContentType 'application/json' `
  -Body (@{
    chat_id = 'app-chat-1'
    sender_id = 'operator-1'
    content = '把左手抬到胸前'
  } | ConvertTo-Json)

Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8300/channels/http/outbound?chat_id=app-chat-1&wait_ms=2000'
```

Minimal outbound payload shape:

```json
{
  "count": 1,
  "messages": [
    {
      "channel": "http",
      "chat_id": "app-chat-1",
      "content": "已启动机器人任务。\nsession_id: ...",
      "reply_to": null,
      "media": [],
      "metadata": {
        "session_id": "...",
        "action": "start"
      }
    }
  ]
}
```

Main gateway files:

- [capx/nanobot/channels/base.py](../capx/nanobot/channels/base.py)
- [capx/nanobot/channels/console.py](../capx/nanobot/channels/console.py)
- [capx/nanobot/channels/http_bridge.py](../capx/nanobot/channels/http_bridge.py)
- [capx/nanobot/channels/manager.py](../capx/nanobot/channels/manager.py)
- [capx/nanobot/runtime.py](../capx/nanobot/runtime.py)
- [capx/nanobot/gateway_app.py](../capx/nanobot/gateway_app.py)
- [capx/cli/nanobot_gateway.py](../capx/cli/nanobot_gateway.py)
- [capx/cli/nanobot_http_gateway.py](../capx/cli/nanobot_http_gateway.py)

## 8. Run OpenArm Doctor

Use this before first deploy or before real robot bring-up:

```powershell
python -m capx.cli.openarm_doctor
```

If you want to also test the real OpenArm hardware connection:

```powershell
python -m capx.cli.openarm_doctor --connect-robot
```

What it checks:

- embedded OpenArm low-level driver availability
- `python-can` dependency availability
- left/right port configuration
- motion asset recording status
- perception service health
- cap-x nanobot relay health
- optional real robot connection

Main doctor file:

- [capx/cli/openarm_doctor.py](../capx/cli/openarm_doctor.py)

## 9. Manual Motion Asset Recording

Check current asset status:

```powershell
python -m capx.cli.openarm_assets status
```

Record anchors after manually moving the robot into position:

```powershell
python -m capx.cli.openarm_assets record-anchor left_neutral_ready --arm-mode single --arm left
python -m capx.cli.openarm_assets record-anchor right_neutral_ready --arm-mode single --arm right
python -m capx.cli.openarm_assets record-anchor home --arm-mode both
python -m capx.cli.openarm_assets record-anchor safe_standby --arm-mode both
```

Record a primitive template:

```powershell
python -m capx.cli.openarm_assets record-primitive left raise_upper_arm medium left_neutral_ready --end-region-hint left_front_mid
python -m capx.cli.openarm_assets record-primitive right wrist_in small right_neutral_ready --end-region-hint right_chest_front
```

Bootstrap combo templates:

```powershell
python -m capx.cli.openarm_assets bootstrap-combos --overwrite
```

Create or refresh one combo template:

```powershell
python -m capx.cli.openarm_assets record-combo hand_to_chest --arm-mode single --magnitude medium
python -m capx.cli.openarm_assets record-combo both_arms_open --arm-mode both --magnitude medium
```

Main recording and asset files:

- [capx/cli/openarm_assets.py](../capx/cli/openarm_assets.py)
- [capx/integrations/openarm/assets.py](../capx/integrations/openarm/assets.py)
- [capx/integrations/openarm/recording.py](../capx/integrations/openarm/recording.py)
- [capx/assets/openarm/README.md](../capx/assets/openarm/README.md)

## 10. Recording and Execution Model

The current execution path is not "replay a long demonstration trajectory".

Primitive execution path:

1. find the nearest allowed start anchor
2. move to that anchor if needed
3. load the primitive template for `arm + primitive + magnitude + start_anchor`
4. apply the stored joint delta in small blocking steps
5. return structured execution metadata to the LLM and web UI

Combo execution path:

1. load the combo template
2. expand it into primitive phases
3. execute each phase in order
4. use checkpoints and recovery anchors if later phases fail

High-level OpenArm executor helpers now available on top of the motion vocabulary:

- `get_tactile_health()`
- `estimate_arm_region(arm)`
- `align_to_target(arm, target_name)`
- `approach_target(arm, target_name)`
- `descend_until_contact(arm, ...)`
- `grasp_with_tactile_guard(arm, ...)`
- `release_grasp(arm, ...)`
- `handover_to_center(arm, receive_mode=False, ...)`

What the recorder stores today:

- anchor joint states
- primitive joint deltas relative to a named start anchor
- combo phase definitions and recovery anchors

What it does not use as the main runtime path:

- full long-horizon demonstration replay
- dataset episode playback as the primary control primitive

This matches the current design goal: "动作原语为主，受限关节控制为辅，复杂规划放后面".

## 11. Common Troubleshooting Commands

Check the full deployment surface:

```powershell
python -m capx.cli.openarm_doctor
```

Check relay health only:

```powershell
python -m capx.cli.nanobot_task health
```

Check current asset recording status:

```powershell
python -m capx.cli.openarm_assets status
```

Check HTTP gateway health:

```powershell
Invoke-RestMethod http://127.0.0.1:8300/health
Invoke-RestMethod http://127.0.0.1:8300/channels/status
```

If the robot does not move as expected, check in this order:

1. `openarm_doctor` output
2. `cap-x` web UI session state
3. perception service `/health` and `/tactile/health`
4. whether the required anchor and primitive assets have actually been recorded
5. whether the current task is blocked waiting for user input instead of still executing
