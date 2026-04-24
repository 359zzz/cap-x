from __future__ import annotations

import sys
from typing import TextIO


def read_console_line(
    prompt: str,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> str:
    """Read one console line without crashing on malformed terminal bytes."""

    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    out_stream.write(prompt)
    out_stream.flush()

    buffer = getattr(in_stream, "buffer", None)
    encoding = getattr(in_stream, "encoding", None) or "utf-8"

    if buffer is not None:
        data = buffer.readline()
        if data == b"":
            raise EOFError
        text = data.decode(encoding, errors="replace")
        return text.rstrip("\r\n")

    text = in_stream.readline()
    if text == "":
        raise EOFError
    return text.rstrip("\r\n")
