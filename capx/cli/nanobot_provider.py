from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from capx.nanobot.provider import CustomProvider
from capx.utils.runtime_defaults import default_llm_model_name


def _print_payload(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _build_provider(args: argparse.Namespace) -> CustomProvider:
    api_key = args.api_key or os.getenv("LLM_API_KEY") or "no-key"
    api_base = args.api_base or os.getenv("LLM_BASE_URL") or "http://127.0.0.1:8110"
    default_model = args.model or default_llm_model_name()
    return CustomProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=default_model,
    )


async def _run_ping(args: argparse.Namespace) -> None:
    provider = _build_provider(args)
    response = await provider.chat(
        messages=[{"role": "user", "content": "Reply with exactly PONG"}],
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
    )
    _print_payload(
        {
            "ok": (response.content or "").strip() == "PONG",
            "model": args.model or provider.get_default_model(),
            "finish_reason": response.finish_reason,
            "content": response.content,
            "usage": response.usage,
        }
    )


async def _run_chat(args: argparse.Namespace) -> None:
    provider = _build_provider(args)
    response = await provider.chat(
        messages=[{"role": "user", "content": args.prompt}],
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
    )
    _print_payload(
        {
            "model": args.model or provider.get_default_model(),
            "finish_reason": response.finish_reason,
            "content": response.content,
            "tool_calls": [tool_call.to_openai_tool_call() for tool_call in response.tool_calls],
            "usage": response.usage,
            "reasoning_content": response.reasoning_content,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check the nanobot-compatible OpenAI provider wiring inside cap-x.",
    )
    parser.add_argument(
        "--api-base",
        default=None,
        help="OpenAI-compatible base URL. Defaults to LLM_BASE_URL or http://127.0.0.1:8110.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key. Defaults to LLM_API_KEY or 'no-key'.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name. Defaults to LLM_MODEL_NAME or qwen3.6-plus.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="Maximum completion tokens.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="medium",
        help="Reasoning effort passed through to the provider.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ping_parser = subparsers.add_parser("ping", help="Send a minimal provider health prompt.")
    ping_parser.set_defaults(func=_run_ping)

    chat_parser = subparsers.add_parser("chat", help="Send one prompt to the provider.")
    chat_parser.add_argument("prompt", help="Prompt text sent as the single user message.")
    chat_parser.set_defaults(func=_run_chat)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
