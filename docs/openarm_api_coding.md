# OpenArm API & Coding Guide

This guide explains how CaP-X exposes APIs to the LLM/code executor, how to control OpenArm through existing APIs, and how to write your own control scripts that use GPU-based vision/motion services on Pro 6000.

---

## 1. How CaP-X APIs Work

CaP-X uses an `ApiBase` pattern (`capx/integrations/base_api.py`). Each integration exposes a set of Python functions that are injected into the code execution environment.

Key files:

- `capx/integrations/base_api.py` — base class `ApiBase`
- `capx/integrations/openarm/control.py` — `OpenArmControlApi`
- `capx/integrations/openarm/runtime.py` — low-level `OpenArmRuntime`
- `capx/integrations/__init__.py` — API registration
- `env_configs/openarm/openarm_motion_real_litellm.yaml` — selects which APIs to load

### API Registration

In `capx/integrations/__init__.py`:

```python
register_api("OpenArmControlApi", OpenArmControlApi)
```

In the YAML config:

```yaml
env:
  cfg:
    apis:
      - OpenArmControlApi
```

The code executor (`OpenArmMotionCodeEnv`) imports every function from every registered API into the global namespace. So the LLM can write:

```python
move_to_named_pose("home")
```

instead of:

```python
APIS["OpenArmControlApi"].move_to_named_pose("home")
```

---

## 2. Existing OpenArm APIs

### `OpenArmControlApi`

Located in `capx/integrations/openarm/control.py`.

Main functions exposed to the LLM:

| Function | Purpose |
|----------|---------|
| `get_robot_state()` | connectivity, calibration, task state |
| `get_observation()` | latest joint states and camera frames |
| `describe_scene(prompt)` | VLM-based scene description via perception gateway |
| `detect_target(target_name)` | detect an object by name via perception gateway |
| `get_target_pose(target_name)` | get camera-frame target pose estimate |
| `move_to_named_pose(name, ...)` | move to a recorded anchor pose |
| `execute_motion_primitive(arm, primitive, magnitude, speed)` | run a cataloged primitive |
| `execute_motion_combo(name, arm, magnitude, speed)` | run a sequence of primitives |
| `open_gripper(arm, width)` | open gripper |
| `close_gripper(arm, force)` | close gripper |
| `go_home()` / `go_safe_standby()` | convenience wrappers |

### `OpenArmRecordingApi`

Used to record anchors, primitive templates, and combo templates. Useful for teaching motion sequences by demonstration.

---

## 3. Low-Level SDK: `OpenArmRuntime`

For direct joint-level control, use `OpenArmRuntime` directly. It is what `OpenArmControlApi` calls under the hood.

Example:

```python
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig
import os

os.environ.setdefault("CAPX_OPENARM_LEFT_PORT", "can0")
os.environ.setdefault("CAPX_OPENARM_RIGHT_PORT", "can1")
os.environ.setdefault("CAPX_OPENARM_CALIBRATION_DIR", os.path.expanduser("~/.capx/openarm/calibration"))

rt = OpenArmRuntime(OpenArmRuntimeConfig())
rt.connect()

# Read state
obs = rt.get_observation()
print(obs["left_arm"]["joint_pos"])

# Move left arm joint_1 by +10 degrees
before = rt.get_arm_joint_positions("left")
rt.move_arm_joints_blocking("left", {"joint_1": before["joint_1"] + 10.0}, speed="slow")

# Set gripper to 50% open
rt.set_gripper_fraction("left", 0.5)

rt.disconnect()
```

Key methods:

- `connect()` / `disconnect()`
- `get_observation()`
- `get_arm_joint_positions(arm)`
- `move_arm_joints_blocking(arm, joints, speed, timeout_s)`
- `move_both_arms_blocking(left_joints, right_joints, speed, timeout_s)`
- `set_gripper_fraction(arm, fraction)`
- `hold_current_position()`
- `detect_target(target_name)` / `describe_scene(prompt)` (via perception gateway)

---

## 4. Using GPU Services (Pro 6000)

The existing `OpenArmControlApi` does **not** automatically call SAM3 / Contact-Graspnet / Pyroki. To use them, write a custom control API or inline script.

### 4.1 Import GPU service clients

