from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, TypedDict

import numpy as np

from .common import (
    Motor,
    MotorCalibration,
    NameOrID,
    Value,
    check_if_already_connected,
    check_if_not_connected,
)
from .damiao_tables import (
    AVAILABLE_BAUDRATES,
    CAN_CMD_DISABLE,
    CAN_CMD_ENABLE,
    CAN_CMD_REFRESH,
    CAN_CMD_SET_ZERO,
    CAN_PARAM_ID,
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT_MS,
    MIT_KD_RANGE,
    MIT_KP_RANGE,
    MOTOR_LIMIT_PARAMS,
    MotorType,
    motor_type_from_string,
)

try:
    import can
except Exception:  # pragma: no cover
    can = None  # type: ignore[assignment]


PYTHON_CAN_AVAILABLE = can is not None

logger = logging.getLogger(__name__)

LONG_TIMEOUT_SEC = 0.1
MEDIUM_TIMEOUT_SEC = 0.01
SHORT_TIMEOUT_SEC = 0.001
PRECISE_TIMEOUT_SEC = 0.0001


class MotorState(TypedDict):
    position: float
    velocity: float
    torque: float
    temp_mos: float
    temp_rotor: float


class DamiaoMotorsBus:
    """Minimal in-repo Damiao CAN bus used by OpenArm real-hardware control."""

    available_baudrates = deepcopy(AVAILABLE_BAUDRATES)
    default_baudrate = DEFAULT_BAUDRATE
    default_timeout = DEFAULT_TIMEOUT_MS

    def __init__(
        self,
        port: str,
        motors: dict[str, Motor],
        calibration: dict[str, MotorCalibration] | None = None,
        can_interface: str = "auto",
        use_can_fd: bool = True,
        bitrate: int = 1_000_000,
        data_bitrate: int | None = 5_000_000,
    ) -> None:
        self.port = port
        self.motors = motors
        self.calibration = calibration if calibration else {}
        self.can_interface = can_interface
        self.use_can_fd = use_can_fd
        self.bitrate = bitrate
        self.data_bitrate = data_bitrate
        self.canbus: Any | None = None
        self._is_connected = False
        self._recv_id_to_motor: dict[int, str] = {}
        self._motor_types: dict[str, MotorType] = {}

        for name, motor in self.motors.items():
            if motor.motor_type_str is None:
                raise ValueError(f"Motor '{name}' is missing a Damiao motor type.")
            self._motor_types[name] = motor_type_from_string(motor.motor_type_str)
            if motor.recv_id is not None:
                self._recv_id_to_motor[motor.recv_id] = name

        self._last_known_states: dict[str, MotorState] = {
            name: {
                "position": 0.0,
                "velocity": 0.0,
                "torque": 0.0,
                "temp_mos": 0.0,
                "temp_rotor": 0.0,
            }
            for name in self.motors
        }
        self._gains: dict[str, dict[str, float]] = {
            name: {"kp": 10.0, "kd": 0.5} for name in self.motors
        }

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self.canbus is not None

    @property
    def is_calibrated(self) -> bool:
        return bool(self.calibration)

    @check_if_already_connected
    def connect(self, handshake: bool = True) -> None:
        if can is None:
            raise RuntimeError(
                "python-can is required for OpenArm real-hardware control. "
                "Install cap-x dependencies again or run `pip install python-can>=4.2,<5`."
            )
        if not self.port:
            raise ConnectionError("OpenArm CAN channel is empty. Set CAPX_OPENARM_LEFT_PORT/RIGHT_PORT.")

        try:
            if self.can_interface == "auto":
                self.can_interface = "slcan" if self.port.startswith("/dev/") else "socketcan"

            kwargs: dict[str, Any] = {
                "channel": self.port,
                "bitrate": self.bitrate,
                "interface": self.can_interface,
            }
            if self.can_interface == "socketcan" and self.use_can_fd and self.data_bitrate is not None:
                kwargs.update({"data_bitrate": self.data_bitrate, "fd": True})

            self.canbus = can.interface.Bus(**kwargs)
            self._is_connected = True
            if handshake:
                self._handshake()
            logger.info("OpenArm Damiao bus connected on %s via %s.", self.port, self.can_interface)
        except Exception as exc:
            self._is_connected = False
            self.canbus = None
            raise ConnectionError(f"Failed to connect to OpenArm CAN bus '{self.port}': {exc}") from exc

    def _handshake(self) -> None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")

        while self.canbus.recv(timeout=0.01):
            pass

        missing_motors: list[str] = []
        for motor_name in self.motors:
            motor_id = self._get_motor_id(motor_name)
            recv_id = self._get_motor_recv_id(motor_name)
            msg = can.Message(  # type: ignore[union-attr]
                arbitration_id=motor_id,
                data=[0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, CAN_CMD_ENABLE],
                is_extended_id=False,
                is_fd=self.use_can_fd,
            )
            self.canbus.send(msg)

            response = None
            start_time = time.time()
            while time.time() - start_time < LONG_TIMEOUT_SEC:
                candidate = self.canbus.recv(timeout=LONG_TIMEOUT_SEC)
                if candidate and candidate.arbitration_id == recv_id:
                    response = candidate
                    break

            if response is None:
                missing_motors.append(motor_name)
            else:
                self._process_response(motor_name, response)
            time.sleep(MEDIUM_TIMEOUT_SEC)

        if missing_motors:
            raise ConnectionError(
                "OpenArm Damiao handshake failed. Missing motors: "
                f"{missing_motors}. Check 24V power, CAN wiring, and motor IDs."
            )

    @check_if_not_connected
    def disconnect(self, disable_torque: bool = True) -> None:
        if disable_torque:
            try:
                self.disable_torque()
            except Exception as exc:
                logger.warning("Failed to disable OpenArm torque during disconnect: %s", exc)

        if self.canbus is not None:
            self.canbus.shutdown()
            self.canbus = None
        self._is_connected = False

    def configure_motors(self) -> None:
        for motor in self.motors:
            self._send_simple_command(motor, CAN_CMD_ENABLE)
            time.sleep(MEDIUM_TIMEOUT_SEC)

    def enable_torque(self, motors: str | list[str] | None = None, num_retry: int = 0) -> None:
        for motor in self._get_motors_list(motors):
            for attempt in range(num_retry + 1):
                try:
                    self._send_simple_command(motor, CAN_CMD_ENABLE)
                    break
                except Exception:
                    if attempt == num_retry:
                        raise
                    time.sleep(MEDIUM_TIMEOUT_SEC)

    def disable_torque(self, motors: str | list[str] | None = None, num_retry: int = 0) -> None:
        for motor in self._get_motors_list(motors):
            for attempt in range(num_retry + 1):
                try:
                    self._send_simple_command(motor, CAN_CMD_DISABLE)
                    break
                except Exception:
                    if attempt == num_retry:
                        raise
                    time.sleep(MEDIUM_TIMEOUT_SEC)

    @contextmanager
    def torque_disabled(self, motors: str | list[str] | None = None):
        self.disable_torque(motors)
        try:
            yield
        finally:
            self.enable_torque(motors)

    def set_zero_position(self, motors: str | list[str] | None = None) -> None:
        for motor in self._get_motors_list(motors):
            self._send_simple_command(motor, CAN_CMD_SET_ZERO)
            time.sleep(MEDIUM_TIMEOUT_SEC)

    def _send_simple_command(self, motor: NameOrID, command_byte: int) -> None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")
        motor_id = self._get_motor_id(motor)
        motor_name = self._get_motor_name(motor)
        recv_id = self._get_motor_recv_id(motor)
        msg = can.Message(  # type: ignore[union-attr]
            arbitration_id=motor_id,
            data=[0xFF] * 7 + [command_byte],
            is_extended_id=False,
            is_fd=self.use_can_fd,
        )
        self.canbus.send(msg)
        if response := self._recv_motor_response(expected_recv_id=recv_id):
            self._process_response(motor_name, response)

    def _refresh_motor(self, motor: NameOrID) -> Any | None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")
        motor_id = self._get_motor_id(motor)
        recv_id = self._get_motor_recv_id(motor)
        msg = can.Message(  # type: ignore[union-attr]
            arbitration_id=CAN_PARAM_ID,
            data=[motor_id & 0xFF, (motor_id >> 8) & 0xFF, CAN_CMD_REFRESH, 0, 0, 0, 0, 0],
            is_extended_id=False,
            is_fd=self.use_can_fd,
        )
        self.canbus.send(msg)
        return self._recv_motor_response(expected_recv_id=recv_id)

    def _recv_motor_response(
        self,
        expected_recv_id: int | None = None,
        timeout: float = SHORT_TIMEOUT_SEC,
    ) -> Any | None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")

        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = self.canbus.recv(timeout=PRECISE_TIMEOUT_SEC)
            if msg and (expected_recv_id is None or msg.arbitration_id == expected_recv_id):
                return msg
        return None

    def _recv_all_responses(
        self,
        expected_recv_ids: list[int],
        timeout: float = 0.002,
    ) -> dict[int, Any]:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")

        responses: dict[int, Any] = {}
        expected = set(expected_recv_ids)
        start_time = time.time()
        while len(responses) < len(expected_recv_ids) and time.time() - start_time < timeout:
            msg = self.canbus.recv(timeout=PRECISE_TIMEOUT_SEC)
            if msg and msg.arbitration_id in expected:
                responses[msg.arbitration_id] = msg
        return responses

    def _encode_mit_packet(
        self,
        motor_type: MotorType,
        kp: float,
        kd: float,
        position_degrees: float,
        velocity_deg_per_sec: float,
        torque: float,
    ) -> list[int]:
        position_rad = np.radians(position_degrees)
        velocity_rad_per_sec = np.radians(velocity_deg_per_sec)
        pmax, vmax, tmax = MOTOR_LIMIT_PARAMS[motor_type]

        kp_uint = self._float_to_uint(kp, *MIT_KP_RANGE, 12)
        kd_uint = self._float_to_uint(kd, *MIT_KD_RANGE, 12)
        q_uint = self._float_to_uint(position_rad, -pmax, pmax, 16)
        dq_uint = self._float_to_uint(velocity_rad_per_sec, -vmax, vmax, 12)
        tau_uint = self._float_to_uint(torque, -tmax, tmax, 12)

        return [
            (q_uint >> 8) & 0xFF,
            q_uint & 0xFF,
            dq_uint >> 4,
            ((dq_uint & 0xF) << 4) | ((kp_uint >> 8) & 0xF),
            kp_uint & 0xFF,
            kd_uint >> 4,
            ((kd_uint & 0xF) << 4) | ((tau_uint >> 8) & 0xF),
            tau_uint & 0xFF,
        ]

    def _mit_control(
        self,
        motor: NameOrID,
        kp: float,
        kd: float,
        position_degrees: float,
        velocity_deg_per_sec: float,
        torque: float,
    ) -> None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")
        motor_id = self._get_motor_id(motor)
        motor_name = self._get_motor_name(motor)
        data = self._encode_mit_packet(
            self._motor_types[motor_name],
            kp,
            kd,
            position_degrees,
            velocity_deg_per_sec,
            torque,
        )
        msg = can.Message(  # type: ignore[union-attr]
            arbitration_id=motor_id,
            data=data,
            is_extended_id=False,
            is_fd=self.use_can_fd,
        )
        self.canbus.send(msg)
        if response := self._recv_motor_response(expected_recv_id=self._get_motor_recv_id(motor)):
            self._process_response(motor_name, response)

    def _mit_control_batch(
        self,
        commands: dict[NameOrID, tuple[float, float, float, float, float]],
    ) -> None:
        if not commands:
            return
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")

        recv_id_to_motor: dict[int, str] = {}
        for motor, (kp, kd, position_degrees, velocity_deg_per_sec, torque) in commands.items():
            motor_id = self._get_motor_id(motor)
            motor_name = self._get_motor_name(motor)
            data = self._encode_mit_packet(
                self._motor_types[motor_name],
                kp,
                kd,
                position_degrees,
                velocity_deg_per_sec,
                torque,
            )
            msg = can.Message(  # type: ignore[union-attr]
                arbitration_id=motor_id,
                data=data,
                is_extended_id=False,
                is_fd=self.use_can_fd,
            )
            self.canbus.send(msg)
            recv_id_to_motor[self._get_motor_recv_id(motor)] = motor_name

        responses = self._recv_all_responses(list(recv_id_to_motor), timeout=SHORT_TIMEOUT_SEC)
        for recv_id, motor_name in recv_id_to_motor.items():
            if response := responses.get(recv_id):
                self._process_response(motor_name, response)

    def _float_to_uint(self, x: float, x_min: float, x_max: float, bits: int) -> int:
        x = max(x_min, min(x_max, x))
        return int(((x - x_min) / (x_max - x_min)) * ((1 << bits) - 1))

    def _uint_to_float(self, x: int, x_min: float, x_max: float, bits: int) -> float:
        return float(x) / ((1 << bits) - 1) * (x_max - x_min) + x_min

    def _decode_motor_state(
        self,
        data: bytearray | bytes,
        motor_type: MotorType,
    ) -> tuple[float, float, float, int, int]:
        if len(data) < 8:
            raise ValueError("Invalid Damiao motor state frame.")

        q_uint = (data[1] << 8) | data[2]
        dq_uint = (data[3] << 4) | (data[4] >> 4)
        tau_uint = ((data[4] & 0x0F) << 8) | data[5]
        temp_mos = data[6]
        temp_rotor = data[7]

        pmax, vmax, tmax = MOTOR_LIMIT_PARAMS[motor_type]
        position_rad = self._uint_to_float(q_uint, -pmax, pmax, 16)
        velocity_rad_per_sec = self._uint_to_float(dq_uint, -vmax, vmax, 12)
        torque = self._uint_to_float(tau_uint, -tmax, tmax, 12)
        return np.degrees(position_rad), np.degrees(velocity_rad_per_sec), torque, temp_mos, temp_rotor

    def _process_response(self, motor: str, msg: Any) -> None:
        try:
            pos, vel, torque, temp_mos, temp_rotor = self._decode_motor_state(
                msg.data,
                self._motor_types[motor],
            )
            self._last_known_states[motor] = {
                "position": pos,
                "velocity": vel,
                "torque": torque,
                "temp_mos": float(temp_mos),
                "temp_rotor": float(temp_rotor),
            }
        except Exception as exc:
            logger.warning("Failed to decode Damiao response from %s: %s", motor, exc)

    @check_if_not_connected
    def read(self, data_name: str, motor: str) -> Value:
        msg = self._refresh_motor(motor)
        if msg is None:
            raise ConnectionError(
                f"No response from OpenArm motor '{motor}' "
                f"(send ID: 0x{self._get_motor_id(motor):02X}, "
                f"recv ID: 0x{self._get_motor_recv_id(motor):02X})."
            )
        self._process_response(motor, msg)
        return self._get_cached_value(motor, data_name)

    @check_if_not_connected
    def write(self, data_name: str, motor: str, value: Value) -> None:
        if data_name in {"Kp", "Kd"}:
            self._gains[motor][data_name.lower()] = float(value)
        elif data_name == "Goal_Position":
            gains = self._gains[motor]
            self._mit_control(motor, gains["kp"], gains["kd"], float(value), 0.0, 0.0)
        else:
            raise ValueError(f"Writing '{data_name}' is not supported in OpenArm MIT mode.")

    def sync_read(
        self,
        data_name: str,
        motors: str | list[str] | None = None,
    ) -> dict[str, Value]:
        target_motors = self._get_motors_list(motors)
        self._batch_refresh(target_motors)
        return {motor: self._get_cached_value(motor, data_name) for motor in target_motors}

    def sync_read_all_states(
        self,
        motors: str | list[str] | None = None,
        *,
        num_retry: int = 0,
    ) -> dict[str, MotorState]:
        del num_retry
        target_motors = self._get_motors_list(motors)
        self._batch_refresh(target_motors)
        return {motor: self._last_known_states[motor].copy() for motor in target_motors}

    @check_if_not_connected
    def sync_write(self, data_name: str, values: dict[str, Value]) -> None:
        if data_name in {"Kp", "Kd"}:
            key = data_name.lower()
            for motor, value in values.items():
                self._gains[motor][key] = float(value)
        elif data_name == "Goal_Position":
            commands = {
                motor: (
                    self._gains[motor]["kp"],
                    self._gains[motor]["kd"],
                    float(value),
                    0.0,
                    0.0,
                )
                for motor, value in values.items()
            }
            self._mit_control_batch(commands)
        else:
            for motor, value in values.items():
                self.write(data_name, motor, value)

    def _batch_refresh(self, motors: list[str]) -> None:
        if self.canbus is None:
            raise RuntimeError("CAN bus is not initialized.")

        for motor in motors:
            motor_id = self._get_motor_id(motor)
            msg = can.Message(  # type: ignore[union-attr]
                arbitration_id=CAN_PARAM_ID,
                data=[motor_id & 0xFF, (motor_id >> 8) & 0xFF, CAN_CMD_REFRESH, 0, 0, 0, 0, 0],
                is_extended_id=False,
                is_fd=self.use_can_fd,
            )
            self.canbus.send(msg)

        recv_ids = [self._get_motor_recv_id(motor) for motor in motors]
        responses = self._recv_all_responses(recv_ids, timeout=MEDIUM_TIMEOUT_SEC)
        for motor in motors:
            response = responses.get(self._get_motor_recv_id(motor))
            if response:
                self._process_response(motor, response)
            else:
                logger.warning("OpenArm packet drop on %s. Using last known state.", motor)

    def _get_cached_value(self, motor: str, data_name: str) -> Value:
        state = self._last_known_states[motor]
        mapping: dict[str, Value] = {
            "Present_Position": state["position"],
            "Present_Velocity": state["velocity"],
            "Present_Torque": state["torque"],
            "Temperature_MOS": state["temp_mos"],
            "Temperature_Rotor": state["temp_rotor"],
        }
        if data_name not in mapping:
            raise ValueError(f"Unknown Damiao data name: {data_name}")
        return mapping[data_name]

    def read_calibration(self) -> dict[str, MotorCalibration]:
        return self.calibration if self.calibration else {}

    def write_calibration(self, calibration_dict: dict[str, MotorCalibration], cache: bool = True) -> None:
        if cache:
            self.calibration = calibration_dict

    def _get_motors_list(self, motors: str | list[str] | None) -> list[str]:
        if motors is None:
            return list(self.motors.keys())
        if isinstance(motors, str):
            return [motors]
        if isinstance(motors, list):
            return motors
        raise TypeError(f"Invalid motors selector: {type(motors)}")

    def _get_motor_id(self, motor: NameOrID) -> int:
        if isinstance(motor, str):
            if motor not in self.motors:
                raise ValueError(f"Unknown OpenArm motor: {motor}")
            return self.motors[motor].id
        return motor

    def _get_motor_name(self, motor: NameOrID) -> str:
        if isinstance(motor, str):
            return motor
        for name, value in self.motors.items():
            if value.id == motor:
                return name
        raise ValueError(f"Unknown OpenArm motor ID: {motor}")

    def _get_motor_recv_id(self, motor: NameOrID) -> int:
        motor_name = self._get_motor_name(motor)
        motor_obj = self.motors.get(motor_name)
        if motor_obj and motor_obj.recv_id is not None:
            return motor_obj.recv_id
        raise ValueError(f"OpenArm motor '{motor_name}' does not have a recv_id.")
