from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capx.integrations.openarm.assets import OpenArmMotionAssetRegistry
from capx.integrations.openarm.driver import PYTHON_CAN_AVAILABLE
from capx.integrations.openarm.perception_adapter import (
    OpenClawPerceptionConfig,
    OpenClawServiceAdapter,
)
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig
from capx.nanobot.task_client import CapxNanobotTaskClient


def _ok(name: str, detail: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "ok": True, "detail": detail, "payload": payload or {}}


def _fail(name: str, detail: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "ok": False, "detail": detail, "payload": payload or {}}


def collect_openarm_doctor_report(
    *,
    asset_root: str | None = None,
    relay_base_url: str = "http://127.0.0.1:8200",
    perception_base_url: str | None = None,
    connect_robot: bool = False,
    runtime: OpenArmRuntime | None = None,
    registry: OpenArmMotionAssetRegistry | None = None,
    perception: OpenClawServiceAdapter | None = None,
    relay_client: CapxNanobotTaskClient | None = None,
) -> dict[str, Any]:
    cfg = runtime.config if runtime is not None else OpenArmRuntimeConfig()
    if perception_base_url:
        cfg.perception.base_url = perception_base_url

    registry = registry or OpenArmMotionAssetRegistry(
        asset_root=Path(asset_root).expanduser() if asset_root else None
    )
    perception = perception or OpenClawServiceAdapter(
        OpenClawPerceptionConfig(
            base_url=cfg.perception.base_url,
            timeout_s=cfg.perception.timeout_s,
            enabled=cfg.perception.enabled,
        )
    )
    relay_client = relay_client or CapxNanobotTaskClient(base_url=relay_base_url)

    checks: list[dict[str, Any]] = []

    checks.append(
        _ok(
            "openarm_driver",
            "Using the in-repo OpenArm low-level driver stack.",
            {"driver": "capx.integrations.openarm.driver", "embedded": True},
        )
    )

    if PYTHON_CAN_AVAILABLE:
        checks.append(
            _ok(
                "python_can",
                "python-can is available for the in-repo OpenArm low-level driver.",
                {"driver": "capx.integrations.openarm.driver", "embedded": True},
            )
        )
    else:
        checks.append(
            _fail(
                "python_can",
                "python-can is missing. Install cap-x dependencies so the in-repo OpenArm driver can talk to CAN hardware.",
                {"driver": "capx.integrations.openarm.driver", "embedded": True},
            )
        )

    port_payload = {
        "left_port": cfg.left_arm.port,
        "right_port": cfg.right_arm.port,
        "left_can_interface": cfg.left_arm.can_interface,
        "right_can_interface": cfg.right_arm.can_interface,
    }
    if cfg.left_arm.port and cfg.right_arm.port:
        checks.append(_ok("arm_ports", "Both OpenArm ports are configured.", port_payload))
    else:
        checks.append(
            _fail(
                "arm_ports",
                "OpenArm left/right ports are missing. Set CAPX_OPENARM_LEFT_PORT and CAPX_OPENARM_RIGHT_PORT.",
                port_payload,
            )
        )

    asset_status = registry.get_recording_status()
    missing_anchors = asset_status.get("anchors_missing", [])
    missing_combos = asset_status.get("combo_templates_missing", [])
    if not missing_anchors and not missing_combos:
        checks.append(
            _ok(
                "motion_assets",
                "All default v1 anchors are recorded.",
                asset_status,
            )
        )
    else:
        checks.append(
            _fail(
                "motion_assets",
                (
                    "Missing default motion assets. "
                    f"anchors={len(missing_anchors)} combos={len(missing_combos)}"
                ),
                asset_status,
            )
        )

    try:
        health = perception.health()
        tactile_health = perception.tactile_health()
        checks.append(
            _ok(
                "perception",
                "Perception and tactile services responded successfully.",
                {"health": health, "tactile_health": tactile_health},
            )
        )
    except Exception as exc:
        checks.append(
            _fail(
                "perception",
                f"Perception service check failed: {exc}",
                {"base_url": cfg.perception.base_url, "enabled": cfg.perception.enabled},
            )
        )

    try:
        relay_health = relay_client.health()
        checks.append(_ok("relay", "cap-x nanobot relay responded successfully.", relay_health))
    except Exception as exc:
        checks.append(
            _fail(
                "relay",
                f"cap-x nanobot relay check failed: {exc}",
                {"base_url": relay_base_url},
            )
        )

    if connect_robot:
        runtime = runtime or OpenArmRuntime(cfg)
        try:
            runtime.connect()
            state = runtime.get_robot_state()
            checks.append(_ok("robot_connection", "Robot connected successfully.", state))
        except Exception as exc:
            checks.append(_fail("robot_connection", f"Robot connection failed: {exc}"))
        finally:
            try:
                runtime.disconnect()
            except Exception:
                pass
    else:
        checks.append(
            _ok(
                "robot_connection",
                "Skipped real robot connection check. Re-run with --connect-robot when hardware is ready.",
                {"checked": False},
            )
        )

    return {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
        "summary": {
            "ok_count": sum(1 for item in checks if item["ok"]),
            "fail_count": sum(1 for item in checks if not item["ok"]),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deployment/self-checks for the cap-x OpenArm integration.",
    )
    parser.add_argument("--asset-root", default=None, help="Override the OpenArm asset root.")
    parser.add_argument(
        "--relay-base-url",
        default="http://127.0.0.1:8200",
        help="cap-x web relay base URL.",
    )
    parser.add_argument(
        "--perception-base-url",
        default=None,
        help="Override the OpenClaw perception service base URL.",
    )
    parser.add_argument(
        "--connect-robot",
        action="store_true",
        help="Also try connecting to the real OpenArm hardware.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    report = collect_openarm_doctor_report(
        asset_root=args.asset_root,
        relay_base_url=args.relay_base_url,
        perception_base_url=args.perception_base_url,
        connect_robot=args.connect_robot,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["success"] else 1)


if __name__ == "__main__":
    main()
