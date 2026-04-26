"""OpenArm perception gateway with an OpenAI-compatible VLM backend.

This service is a lightweight in-repo replacement for the external
``openclaw_realsense_agent`` endpoints expected by the OpenArm adapter:

    GET  /health
    GET  /tactile/health
    POST /tactile/read
    POST /detect_once

It also exposes ``POST /describe_once`` for scene-level visual descriptions.
The vision backend is any OpenAI-compatible chat-completions endpoint, such as
the local 8110 proxy pointed at DashScope/Qwen.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


@dataclass
class VisionGatewayConfig:
    model: str = os.getenv("CAPX_OPENARM_VISION_MODEL", "qwen3.6-plus")
    server_url: str = os.getenv(
        "CAPX_OPENARM_VISION_SERVER_URL",
        os.getenv("CAPX_LLM_SERVER_URL", "http://127.0.0.1:8110/chat/completions"),
    )
    api_key: str | None = os.getenv("CAPX_OPENARM_VISION_API_KEY") or None
    timeout_s: float = float(os.getenv("CAPX_OPENARM_VISION_TIMEOUT_S", "60"))
    max_tokens: int = int(os.getenv("CAPX_OPENARM_VISION_MAX_TOKENS", "1024"))
    camera_snapshot_url: str | None = os.getenv("CAPX_OPENARM_CAMERA_SNAPSHOT_URL") or None
    camera_image_path: str | None = os.getenv("CAPX_OPENARM_CAMERA_IMAGE_PATH") or None
    camera_base64: str | None = os.getenv("CAPX_OPENARM_CAMERA_BASE64") or None
    tactile_base_url: str | None = os.getenv("CAPX_OPENARM_TACTILE_BASE_URL") or None


class DetectOnceRequest(BaseModel):
    target: str | None = None
    top_k: int = 3
    prompt: str | None = None
    image_base64: str | None = None
    image_url: str | None = None


class DescribeOnceRequest(BaseModel):
    prompt: str | None = None
    image_base64: str | None = None
    image_url: str | None = None


class TactileReadRequest(BaseModel):
    include_taxels: bool = False
    max_taxels: int = 8
    include_raw_response: bool = False


class VisionResult(BaseModel):
    status: str = "ok"
    description: str = ""
    detections: list[dict[str, Any]] = Field(default_factory=list)
    image_base64: str | None = None
    images: list[str] = Field(default_factory=list)
    model: str | None = None
    raw_content: str | None = None


def create_app(config: VisionGatewayConfig | None = None) -> FastAPI:
    cfg = config or VisionGatewayConfig()
    app = FastAPI(
        title="cap-x OpenArm Perception Gateway",
        description="OpenClaw-compatible perception endpoints backed by an OpenAI-compatible VLM.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "capx.openarm_perception_gateway",
            "model": cfg.model,
            "server_url": cfg.server_url,
            "image_source_configured": bool(
                cfg.camera_snapshot_url or cfg.camera_image_path or cfg.camera_base64
            ),
            "endpoints": ["/describe_once", "/detect_once", "/tactile/health", "/tactile/read"],
        }

    @app.get("/tactile/health")
    async def tactile_health() -> dict[str, Any]:
        if cfg.tactile_base_url:
            return _forward_json("GET", cfg.tactile_base_url.rstrip("/") + "/tactile/health")
        return {"status": "disabled", "detail": "No CAPX_OPENARM_TACTILE_BASE_URL configured."}

    @app.post("/tactile/read")
    async def tactile_read(request: TactileReadRequest) -> dict[str, Any]:
        if cfg.tactile_base_url:
            return _forward_json(
                "POST",
                cfg.tactile_base_url.rstrip("/") + "/tactile/read",
                payload=request.model_dump(),
            )
        return {
            "status": "disabled",
            "contact": False,
            "stable_grasp": False,
            "detail": "No CAPX_OPENARM_TACTILE_BASE_URL configured.",
        }

    @app.post("/describe_once", response_model=VisionResult)
    async def describe_once(request: DescribeOnceRequest) -> VisionResult:
        image_url = _resolve_image_url(
            request_image=request.image_base64,
            request_url=request.image_url,
            cfg=cfg,
        )
        if not image_url:
            return _no_image_result(cfg)
        prompt = request.prompt or "Describe the current robot camera image for a robot manipulation task."
        return _query_vision(
            cfg,
            image_url=image_url,
            prompt=prompt,
            target=None,
            top_k=0,
        )

    @app.post("/detect_once", response_model=VisionResult)
    async def detect_once(request: DetectOnceRequest) -> VisionResult:
        image_url = _resolve_image_url(
            request_image=request.image_base64,
            request_url=request.image_url,
            cfg=cfg,
        )
        if not image_url:
            return _no_image_result(cfg)
        target = request.target.strip() if isinstance(request.target, str) and request.target.strip() else None
        prompt = request.prompt or _build_detection_prompt(target=target, top_k=request.top_k)
        return _query_vision(
            cfg,
            image_url=image_url,
            prompt=prompt,
            target=target,
            top_k=request.top_k,
        )

    return app


def _query_vision(
    cfg: VisionGatewayConfig,
    *,
    image_url: str,
    prompt: str,
    target: str | None,
    top_k: int,
) -> VisionResult:
    system_prompt = (
        "You are a robot perception adapter. Return strict JSON only. "
        "Use this schema: {\"description\": string, \"detections\": ["
        "{\"label\": string, \"confidence\": number, \"pixel_center\": [x,y] or null, "
        "\"bbox_xyxy\": [x1,y1,x2,y2] or null, \"camera_xyz_m\": [x,y,z] or null, "
        "\"depth_m\": number or null}]}. If metric 3D/depth is unavailable, use null."
    )
    if target:
        user_text = (
            f"Target: {target}\nTop K: {top_k}\n{prompt}\n"
            "Find task-relevant instances of the target in the image."
        )
    else:
        user_text = f"{prompt}\nIf no specific target is requested, detections can be an empty list."

    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": cfg.max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    try:
        response = requests.post(cfg.server_url, headers=headers, json=payload, timeout=cfg.timeout_s)
        response.raise_for_status()
        content = _extract_message_content(response.json())
        parsed = _parse_json_content(content)
    except Exception as exc:
        return VisionResult(
            status="error",
            description=f"Vision model request failed: {exc}",
            detections=[],
            image_base64=image_url,
            images=[image_url],
            model=cfg.model,
        )

    description = str(parsed.get("description") or parsed.get("summary") or content)
    detections = parsed.get("detections")
    if not isinstance(detections, list):
        detections = []
    return VisionResult(
        status="ok",
        description=description,
        detections=[item for item in detections if isinstance(item, dict)][: max(top_k, 0) or None],
        image_base64=image_url,
        images=[image_url],
        model=cfg.model,
        raw_content=content,
    )


def _build_detection_prompt(*, target: str | None, top_k: int) -> str:
    if target:
        return (
            f"Identify up to {top_k} visible instance(s) of {target}. "
            "Describe where they are in the image and return approximate pixel centers/bounding boxes when possible."
        )
    return (
        f"Identify up to {top_k} manipulation-relevant visible objects. "
        "Describe where they are in the image and return approximate pixel centers/bounding boxes when possible."
    )


def _resolve_image_url(
    *,
    request_image: str | None,
    request_url: str | None,
    cfg: VisionGatewayConfig,
) -> str | None:
    if request_image:
        return _ensure_image_url(request_image)
    if request_url:
        return request_url
    if cfg.camera_base64:
        return _ensure_image_url(cfg.camera_base64)
    if cfg.camera_image_path:
        path = Path(cfg.camera_image_path).expanduser()
        if path.exists():
            return _image_file_to_data_url(path)
    if cfg.camera_snapshot_url:
        return _fetch_snapshot(cfg.camera_snapshot_url)
    return None


def _fetch_snapshot(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return None

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        encoded = base64.b64encode(response.content).decode("utf-8")
        return f"data:{content_type.split(';', 1)[0]};base64,{encoded}"

    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("image_base64", "image", "image_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return _ensure_image_url(value)
    images = payload.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, str) and item:
                return _ensure_image_url(item)
    return None


def _ensure_image_url(value: str) -> str:
    clean = value.strip()
    if clean.startswith(("data:", "http://", "https://")):
        return clean
    return f"data:image/png;base64,{clean}"


def _image_file_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _extract_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    return json.dumps(body, ensure_ascii=False)


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"description": content, "detections": []}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"description": content, "detections": []}
        except json.JSONDecodeError:
            pass
    return {"description": content, "detections": []}


def _forward_json(method: str, url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.request(method, url, json=payload, timeout=5)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {"value": body}


def _no_image_result(cfg: VisionGatewayConfig) -> VisionResult:
    return VisionResult(
        status="no_image",
        description=(
            "No camera image is configured. Set CAPX_OPENARM_CAMERA_SNAPSHOT_URL, "
            "CAPX_OPENARM_CAMERA_IMAGE_PATH, or pass image_base64/image_url to the request."
        ),
        detections=[],
        model=cfg.model,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the cap-x OpenArm perception gateway.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument("--model", default=None, help="Vision model name. Defaults to CAPX_OPENARM_VISION_MODEL.")
    parser.add_argument("--server-url", default=None, help="OpenAI-compatible chat completions URL.")
    parser.add_argument("--api-key", default=None, help="Optional API key for the vision endpoint.")
    parser.add_argument("--camera-snapshot-url", default=None, help="HTTP endpoint returning an image or JSON image payload.")
    parser.add_argument("--camera-image-path", default=None, help="Local image file used as the camera source.")
    parser.add_argument("--tactile-base-url", default=None, help="Optional tactile service base URL to forward tactile endpoints.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = VisionGatewayConfig()
    if args.model:
        cfg.model = args.model
    if args.server_url:
        cfg.server_url = args.server_url
    if args.api_key:
        cfg.api_key = args.api_key
    if args.camera_snapshot_url:
        cfg.camera_snapshot_url = args.camera_snapshot_url
    if args.camera_image_path:
        cfg.camera_image_path = args.camera_image_path
    if args.tactile_base_url:
        cfg.tactile_base_url = args.tactile_base_url
    uvicorn.run(create_app(cfg), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
