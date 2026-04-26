from __future__ import annotations

from capx.cli.nanobot_console import build_parser as build_console_parser
from capx.cli.nanobot_gateway import build_parser as build_gateway_parser
from capx.cli.nanobot_http_gateway import build_parser as build_http_gateway_parser
from capx.cli.nanobot_task import build_parser as build_task_parser
from capx.nanobot import RobotShellConfig
from capx.web.models import NanobotTaskStartRequest


def test_nanobot_task_request_uses_environment_defaults(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "qwen3.6-plus")
    monkeypatch.setenv("CAPX_LLM_SERVER_URL", "http://127.0.0.1:9110/chat/completions")

    request = NanobotTaskStartRequest(initial_instruction="pick up the cup")

    assert request.model == "qwen3.6-plus"
    assert request.server_url == "http://127.0.0.1:9110/chat/completions"
    assert request.visual_differencing_model == "qwen3.6-plus"
    assert request.visual_differencing_model_server_url == "http://127.0.0.1:9110/chat/completions"


def test_robot_shell_config_uses_environment_defaults(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "qwen3.6-plus")
    monkeypatch.setenv("CAPX_LLM_SERVER_URL", "http://127.0.0.1:9110/chat/completions")

    config = RobotShellConfig()

    assert config.model == "qwen3.6-plus"
    assert config.server_url == "http://127.0.0.1:9110/chat/completions"


def test_nanobot_cli_defaults_follow_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "qwen3.6-plus")
    monkeypatch.setenv("CAPX_LLM_SERVER_URL", "http://127.0.0.1:9110/chat/completions")
    monkeypatch.setenv("CAPX_WEB_BASE_URL", "http://127.0.0.1:9200")

    task_args = build_task_parser().parse_args(["start", "hello"])
    assert task_args.model == "qwen3.6-plus"
    assert task_args.llm_server_url == "http://127.0.0.1:9110/chat/completions"

    console_args = build_console_parser().parse_args([])
    assert console_args.server == "http://127.0.0.1:9200"
    assert console_args.model == "qwen3.6-plus"
    assert console_args.llm_server_url == "http://127.0.0.1:9110/chat/completions"

    http_gateway_args = build_http_gateway_parser().parse_args([])
    assert http_gateway_args.server == "http://127.0.0.1:9200"
    assert http_gateway_args.model == "qwen3.6-plus"
    assert http_gateway_args.llm_server_url == "http://127.0.0.1:9110/chat/completions"

    gateway_args = build_gateway_parser().parse_args([])
    assert gateway_args.server == "http://127.0.0.1:9200"
    assert gateway_args.model == "qwen3.6-plus"
    assert gateway_args.llm_server_url == "http://127.0.0.1:9110/chat/completions"
