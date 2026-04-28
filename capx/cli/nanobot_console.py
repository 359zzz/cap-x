from __future__ import annotations

import argparse
import asyncio

from capx.nanobot import (
    CapxNanobotRobotShell,
    InboundMessage,
    MessageBus,
    RobotShellConfig,
)
from capx.nanobot.console_io import read_console_line
from capx.utils.runtime_defaults import (
    default_llm_model_name,
    default_llm_server_url,
    default_web_base_url,
)


async def _print_outbound(bus: MessageBus) -> None:
    while True:
        msg = await bus.consume_outbound()
        print()
        print("-" * 40)
        print("智能体（已接入千问大模型）")
        print("-" * 40)
        print(msg.content.rstrip())
        if msg.media:
            count = len(msg.media)
            print(f"图片  {count} 项")
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
            use_visual_feedback=args.use_visual_feedback,
            use_img_differencing=args.use_img_differencing,
            visual_differencing_model=args.visual_differencing_model,
            visual_differencing_model_server_url=args.visual_differencing_server_url,
            await_user_input_each_turn=args.await_user_input_each_turn,
            execution_timeout=args.execution_timeout,
            poll_interval_s=args.poll_interval,
        ),
    )

    await shell.start()
    printer_task = asyncio.create_task(_print_outbound(bus))

    print("-" * 40)
    print("多模态智能体")
    print("-" * 40)
    print("输入自然语言指令")
    print("命令  /help  /status  /stop  exit")
    print()

    try:
        while True:
            try:
                text = await asyncio.to_thread(read_console_line, "用户: ")
            except EOFError:
                break
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
        default=default_web_base_url(),
        help="cap-x web relay base URL. Defaults to CAPX_WEB_BASE_URL or http://127.0.0.1:8200.",
    )
    parser.add_argument(
        "--config-path",
        default=None,
        help="Default cap-x YAML config path used when starting a new task.",
    )
    parser.add_argument(
        "--model",
        default=default_llm_model_name(),
        help="Model name passed to cap-x. Defaults to LLM_MODEL_NAME or qwen3.6-plus.",
    )
    parser.add_argument(
        "--llm-server-url",
        default=default_llm_server_url(),
        help="OpenAI-compatible chat completions endpoint used by cap-x. Defaults to CAPX_LLM_SERVER_URL or http://127.0.0.1:8110/chat/completions.",
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
        "--use-visual-feedback",
        type=lambda value: value.strip().lower() in {"1", "true", "yes", "on"},
        default=None,
        help="Override cap-x use_visual_feedback. Use True for image input to the model.",
    )
    parser.add_argument(
        "--use-img-differencing",
        type=lambda value: value.strip().lower() in {"1", "true", "yes", "on"},
        default=None,
        help="Override cap-x use_img_differencing. Use True for VLM state descriptions.",
    )
    parser.add_argument(
        "--visual-differencing-model",
        default=None,
        help="Model used for image differencing. Defaults to --model.",
    )
    parser.add_argument(
        "--visual-differencing-server-url",
        default=None,
        help="Chat completions endpoint for the image differencing model. Defaults to --llm-server-url.",
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
