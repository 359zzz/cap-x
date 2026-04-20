from __future__ import annotations

from typing import Any

import requests

from capx.web.models import (
    NanobotTaskActionResponse,
    NanobotTaskStartRequest,
    NanobotTaskStatusResponse,
)


class CapxNanobotTaskClient:
    """HTTP client for the cap-x nanobot relay endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8200",
        *,
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._session = requests.Session()

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/nanobot/health")

    def start_task(self, request: NanobotTaskStartRequest) -> NanobotTaskActionResponse:
        payload = request.model_dump()
        data = self._request_json("POST", "/api/nanobot/tasks/start", payload=payload)
        return NanobotTaskActionResponse.model_validate(data)

    def get_task(self, session_id: str) -> NanobotTaskStatusResponse:
        data = self._request_json("GET", f"/api/nanobot/tasks/{session_id}")
        return NanobotTaskStatusResponse.model_validate(data)

    def inject_task(
        self,
        session_id: str,
        text: str,
        *,
        media: list[str] | None = None,
    ) -> NanobotTaskActionResponse:
        data = self._request_json(
            "POST",
            f"/api/nanobot/tasks/{session_id}/inject",
            payload={"text": text, "media": list(media or [])},
        )
        return NanobotTaskActionResponse.model_validate(data)

    def stop_task(self, session_id: str) -> NanobotTaskActionResponse:
        data = self._request_json("POST", f"/api/nanobot/tasks/{session_id}/stop")
        return NanobotTaskActionResponse.model_validate(data)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self._session.request(
                method,
                url,
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"cap-x relay request failed: {method} {url}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"cap-x relay returned non-JSON response: {url}") from exc

        if not isinstance(body, dict):
            raise RuntimeError(f"cap-x relay returned unexpected payload type: {type(body)!r}")
        return body
