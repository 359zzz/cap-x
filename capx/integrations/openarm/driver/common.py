from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeAlias, TypeVar


NameOrID: TypeAlias = str | int
Value: TypeAlias = int | float
RobotAction: TypeAlias = dict[str, Any]
RobotObservation: TypeAlias = dict[str, Any]

DEFAULT_CALIBRATION_ROOT = Path.home() / ".capx" / "openarm" / "calibration"


class DeviceAlreadyConnectedError(RuntimeError):
    """Raised when a connect operation is requested on an already connected device."""


class DeviceNotConnectedError(RuntimeError):
    """Raised when a hardware operation is requested before connecting the device."""


_F = TypeVar("_F", bound=Callable[..., Any])


def check_if_not_connected(func: _F) -> _F:
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.is_connected:
            raise DeviceNotConnectedError(
                f"{self.__class__.__name__} is not connected. Run `.connect()` first."
            )
        return func(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def check_if_already_connected(func: _F) -> _F:
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self.__class__.__name__} is already connected.")
        return func(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class MotorNormMode(str, Enum):
    RANGE_0_100 = "range_0_100"
    RANGE_M100_100 = "range_m100_100"
    DEGREES = "degrees"


@dataclass
class MotorCalibration:
    id: int
    drive_mode: int
    homing_offset: int
    range_min: int
    range_max: int


@dataclass
class Motor:
    id: int
    model: str
    norm_mode: MotorNormMode
    motor_type_str: str | None = None
    recv_id: int | None = None


class CalibrationBackedDevice:
    """Small calibration-file helper used by the in-repo OpenArm driver."""

    name = "openarm_device"

    def __init__(self, *, device_id: str | None, calibration_dir: Path | None) -> None:
        self.id = device_id or self.name
        root = Path(calibration_dir).expanduser() if calibration_dir else DEFAULT_CALIBRATION_ROOT
        self.calibration_dir = root / self.name
        self.calibration_fpath = self.calibration_dir / f"{self.id}.json"
        self.calibration: dict[str, MotorCalibration] = {}
        if self.calibration_fpath.is_file():
            self._load_calibration()

    def __str__(self) -> str:
        return f"{self.id} {self.__class__.__name__}"

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.disconnect()

    def __del__(self) -> None:
        try:
            if self.is_connected:
                self.disconnect()
        except Exception:
            pass

    def _load_calibration(self, fpath: Path | None = None) -> None:
        path = self.calibration_fpath if fpath is None else fpath
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.calibration = {
            str(name): MotorCalibration(**value)
            for name, value in payload.items()
            if isinstance(value, dict)
        }

    def _save_calibration(self, fpath: Path | None = None) -> None:
        path = self.calibration_fpath if fpath is None else fpath
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {name: asdict(value) for name, value in self.calibration.items()}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
