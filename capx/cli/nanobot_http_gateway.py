from __future__ import annotations

import argparse

import uvicorn

from capx.nanobot import (
    CapxNanobotRuntimeConfig,
    ConsoleChannelConfig,
    HttpBridgeChannelConfig,
    RobotShellConfig,
)
from capx.nanobot.gateway_app import create_gateway_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the embedded cap-x nanobot HTTP gateway.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP gateway bind host.")
    parser.add_argument("--port", type=int, default=8300, help="HTTP gateway bind port.")
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:8200",
        help="cap-x web relay base URL.",
    )
    parser.add_argument(
        "--config-path",
        default=None,
        help="Default cap-x YAML config path used when starting a new task.",
    )
    parser.add_argument("--model", default="openai/gpt-5.4", help="Model name passed to cap-x.")
    parser.add_argument(
        "--llm-server-url",
        default="http://127.0.0.1:8110/chat/completions",
        help="OpenAI-compatible chat completions endpoint used by cap-x.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature passed to cap-x.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="Maximum completion tokens passed to cap-x.",
    )
    parser.add_argument(
        "--await-user-input-each-turn",
        type=lambda value: value.strip().lower() in {"1", "true", "yes", "on"},
        default=True,
        help="Whether cap-x pauses after each turn for follow-up guidance.",
    )
    parser.add_argument(
        "--execution-timeout",
        type=int,
        default=180,
        help="Per-code-block execution timeout in seconds.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="How often the shell polls task status.",
    )
    parser.add_argument(
        "--max-pending-per-chat",
        type=int,
        default=100,
        help="Maximum buffered outbound messages kept per chat.",
    )
    parser.add_argument(
        "--enable-console",
        action="store_true",
        help="Also enable the built-in console channel alongside the HTTP bridge.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    app = create_gateway_app(
        CapxNanobotRuntimeConfig(
            shell=RobotShellConfig(
                relay_base_url=args.server,
                config_path=args.config_path,
                model=args.model,
                server_url=args.llm_server_url,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                await_user_input_each_turn=args.await_user_input_each_turn,
                execution_timeout=args.execution_timeout,
                poll_interval_s=args.poll_interval,
            ),
            console=ConsoleChannelConfig(),
            http_bridge=HttpBridgeChannelConfig(max_pending_per_chat=args.max_pending_per_chat),
            enable_console_channel=args.enable_console,
            enable_http_channel=True,
        )
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
