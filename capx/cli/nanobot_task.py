from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import requests


def _print_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _optional_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _server_base_url(args: argparse.Namespace) -> str:
    return (args.server or os.getenv("CAPX_WEB_BASE_URL") or "http://127.0.0.1:8200").rstrip("/")


def _load_media(values: list[str] | None) -> list[str]:
    media: list[str] = []
    for value in values or []:
        if value.startswith(("data:", "http://", "https://")):
            media.append(value)
            continue
        path = Path(value).expanduser()
        if not path.exists():
            raise SystemExit(f"Image file not found: {value}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        media.append(f"data:{mime_type};base64,{encoded}")
    return media


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.request(method, url, json=payload, timeout=10)
    try:
        body = response.json()
    except ValueError:
        body = {"status_code": response.status_code, "text": response.text}
    if response.ok:
        return body
    detail = body.get("detail") if isinstance(body, dict) else None
    raise SystemExit(f"HTTP {response.status_code}: {detail or body}")


def cmd_health(args: argparse.Namespace) -> None:
    url = f"{_server_base_url(args)}/api/nanobot/health"
    _print_payload(_request("GET", url))


def cmd_start(args: argparse.Namespace) -> None:
    url = f"{_server_base_url(args)}/api/nanobot/tasks/start"
    payload = {
        "config_path": args.config_path,
        "initial_instruction": args.instruction,
        "model": args.model,
        "server_url": args.llm_server_url,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "await_user_input_each_turn": args.await_user_input_each_turn,
        "execution_timeout": args.execution_timeout,
        "initial_media": _load_media(args.image),
    }
    if args.use_visual_feedback is not None:
        payload["use_visual_feedback"] = args.use_visual_feedback
    if args.use_img_differencing is not None:
        payload["use_img_differencing"] = args.use_img_differencing
    if args.visual_differencing_model is not None:
        payload["visual_differencing_model"] = args.visual_differencing_model
    if args.visual_differencing_server_url is not None:
        payload["visual_differencing_model_server_url"] = args.visual_differencing_server_url
    _print_payload(_request("POST", url, payload=payload))


def cmd_status(args: argparse.Namespace) -> None:
    url = f"{_server_base_url(args)}/api/nanobot/tasks/{args.session_id}"
    _print_payload(_request("GET", url))


def cmd_inject(args: argparse.Namespace) -> None:
    url = f"{_server_base_url(args)}/api/nanobot/tasks/{args.session_id}/inject"
    _print_payload(_request("POST", url, payload={"text": args.text, "media": _load_media(args.image)}))


def cmd_stop(args: argparse.Namespace) -> None:
    url = f"{_server_base_url(args)}/api/nanobot/tasks/{args.session_id}/stop"
    _print_payload(_request("POST", url))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control cap-x nanobot relay tasks from the command line.",
    )
    parser.add_argument(
        "--server",
        default=None,
        help="cap-x web server base URL. Defaults to CAPX_WEB_BASE_URL or http://127.0.0.1:8200.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Check nanobot relay health.")
    health_parser.set_defaults(func=cmd_health)

    start_parser = subparsers.add_parser("start", help="Start a nanobot-driven cap-x task.")
    start_parser.add_argument("instruction", help="Initial task instruction sent to cap-x.")
    start_parser.add_argument(
        "--config-path",
        default=None,
        help="cap-x YAML config path. If omitted, the web server default config is used.",
    )
    start_parser.add_argument(
        "--model",
        default="qwen3.5-plus",
        help="LLM model name passed to cap-x.",
    )
    start_parser.add_argument(
        "--llm-server-url",
        default="http://127.0.0.1:8110/chat/completions",
        help="OpenAI-compatible chat completions endpoint used by cap-x.",
    )
    start_parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Model sampling temperature.",
    )
    start_parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Maximum completion tokens.",
    )
    start_parser.add_argument(
        "--await-user-input-each-turn",
        type=_optional_bool,
        default=True,
        help="Whether cap-x pauses after each turn for follow-up guidance.",
    )
    start_parser.add_argument(
        "--execution-timeout",
        type=int,
        default=180,
        help="Per-code-block execution timeout in seconds.",
    )
    start_parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Attach an image path, data URL, or HTTP URL to the initial nanobot instruction. Repeat for multiple images.",
    )
    start_parser.add_argument(
        "--use-visual-feedback",
        type=_optional_bool,
        default=None,
        help="Override cap-x use_visual_feedback. Omit to keep config behavior.",
    )
    start_parser.add_argument(
        "--use-img-differencing",
        type=_optional_bool,
        default=None,
        help="Override cap-x use_img_differencing. Omit to keep config behavior.",
    )
    start_parser.add_argument(
        "--visual-differencing-model",
        default=None,
        help="Optional visual differencing model override.",
    )
    start_parser.add_argument(
        "--visual-differencing-server-url",
        default=None,
        help="Optional visual differencing server override.",
    )
    start_parser.set_defaults(func=cmd_start)

    status_parser = subparsers.add_parser("status", help="Get one task status.")
    status_parser.add_argument("session_id", help="Session ID returned by the start command.")
    status_parser.set_defaults(func=cmd_status)

    inject_parser = subparsers.add_parser("inject", help="Inject follow-up guidance.")
    inject_parser.add_argument("session_id", help="Session ID returned by the start command.")
    inject_parser.add_argument("text", help="Follow-up instruction text.")
    inject_parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Attach an image path, data URL, or HTTP URL to the follow-up instruction. Repeat for multiple images.",
    )
    inject_parser.set_defaults(func=cmd_inject)

    stop_parser = subparsers.add_parser("stop", help="Stop one task.")
    stop_parser.add_argument("session_id", help="Session ID returned by the start command.")
    stop_parser.set_defaults(func=cmd_stop)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
