from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class OpenClawPerceptionConfig:
    base_url: str = "http://127.0.0.1:8000"
    timeout_s: float = 3.0
    enabled: bool = True


class OpenClawServiceAdapter:
    def __init__(self, config: OpenClawPerceptionConfig | None = None) -> None:
        self.config = config or OpenClawPerceptionConfig()
        self._session = requests.Session()

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.base_url)

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def tactile_health(self) -> dict[str, Any]:
        return self._request_json("GET", "/tactile/health")

    def tactile_read(self) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/tactile/read",
            json={
                "include_taxels": False,
                "max_taxels": 8,
                "include_raw_response": False,
            },
        )

    def detect_once(self, target: str | None, top_k: int = 3) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/detect_once",
            json={"target": target, "top_k": top_k},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "detail": "perception adapter disabled"}
        url = self.config.base_url.rstrip("/") + path
        try:
            response = self._session.request(
                method,
                url,
                json=json,
                timeout=self.config.timeout_s,
            )
            response.raise_for_status()
            return dict(response.json())
        except requests.RequestException as exc:
            raise RuntimeError(f"OpenClaw service request failed: {method} {url}") from exc
