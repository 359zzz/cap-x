from __future__ import annotations

import os

DEFAULT_LLM_MODEL_NAME = "qwen3.6-plus"
DEFAULT_LLM_SERVER_URL = "http://127.0.0.1:8110/chat/completions"
DEFAULT_WEB_BASE_URL = "http://127.0.0.1:8200"


def default_llm_model_name() -> str:
    return os.getenv("LLM_MODEL_NAME") or DEFAULT_LLM_MODEL_NAME


def default_llm_server_url() -> str:
    return os.getenv("CAPX_LLM_SERVER_URL") or DEFAULT_LLM_SERVER_URL


def default_web_base_url() -> str:
    return os.getenv("CAPX_WEB_BASE_URL") or DEFAULT_WEB_BASE_URL
