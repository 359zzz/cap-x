#!/usr/bin/env python3
"""Minimal OpenArm hardware loop test.

Run this on the IPC (the machine physically connected to OpenArm) to verify:
  1. Driver CAN connection works.
  2. Joint positions can be read.
  3. A tiny, safe gripper movement executes and reports back.

Usage:
    cd /path/to/cap-x
    export CAPX_OPENARM_LEFT_PORT="can0"
    export CAPX_OPENARM_RIGHT_PORT="can1"
    export CAPX_OPENARM_CALIBRATION_DIR="/path/to/calibration"
    python scripts/test_openarm_minimal.py

Safety:
    - Keep the arm in a stable posture before running.
    - Have emergency stop ready.
    - The default motion is only a small gripper delta (<= 5 degrees).
"""

from __future__ import annotations

import argparse
import sys
import time

from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal OpenArm loop test")
    parser.add_argument(
        "--arm",
        choices=["left", "right"],
        default="left",
        help="Which arm to exercise (default: left)",
    )
    parser.add_argument(
        "--gripper-delta-deg",
        type=float,
        default=5.0,
        help="Tiny gripper position delta in degrees (default: 5.0, clamped to [-10, 10])",
    )
    parser.add_argument(
        "--no-motion",
        action="store_true",
        help="Only read state, do not command any motion",
    )
    args = parser.parse_args()

    delta = max(-10.0, min(10.0, args.gripper_delta_deg))
    arm = args.arm

    print("=" * 60)
    print("OpenArm minimal loop test")
    print(f"arm={arm}, gripper_delta_deg={delta}, no_motion={args.no_motion}")
    print("=" * 60)

    config = OpenArmRuntimeConfig()
    runtime = OpenArmRuntime(config)

    try:
        print("\n[1/4] Connecting to OpenArm...")
        runtime.connect()
        print(f"  connected={runtime.driver.is_connected}")
        print(f"  calibrated={runtime.driver.is_calibrated}")

        print(f"\n[2/4] Reading current {arm} arm state...")
        joints = runtime.get_arm_joint_positions(arm)
        gripper_pos = joints.get("gripper", 0.0)
        print(f"  joint positions: {joints}")
        print(f"  current gripper position: {gripper_pos:.3f} deg")

        if args.no_motion:
            print("\n[3/4] Skipping motion (--no-motion)")
        else:
            print(f"\n[3/4] Commanding tiny gripper movement (delta={delta:.1f} deg)...")
            target_gripper = gripper_pos + delta
            # OpenArm gripper range is roughly [-65, 0] degrees.
            target_gripper = max(-65.0, min(0.0, target_gripper))
            print(f"  target gripper position: {target_gripper:.3f} deg")

            runtime.move_arm_joints_blocking(
                arm,
                {"gripper": target_gripper},
                speed="slow",
                timeout_s=5.0,
            )

            print("\n[4/4] Reading state after motion...")
            joints_after = runtime.get_arm_joint_positions(arm)
            print(f"  joint positions: {joints_after}")
            print(f"  gripper position: {joints_after.get('gripper', 0.0):.3f} deg")

        print("\nTest completed successfully.")
        return 0

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    finally:
        print("\nDisconnecting...")
        runtime.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    raise SystemExit(main())
