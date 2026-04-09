from __future__ import annotations

from typing import Any

import numpy as np

from capx.envs.base import BaseEnv
from capx.integrations.openarm.assets import OpenArmMotionAssetRegistry
from capx.integrations.openarm.recording import ManualOpenArmRecorder
from capx.integrations.openarm.runtime import OpenArmRuntime, OpenArmRuntimeConfig


class OpenArmRealLowLevel(BaseEnv):
    def __init__(
        self,
        seed: int | None = None,
        privileged: bool = False,
        enable_render: bool = False,
        viser_debug: bool = False,
    ) -> None:
        del seed, privileged, enable_render, viser_debug
        super().__init__()
        self.runtime = OpenArmRuntime(OpenArmRuntimeConfig())
        self.asset_registry = OpenArmMotionAssetRegistry()
        self.recorder = ManualOpenArmRecorder(self.runtime, self.asset_registry)
        self._record_frames = False
        self._frame_buffer: list[np.ndarray] = []

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        del seed, options
        self.runtime.connect()
        obs = self.get_observation()
        return obs, {}

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        del action
        obs = self.get_observation()
        return obs, 0.0, False, False, {}

    def get_observation(self) -> dict[str, Any]:
        obs = self.runtime.get_observation()
        if self._record_frames:
            frame = self._extract_first_rgb_frame(obs)
            if frame is not None:
                self._frame_buffer.append(frame.copy())
        return obs

    def compute_reward(self) -> float:
        return 0.0

    def task_completed(self) -> bool:
        return False

    def render(self, mode: str = "rgb_array") -> np.ndarray:  # type: ignore[override]
        del mode
        frame = self._extract_first_rgb_frame(self.get_observation())
        if frame is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        return frame

    def close(self) -> None:
        self.runtime.disconnect()

    def enable_video_capture(self, enabled: bool = True, *, clear: bool = True) -> None:
        self._record_frames = enabled
        if clear:
            self._frame_buffer.clear()
        if enabled:
            frame = self._extract_first_rgb_frame(self.get_observation())
            if frame is not None:
                self._frame_buffer.append(frame.copy())

    def get_video_frames(self, *, clear: bool = False) -> list[np.ndarray]:
        frames = [frame.copy() for frame in self._frame_buffer]
        if clear:
            self._frame_buffer.clear()
        return frames

    def get_video_frame_count(self) -> int:
        return len(self._frame_buffer)

    def get_video_frames_range(self, start: int, end: int) -> list[np.ndarray]:
        return [frame.copy() for frame in self._frame_buffer[start:end]]

    def _extract_first_rgb_frame(self, obs: dict[str, Any]) -> np.ndarray | None:
        for value in obs.get("cameras", {}).values():
            if isinstance(value, np.ndarray) and value.ndim == 3 and value.shape[-1] in {3, 4}:
                return value[..., :3]
        return None


__all__ = ["OpenArmRealLowLevel"]
