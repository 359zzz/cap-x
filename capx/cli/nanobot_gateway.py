from __future__ import annotations

import argparse
import asyncio

from capx.nanobot import (
    CapxNanobotRuntime,
    CapxNanobotRuntimeConfig,
    ConsoleChannelConfig,
    RobotShellConfig,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the embedded cap-x nanobot gateway runtime.",
    )
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
    parser.add_argument(
        "--model",
        default="openai/gpt-5.4",
        help="Model name passed to cap-x.",
    )
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
        "--disable-console",
        action="store_true",
        help="Start the runtime without the built-in console channel.",
    )
    return parser


async def _run_gateway(args: argparse.Namespace) -> None:
    runtime = CapxNanobotRuntime(
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
            enable_console_channel=not args.disable_console,
        )
    )

    await runtime.start()
    try:
        await runtime.wait()
    finally:
        await runtime.stop()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_run_gateway(args))


if __name__ == "__main__":
    main()
