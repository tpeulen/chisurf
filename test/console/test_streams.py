"""The console streams are text streams: pdb, print and input take them as such."""

from __future__ import annotations

import io
import pdb
import typing

import pytest

from chisurf.core.console.streams import CapturingStream, InputStream, OutputStream


def test_output_reaches_the_sink_and_cannot_be_read():
    seen: list[tuple[str, str]] = []
    out = OutputStream("stdout", lambda name, text: seen.append((name, text)))
    assert isinstance(out, typing.TextIO)
    print("hello", file=out)
    out.writelines(["a", "b"])
    assert "".join(t for _, t in seen) == "hello\nab"
    assert out.writable() and not out.readable()
    with pytest.raises(io.UnsupportedOperation):
        out.read()
    with pytest.raises(io.UnsupportedOperation):
        out.fileno()


def test_input_reads_lines_until_eof():
    lines = iter(["first", "second"])

    def reader(prompt: str, password: bool) -> str:
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    stdin = InputStream(reader)
    assert list(stdin) == ["first\n", "second\n"]
    assert stdin.readline() == ""


def test_pdb_accepts_the_streams():
    captured = CapturingStream("stdout")
    debugger = pdb.Pdb(stdin=InputStream(lambda p, pw: "c"), stdout=captured)
    debugger.use_rawinput = False
    assert debugger.stdout is captured