```python
from capx.integrations.vision.sam3 import init_sam3
from capx.integrations.vision.graspnet import init_contact_graspnet
from capx.integrations.motion.pyroki import init_pyroki

# These read remote URLs from environment variables automatically:
# CAPX_SAM3_SERVICE_URL, GRASPNET_SERVICE_URL, CAPX_PYROKI_SERVICE_URL

sam3_seg_fn = init_sam3()
graspnet_plan_fn = init_contact_graspnet()
ik_solve_fn = init_pyroki()
```

### 4.2 Example: detect object with SAM3 and plan grasp

```python
import numpy as np
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig
from capx.integrations.vision.sam3 import init_sam3
from capx.integrations.vision.graspnet import init_contact_graspnet

rt = OpenArmRuntime(OpenArmRuntimeConfig())
rt.connect()

obs = rt.get_observation()
rgb = obs["cameras"]["left_wrist"]  # depends on how cameras are named
depth = ...  # obtain depth from RealSense SDK
intrinsics = ...

# Segment object
sam3 = init_sam3()
results = sam3(rgb, text_prompt="red cube")
best = max(results, key=lambda r: r["score"])
mask = best["mask"]

# Plan grasp
graspnet = init_contact_graspnet()
grasps = graspnet_plan_fn(depth, intrinsics, mask, instance_id=1)

rt.disconnect()
```

> Note: RealSense depth alignment and camera intrinsics must be handled separately. This snippet shows the integration points.

---

## 5. Writing a Custom Control API

Create `capx/integrations/openarm/control_visual.py`:

```python
from __future__ import annotations
from typing import Any
from capx.integrations.base_api import ApiBase
from capx.integrations.vision.sam3 import init_sam3
from capx.integrations.openarm.runtime import OpenArmRuntime

class OpenArmVisualControlApi(ApiBase):
    def __init__(self, env) -> None:
        super().__init__(env)
        self.runtime: OpenArmRuntime = env.runtime
        self.sam3 = init_sam3()

    def functions(self) -> dict[str, Any]:
        return {
            "segment_object": self.segment_object,
        }

    def segment_object(self, object_name: str) -> dict[str, Any]:
        """Segment object by name using SAM3 on Pro 6000."""
        obs = self._env.get_observation()
        rgb = ...  # extract RGB from obs
        results = self.sam3(rgb, text_prompt=object_name)
        return {"object": object_name, "detections": len(results)}
```

Register it in `capx/integrations/__init__.py`:

```python
from .openarm.control_visual import OpenArmVisualControlApi
register_api("OpenArmVisualControlApi", OpenArmVisualControlApi)
```

Then add it to the YAML config:

```yaml
env:
  cfg:
    apis:
      - OpenArmControlApi
      - OpenArmVisualControlApi
```

---

## 6. Running a Task via Web UI

1. Start LiteLLM proxy on IPC.
2. Start GPU services on Pro 6000.
3. Set all environment variables on IPC.
4. Launch CaP-X:

```bash
uv run --no-sync --active capx/envs/launch.py \
    --config-path env_configs/openarm/openarm_motion_real_litellm.yaml
```

5. Open `http://<IPC_IP>:8200` on the laptop.
6. Enter a task prompt, e.g.:

```text
Move the left arm to home pose, then open the left gripper fully.
```

The LLM will generate Python code using the exposed APIs and execute it on the robot.

---

## 7. Example Task: Go Home and Open Gripper

The LLM might generate:

```python
go_home()
open_gripper("left", width="full")
RESULT = {"status": "done"}
```

If you want it to use visual confirmation first:

```python
desc = describe_scene("Is there a red cube on the table?")
print(desc)
move_to_named_pose("safe_standby")
```

---

## 8. Forward Kinematics & Camera Extrinsics (ROS2-free)

CaP-X now includes ROS2-free FK and wrist-camera handling for OpenArm v2.0.

### 8.1 Install dependencies

```bash
pip install pinocchio pyrealsense2
```

`pinocchio` is required for FK. `pyrealsense2` is required if you want aligned depth; RGB-only V4L capture works with `opencv-python-headless` alone.

### 8.2 Download the OpenArm URDF

```bash
./scripts/setup_openarm_urdf.sh
export CAPX_OPENARM_URDF="$HOME/robot_workspace/cap-x/third_party/openarm_description/output.urdf"
```

### 8.3 Run FK from joint positions

