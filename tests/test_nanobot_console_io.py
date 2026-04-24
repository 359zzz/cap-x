from __future__ import annotations

from io import BytesIO, StringIO

from capx.nanobot.console_io import read_console_line


class _FakeBinaryStdin:
    def __init__(self, data: bytes, encoding: str = "utf-8") -> None:
        self.buffer = BytesIO(data)
        self.encoding = encoding


def test_read_console_line_decodes_utf8_input() -> None:
    stdin = _FakeBinaryStdin("依次执行 tomato_dual_grasp_sync\n".encode("utf-8"))
    stdout = StringIO()

    text = read_console_line("You: ", stdin=stdin, stdout=stdout)

    assert text == "依次执行 tomato_dual_grasp_sync"
    assert stdout.getvalue() == "You: "


def test_read_console_line_replaces_invalid_terminal_bytes() -> None:
    stdin = _FakeBinaryStdin(b"\xe4\xbd\x00 replay safe_standby\n")
    stdout = StringIO()

    text = read_console_line("You: ", stdin=stdin, stdout=stdout)

    assert "replay safe_standby" in text
    assert stdout.getvalue() == "You: "


def test_read_console_line_raises_eof_on_empty_stream() -> None:
    stdin = _FakeBinaryStdin(b"")

    try:
        read_console_line("You: ", stdin=stdin, stdout=StringIO())
    except EOFError:
        return

    raise AssertionError("Expected EOFError for empty input stream")
