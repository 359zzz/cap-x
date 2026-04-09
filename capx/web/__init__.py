"""CaP-X Interactive Web UI Backend.

This module provides a FastAPI-based web server with WebSocket support
for real-time interactive robot code execution demos.
"""

from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any):
    """Lazily import the FastAPI app factory.

    This keeps lightweight modules such as ``capx.web.models`` importable
    without eagerly importing the full web server dependency stack.
    """
    from capx.web.server import create_app as _create_app

    return _create_app(*args, **kwargs)

__all__ = ["create_app"]
