from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseChannel

_INTERNAL = frozenset({"base", "manager", "registry"})


def discover_channel_names() -> list[str]:
    """Return all embedded channel module names."""
    import capx.nanobot.channels as pkg

    return [
        name
        for _, name, ispkg in pkgutil.iter_modules(pkg.__path__)
        if name not in _INTERNAL and not ispkg
    ]


def load_channel_class(module_name: str) -> type["BaseChannel"]:
    """Import one channel module and return its BaseChannel subclass."""
    from .base import BaseChannel as _BaseChannel

    mod = importlib.import_module(f"capx.nanobot.channels.{module_name}")
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and issubclass(obj, _BaseChannel) and obj is not _BaseChannel:
            return obj
    raise ImportError(f"No BaseChannel subclass found in capx.nanobot.channels.{module_name}")