```python
from capx.integrations.openarm.kinematics import OpenArmKinematics, OpenArmKinematicsConfig

kin = OpenArmKinematics(OpenArmKinematicsConfig(side="left"))
assert kin.is_available, "Install pinocchio or check CAPX_OPENARM_URDF"

fk = kin.solve_fk({
    "joint_1": 0.0, "joint_2": 0.0, "joint_3": 0.0,
    "joint_4": 0.0, "joint_5": 0.0, "joint_6": 0.0, "joint_7": 0.0,
})
print(fk.ee_position)
print(fk.ee_quaternion_xyzw)  # [x, y, z, w]
```

The FK model uses:
  * base frame: `openarm_body_link0`
  * arm base: `openarm_left_base_link` / `openarm_right_base_link`
  * ee flange: `openarm_left_ee_base_link` / `openarm_right_ee_base_link`

### 8.4 Calibrate wrist camera extrinsics (eye-in-hand)

Print a chessboard (e.g. 9x6 internal corners, 20 mm squares), attach it rigidly in front of the robot, and run:

```bash
export CAPX_OPENARM_URDF="$HOME/robot_workspace/cap-x/third_party/openarm_description/output.urdf"
PYTHONPATH=~/robot_workspace/cap-x python3 scripts/calibrate_openarm_handeye.py \
    --arm left --camera <realsense_serial> --square-size 0.02
```

The script will:
1. Connect to OpenArm and start the left wrist RealSense.
2. Ask you to jog the arm to diverse poses and press ENTER to capture.
3. Run Tsai-Lenz hand-eye calibration and save `env_configs/openarm/camera_extrinsics/left_wrist.yaml`.

Repeat for the right arm if needed.

### 8.5 Camera environment variables

```bash
export CAPX_OPENARM_LEFT_CAMERA_DEVICE=/dev/video2
export CAPX_OPENARM_RIGHT_CAMERA_DEVICE=/dev/video8
export CAPX_OPENARM_CAMERA_EXTRINSICS_DIR=env_configs/openarm/camera_extrinsics
```

When the runtime starts, it will open the configured cameras and fill the observation with:

```python
obs["cameras"]["left"]["rgb"]           # (H, W, 3) uint8
obs["cameras"]["left"]["depth"]         # (H, W) float32 meters (RealSense only)
obs["cameras"]["left"]["intrinsics"]    # (3, 3) camera matrix
obs["cameras"]["left"]["T_base_cam"]    # (4, 4) camera pose in base frame
obs["left_ee_pose"]["T_base_ee"]        # (4, 4) left ee pose in base frame
obs["robot0_robotview"]                 # Robosuite-style camera entry for vision APIs
```

### 8.6 Example: Franka-style visual servoing

```python
import numpy as np
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig
from capx.integrations.vision.sam3 import init_sam3
from capx.integrations.vision.graspnet import init_contact_graspnet
from capx.integrations.motion.pyroki import init_pyroki

runtime = OpenArmRuntime(OpenArmRuntimeConfig())
runtime.connect()

obs = runtime.get_observation_with_cameras()
rgb = obs["robot0_robotview"]["images"]["rgb"]
depth = obs["robot0_robotview"]["images"]["depth"][:, :, 0]
intrinsics = obs["robot0_robotview"]["intrinsics"]

# Segment object with SAM3 on Pro 6000
sam3 = init_sam3()
results = sam3(rgb, text_prompt="red cube")
best = max(results, key=lambda r: r["score"])
mask = best["mask"]

# Plan grasp with Contact-Graspnet on Pro 6000
graspnet = init_contact_graspnet()
grasps = graspnet(depth, intrinsics, mask, instance_id=1)
best_grasp = grasps[0]  # {pose: (4,4), width: float, score: float}

# Solve IK with Pyroki on Pro 6000
ik = init_pyroki()
# ... convert grasp pose to target joint angles via ik_solve_fn ...

runtime.disconnect()
```

See `capx/integrations/franka/control.py` for the full grasp/IK/execute pattern.

---

## 9. Next Recommendation

With FK and camera extrinsics in place, the next step is to create `OpenArmVisualControlApi` that:

1. Reads RGB-D from `robot0_robotview` in the observation.
2. Calls SAM3 / Contact-Graspnet / Pyroki on Pro 6000.
3. Uses `OpenArmRuntime.move_arm_joints_safe(...)` or `move_to_named_pose(...)` to execute.
4. Optionally visualizes the scene with Viser using the FK model and camera poses.
