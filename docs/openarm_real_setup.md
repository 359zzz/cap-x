# OpenArm Real Robot Setup Guide

This document describes how to run a real OpenArm dual-arm robot with CaP-X using two Intel RealSense wrist cameras.

## Hardware Architecture

```
[Industrial PC / IPC]
  CPU: x86_64, no discrete GPU
  OS: Ubuntu 22.04/24.04
  Connected to:
    - OpenArm dual-arm follower (left: can0, right: can1)
    - Left wrist RealSense (RGB on /dev/video2)
    - Right wrist RealSense (RGB on /dev/video8)
  Software:
    - CaP-X main program + Web UI
    - LiteLLM proxy -> DeepSeek API
    - OpenArm camera snapshot server (optional)
    - OpenArm perception gateway (optional)

[GPU Server / Pro 6000]
  GPU: NVIDIA RTX (CUDA)
  Software:
    - SAM3 server           :8114
    - ContactGraspnet server :8115
    - Pyroki IK server       :8116

[Operator Laptop]
  - SSH to IPC
  - Browser to http://<IPC_IP>:8200
```

## Branches & Code

Use the `capx` branch which contains OpenArm + LiteLLM configs:

```bash
git clone -b capx https://github.com/359zzz/cap-x.git
cd cap-x
git checkout capx
```

## Environment Setup on IPC

### 1. Python Virtual Environment

```bash
cd ~/robot_workspace/cap-x
uv venv --python 3.10 --clear
source .venv/bin/activate
uv pip install "python-can>=4.2,<5" numpy scipy pillow pyyaml requests opencv-python-headless
```

### 2. CAN Interfaces (CAN-FD)

OpenArm uses CAN-FD. Bring both interfaces up:

```bash
sudo ip link set can0 down
sudo ip link set can1 down
sudo ip link set can0 up type can bitrate 1000000 dbitrate 5000000 fd on
sudo ip link set can1 up type can bitrate 1000000 dbitrate 5000000 fd on

# Verify
ip link show can0
ip link show can1
```

Expected: `state UP` and `mtu 72` (indicates CAN-FD).

### 3. OpenArm Driver Environment

```bash
export CAPX_OPENARM_LEFT_PORT="can0"
export CAPX_OPENARM_RIGHT_PORT="can1"
export CAPX_OPENARM_CALIBRATION_DIR="$HOME/.capx/openarm/calibration"
```

### 4. Calibration

If no calibration file exists, run interactive calibration once:

```bash
export CAPX_OPENARM_AUTO_CALIBRATE="true"
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_minimal.py --arm left --no-motion
```

Place both arms in a safe hanging zero posture with grippers closed, then follow the prompts.

Calibration is saved to:

```bash
~/.capx/openarm/calibration/bi_openarm_follower/capx_openarm.json
```

After calibration, disable auto-calibrate:

```bash
export CAPX_OPENARM_AUTO_CALIBRATE="false"
```

## Minimal Hardware Loop Test

### Read state only

```bash
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_minimal.py --arm left --no-motion
```

Expected output includes:

```text
connected=True
calibrated=True
joint positions: {...}
```

### Small gripper motion

Open gripper (move toward negative limit):

```bash
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_minimal.py --arm left --gripper-delta-deg -10
```

Close gripper (move toward zero):

```bash
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_minimal.py --arm left --gripper-delta-deg 10
```

> Gripper convention: `0 deg` = closed, `-65 deg` = fully open.

## Camera Setup

### Identify RealSense devices

```bash
sudo apt install -y v4l-utils
v4l2-ctl --list-devices
```

Each RealSense exposes multiple V4L nodes. For this setup:

| Camera | Physical Location | RGB V4L Device |
|--------|-------------------|----------------|
| Camera 1 | Left wrist | `/dev/video2` |
| Camera 2 | Right wrist | `/dev/video8` |

### Capture test images

```bash
# Left wrist
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_camera.py \
    --device /dev/video2 --width 1280 --height 720 \
    --output /tmp/openarm_left_wrist.jpg

# Right wrist
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/test_openarm_camera.py \
    --device /dev/video8 --width 1280 --height 720 \
    --output /tmp/openarm_right_wrist.jpg
```

### Transfer images to laptop

```bash
# Run on laptop
scp whz@<IPC_IP>:/tmp/openarm_left_wrist.jpg ./left_wrist.jpg
scp whz@<IPC_IP>:/tmp/openarm_right_wrist.jpg ./right_wrist.jpg
```

## LiteLLM / DeepSeek Setup on IPC

Install and start LiteLLM proxy:

```bash
uv pip install litellm
export DEEPSEEK_API_KEY="sk-..."
./scripts/start_litellm_deepseek.sh
```

Test the proxy:

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek/deepseek-chat", "messages": [{"role": "user", "content": "hello"}]}'
```

## GPU Service Setup on Pro 6000

On the GPU server, start vision/motion services bound to all interfaces:

```bash
cd /path/to/cap-x
uv run --no-sync --active capx/serving/launch_servers.py --profile default --host 0.0.0.0
```

Verify ports:

```bash
ss -tlnp | grep -E '8114|8115|8116'
```

On IPC, point clients to Pro 6000:

```bash
export CAPX_SAM3_SERVICE_URL="http://<PRO6000_IP>:8114"
export GRASPNET_SERVICE_URL="http://<PRO6000_IP>:8115"
export CAPX_PYROKI_SERVICE_URL="http://<PRO6000_IP>:8116"
```

## Start CaP-X Main Program + Web UI

```bash
cd ~/robot_workspace/cap-x
source .venv/bin/activate

export CAPX_OPENARM_LEFT_PORT="can0"
export CAPX_OPENARM_RIGHT_PORT="can1"
export CAPX_OPENARM_CALIBRATION_DIR="$HOME/.capx/openarm/calibration"
export CAPX_SAM3_SERVICE_URL="http://<PRO6000_IP>:8114"
export GRASPNET_SERVICE_URL="http://<PRO6000_IP>:8115"
export CAPX_PYROKI_SERVICE_URL="http://<PRO6000_IP>:8116"

uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/openarm/openarm_motion_real_litellm.yaml
```

Open in browser:

```bash
http://<IPC_IP>:8200
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'python-can'`

Install it into the active venv:

```bash
uv pip install "python-can>=4.2,<5"
```

### CAN error "Network is down"

Bring interface up with CAN-FD:

```bash
sudo ip link set can0 up type can bitrate 1000000 dbitrate 5000000 fd on
```

### CAN error "Invalid argument"

Interface was brought up as classic CAN, not CAN-FD. Re-run the CAN-FD command above.

### `calibrated=False`

Set `CAPX_OPENARM_AUTO_CALIBRATE="true"` and run the minimal test once.

### Camera capture fails

Try different `/dev/video*` nodes. RealSense RGB is usually the third node of each device (e.g., `/dev/video2`, `/dev/video8`).

## Next Steps

See the API coding guide for how to write OpenArm control scripts and use GPU-based vision/motion services.
