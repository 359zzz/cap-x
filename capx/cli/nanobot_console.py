from __future__ import annotations

import argparse
import asyncio

from capx.nanobot import (
    CapxNanobotRobotShell,
    InboundMessage,
    MessageBus,
    RobotShellConfig,
)


async def _print_outbound(bus: MessageBus) -> None:
    while True:
        msg = await bus.consume_outbound()
        print()
        print("Robot:")
        print(msg.content)
        print()


async def _run_console(args: argparse.Namespace) -> None:
    bus = MessageBus()
    shell = CapxNanobotRobotShell(
        bus,
        RobotShellConfig(
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
    )

    await shell.start()
    printer_task = asyncio.create_task(_print_outbound(bus))

    print("Capx Nanobot Console")
    print("Type natural language to start/inject tasks.")
    print("Commands: /help /status /stop exit")
    print()

    try:
        while True:
            text = await asyncio.to_thread(input, "You: ")
            if text.strip().lower() in {"exit", "quit"}:
                break
            await bus.publish_inbound(
                InboundMessage(
                    channel="cli",
                    sender_id="local-user",
                    chat_id="local-chat",
                    content=text,
                )
            )
    finally:
        printer_task.cancel()
        try:
            await printer_task
        except asyncio.CancelledError:
            pass
        await shell.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local nanobot-style console shell for the cap-x robot runtime.",
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
        help="How often the console shell polls task status.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_run_console(args))


if __name__ == "__main__":
    main()
