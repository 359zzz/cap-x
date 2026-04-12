from __future__ import annotations

from enum import IntEnum


class MotorType(IntEnum):
    DM3507 = 0
    DM4310 = 1
    DM4310_48V = 2
    DM4340 = 3
    DM4340_48V = 4
    DM6006 = 5
    DM8006 = 6
    DM8009 = 7
    DM10010L = 8
    DM10010 = 9
    DMH3510 = 10
    DMH6215 = 11
    DMG6220 = 12


MOTOR_LIMIT_PARAMS = {
    MotorType.DM3507: (12.5, 30, 10),
    MotorType.DM4310: (12.5, 30, 10),
    MotorType.DM4310_48V: (12.5, 50, 10),
    MotorType.DM4340: (12.5, 8, 28),
    MotorType.DM4340_48V: (12.5, 10, 28),
    MotorType.DM6006: (12.5, 45, 20),
    MotorType.DM8006: (12.5, 45, 40),
    MotorType.DM8009: (12.5, 45, 54),
    MotorType.DM10010L: (12.5, 25, 200),
    MotorType.DM10010: (12.5, 20, 200),
    MotorType.DMH3510: (12.5, 280, 1),
    MotorType.DMH6215: (12.5, 45, 10),
    MotorType.DMG6220: (12.5, 45, 10),
}

AVAILABLE_BAUDRATES = [
    125_000,
    200_000,
    250_000,
    500_000,
    1_000_000,
    2_000_000,
    2_500_000,
    3_200_000,
    4_000_000,
    5_000_000,
]
DEFAULT_BAUDRATE = 1_000_000
DEFAULT_TIMEOUT_MS = 1_000

MIT_KP_RANGE = (0.0, 500.0)
MIT_KD_RANGE = (0.0, 5.0)

CAN_CMD_ENABLE = 0xFC
CAN_CMD_DISABLE = 0xFD
CAN_CMD_SET_ZERO = 0xFE
CAN_CMD_REFRESH = 0xCC
CAN_PARAM_ID = 0x7FF


def motor_type_from_string(value: str) -> MotorType:
    key = value.upper().replace("-", "_")
    try:
        return MotorType[key]
    except KeyError as exc:
        valid = ", ".join(item.name.lower() for item in MotorType)
        raise ValueError(f"Unsupported Damiao motor type '{value}'. Valid values: {valid}") from exc
