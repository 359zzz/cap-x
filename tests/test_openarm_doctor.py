from __future__ import annotations

from types import SimpleNamespace

import capx.cli.openarm_doctor as openarm_doctor
from capx.cli.openarm_doctor import collect_openarm_doctor_report
from capx.integrations.openarm.runtime import OpenArmRuntimeConfig


class FakeRegistry:
    def __init__(self, missing: list[str] | None = None) -> None:
        self.missing = missing or []

    def get_recording_status(self) -> dict[str, object]:
        return {
            "asset_root": "test-assets",
            "anchors_missing": list(self.missing),
            "combo_templates_missing": [],
        }


class FakePerception:
    def health(self) -> dict[str, object]:
        return {"status": "ok"}

    def tactile_health(self) -> dict[str, object]:
        return {"status": "ok", "sensor_count": 1}


class BrokenPerception:
    def health(self) -> dict[str, object]:
        raise RuntimeError("offline")

    def tactile_health(self) -> dict[str, object]:
        raise RuntimeError("offline")


class FakeRelayClient:
    def health(self) -> dict[str, object]:
        return {"status": "ok", "active_task": None}


def _runtime_stub() -> object:
    cfg = OpenArmRuntimeConfig()
    cfg.left_arm.port = "left-port"
    cfg.right_arm.port = "right-port"
    return SimpleNamespace(config=cfg)


def test_openarm_doctor_report_success_path(monkeypatch) -> None:
    monkeypatch.setattr(openarm_doctor, "PYTHON_CAN_AVAILABLE", True)
    report = collect_openarm_doctor_report(
        runtime=_runtime_stub(),
        registry=FakeRegistry(),
        perception=FakePerception(),
        relay_client=FakeRelayClient(),
    )

    assert report["success"] is True
    assert report["summary"]["fail_count"] == 0


def test_openarm_doctor_report_surfaces_perception_failure(monkeypatch) -> None:
    monkeypatch.setattr(openarm_doctor, "PYTHON_CAN_AVAILABLE", True)
    report = collect_openarm_doctor_report(
        runtime=_runtime_stub(),
        registry=FakeRegistry(missing=["observe_front"]),
        perception=BrokenPerception(),
        relay_client=FakeRelayClient(),
    )

    failed = {item["name"] for item in report["checks"] if not item["ok"]}
    assert report["success"] is False
    assert "motion_assets" in failed
    assert "perception" in failed
