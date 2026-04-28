from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from capx.integrations.openarm.assets import OpenArmMotionAssetRegistry
from capx.integrations.openarm.recording import ManualOpenArmRecorder
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


@dataclass(frozen=True)
class TomatoStage:
    key: str
    anchor_name: str
    prompt: str
    notes: str


def _default_anchor_names(task_arm: str) -> dict[str, str]:
    prefix = f"{task_arm}_tomato"
    return {
        "locate": f"{prefix}_locate_ready",
        "grasp": f"{prefix}_grasp_hold",
        "detach": f"{prefix}_detach_lift",
    }


def _render_can_setup_commands(left_port: str, right_port: str) -> str:
    ports = (left_port, right_port)
    lines: list[str] = []
    for port in ports:
        lines.extend(
            [
                f"sudo ip link set {port} down",
                f"sudo ip link set {port} type can bitrate 1000000 dbitrate 5000000 fd on",
                f"sudo ip link set {port} up",
            ]
        )
    return "\n".join(lines)


def _set_runtime_env(left_port: str, right_port: str) -> None:
    os.environ["CAPX_OPENARM_LEFT_PORT"] = left_port
    os.environ["CAPX_OPENARM_RIGHT_PORT"] = right_port
    os.environ["CAPX_OPENARM_LEFT_CAN_INTERFACE"] = "socketcan"
    os.environ["CAPX_OPENARM_RIGHT_CAN_INTERFACE"] = "socketcan"


def _build_stages(args: argparse.Namespace) -> list[TomatoStage]:
    return [
        TomatoStage(
            key="locate",
            anchor_name=args.locate_name,
            prompt="把机械臂移动到“已对准番茄、准备夹取”的姿态后按回车。",
            notes="tomato stage 1: tomato localized and aligned for grasp",
        ),
        TomatoStage(
            key="grasp",
            anchor_name=args.grasp_name,
            prompt="把机械臂移动到“夹爪已夹住番茄”的姿态后按回车。",
            notes="tomato stage 2: tomato grasped and held",
        ),
        TomatoStage(
            key="detach",
            anchor_name=args.detach_name,
            prompt="把机械臂移动到“番茄已摘下并轻微抬起”的姿态后按回车。",
            notes="tomato stage 3: tomato detached and lifted clear",
        ),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactively record three single-arm tomato task anchors for OpenArm.",
    )
    parser.add_argument(
        "--task-arm",
        default="left",
        choices=["left", "right"],
        help="Which arm performs the tomato task.",
    )
    parser.add_argument(
        "--left-port",
        default="can1",
        help="OpenArm left CAN channel, for example can1.",
    )
    parser.add_argument(
        "--right-port",
        default="can0",
        help="OpenArm right CAN channel, for example can0.",
    )
    parser.add_argument(
        "--asset-root",
        default=None,
        help="Optional custom OpenArm asset root.",
    )
    parser.add_argument(
        "--locate-name",
        default=None,
        help="Anchor name for the locate-ready stage.",
    )
    parser.add_argument(
        "--grasp-name",
        default=None,
        help="Anchor name for the grasp-hold stage.",
    )
    parser.add_argument(
        "--detach-name",
        default=None,
        help="Anchor name for the detach-lift stage.",
    )
    parser.add_argument(
        "--print-can-setup",
        action="store_true",
        help="Print the Linux socketCAN reset commands before connecting.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the initial safety confirmation prompt.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    default_names = _default_anchor_names(args.task_arm)
    args.locate_name = args.locate_name or default_names["locate"]
    args.grasp_name = args.grasp_name or default_names["grasp"]
    args.detach_name = args.detach_name or default_names["detach"]

    if args.print_can_setup:
        print("请先在 Linux 机器上重新 set CAN 口：")
        print(_render_can_setup_commands(args.left_port, args.right_port))
        print()

    _set_runtime_env(args.left_port, args.right_port)

    summary = {
        "task_arm": args.task_arm,
        "left_port": args.left_port,
        "right_port": args.right_port,
        "anchors": {
            "locate": args.locate_name,
            "grasp": args.grasp_name,
            "detach": args.detach_name,
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not args.yes:
        input("确认 CAN 已经 set 好、机械臂在安全位置后，按回车开始录制。")

    runtime = OpenArmRuntime(OpenArmRuntimeConfig())
    registry = OpenArmMotionAssetRegistry(
        asset_root=Path(args.asset_root).expanduser() if args.asset_root else None
    )
    recorder = ManualOpenArmRecorder(runtime, registry)
    stages = _build_stages(args)
    results: list[dict[str, str]] = []

    try:
        runtime.connect()
        for index, stage in enumerate(stages, start=1):
            input(f"[{index}/3] {stage.prompt}")
            result = recorder.record_anchor(
                stage.anchor_name,
                arm_mode="single",
                arm=args.task_arm,
                notes=stage.notes,
            )
            payload = {"stage": stage.key, "success": True, "path": result.path, "anchor": stage.anchor_name}
            results.append(payload)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
    finally:
        runtime.disconnect()

    print()
    print("录制完成，可直接使用这些 anchor 名称：")
    for item in results:
        print(f"- {item['anchor']}")
    print()
    print("可用检查命令：")
    print("python -m capx.cli.openarm_assets status")


if __name__ == "__main__":
    main()
