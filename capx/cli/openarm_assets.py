from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capx.integrations.openarm.assets import OpenArmMotionAssetRegistry
from capx.integrations.openarm.recording import ManualOpenArmRecorder
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


def _build_registry(asset_root: str | None) -> OpenArmMotionAssetRegistry:
    root = Path(asset_root).expanduser() if asset_root else None
    return OpenArmMotionAssetRegistry(asset_root=root)


def _build_recorder(asset_root: str | None) -> tuple[OpenArmRuntime, ManualOpenArmRecorder]:
    runtime = OpenArmRuntime(OpenArmRuntimeConfig())
    registry = _build_registry(asset_root)
    recorder = ManualOpenArmRecorder(runtime, registry)
    return runtime, recorder


def _print_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_status(args: argparse.Namespace) -> None:
    registry = _build_registry(args.asset_root)
    _print_payload(registry.get_recording_status())


def cmd_bootstrap(args: argparse.Namespace) -> None:
    registry = _build_registry(args.asset_root)
    paths = registry.bootstrap_combo_templates(
        magnitude=args.magnitude,
        overwrite=args.overwrite,
    )
    _print_payload(
        {
            "success": True,
            "created_count": len(paths),
            "paths": [str(path) for path in paths],
        }
    )


def cmd_record_anchor(args: argparse.Namespace) -> None:
    runtime, recorder = _build_recorder(args.asset_root)
    try:
        result = recorder.record_anchor(
            args.name,
            arm_mode=args.arm_mode,
            arm=args.arm,
            notes=args.notes,
        )
        _print_payload({"success": True, **result.details, "path": result.path})
    finally:
        runtime.disconnect()


def cmd_record_primitive(args: argparse.Namespace) -> None:
    runtime, recorder = _build_recorder(args.asset_root)
    try:
        result = recorder.record_primitive_template(
            arm=args.arm,
            primitive=args.primitive,
            magnitude=args.magnitude,
            start_anchor=args.start_anchor,
            end_region_hint=args.end_region_hint,
            notes=args.notes,
        )
        _print_payload({"success": True, **result.details, "path": result.path})
    finally:
        runtime.disconnect()


def cmd_record_combo(args: argparse.Namespace) -> None:
    runtime, recorder = _build_recorder(args.asset_root)
    try:
        result = recorder.record_combo_template(
            combo=args.combo,
            arm_mode=args.arm_mode,
            magnitude=args.magnitude,
            recovery_anchor=args.recovery_anchor,
        )
        _print_payload({"success": True, **result.details, "path": result.path})
    finally:
        runtime.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage OpenArm motion assets for the cap-x OpenArm integration.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show recorded OpenArm asset status.")
    status_parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    status_parser.set_defaults(func=cmd_status)

    bootstrap_parser = subparsers.add_parser(
        "bootstrap-combos",
        help="Create editable combo template YAMLs from the built-in combo catalog.",
    )
    bootstrap_parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    bootstrap_parser.add_argument(
        "--magnitude",
        default="medium",
        choices=["slight", "small", "medium", "large"],
        help="Top-level combo template magnitude label.",
    )
    bootstrap_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing combo template YAMLs.",
    )
    bootstrap_parser.set_defaults(func=cmd_bootstrap)

    anchor_parser = subparsers.add_parser(
        "record-anchor",
        help="Record the current robot joint state as a named anchor.",
    )
    anchor_parser.add_argument("name", help="Anchor name to save.")
    anchor_parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    anchor_parser.add_argument(
        "--arm-mode",
        default="both",
        choices=["single", "both"],
        help="Whether to record one arm or both arms into the anchor.",
    )
    anchor_parser.add_argument(
        "--arm",
        default=None,
        choices=["left", "right"],
        help="Required when --arm-mode=single.",
    )
    anchor_parser.add_argument("--notes", default="", help="Optional notes stored in the YAML asset.")
    anchor_parser.set_defaults(func=cmd_record_anchor)

    primitive_parser = subparsers.add_parser(
        "record-primitive",
        help="Record a primitive template by comparing current state to a start anchor.",
    )
    primitive_parser.add_argument("arm", choices=["left", "right"], help="Arm to record.")
    primitive_parser.add_argument("primitive", help="Primitive name from the OpenArm catalog.")
    primitive_parser.add_argument(
        "magnitude",
        choices=["slight", "small", "medium", "large"],
        help="Magnitude bucket to store.",
    )
    primitive_parser.add_argument("start_anchor", help="Recorded start anchor asset name.")
    primitive_parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    primitive_parser.add_argument(
        "--end-region-hint",
        default="",
        help="Optional semantic end region stored in the template.",
    )
    primitive_parser.add_argument("--notes", default="", help="Optional notes stored in the YAML asset.")
    primitive_parser.set_defaults(func=cmd_record_primitive)

    combo_parser = subparsers.add_parser(
        "record-combo",
        help="Create or update a combo template using the built-in combo phase definition.",
    )
    combo_parser.add_argument("combo", help="Combo name from the OpenArm catalog.")
    combo_parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    combo_parser.add_argument(
        "--arm-mode",
        default="single",
        choices=["single", "both"],
        help="Single-arm or dual-arm combo template.",
    )
    combo_parser.add_argument(
        "--magnitude",
        default="medium",
        choices=["slight", "small", "medium", "large"],
        help="Top-level combo template magnitude label.",
    )
    combo_parser.add_argument(
        "--recovery-anchor",
        default="safe_standby",
        help="Fallback anchor to store in the combo template.",
    )
    combo_parser.set_defaults(func=cmd_record_combo)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
