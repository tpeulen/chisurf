"""The PTY session engine, driven by a real forked process.

Each test spawns one small program on a real pseudo-terminal and asserts on
what comes back. POSIX only (macOS and Linux); the tests skip elsewhere.
"""

from __future__ import annotations

import sys
import time

import pytest

pytest.importorskip("pty")

from chisurf.plugins.core.terminal.session import PtySession, spawn  # noqa: E402


def drain(session: PtySession, want: str, timeout: float = 10.0) -> str:
    """Read until *want* appeared in the session's screen, or time out."""
    end = time.monotonic() + timeout
    seen = ""
    while time.monotonic() < end:
        seen = "\n".join(session.screen.line_text(i) for i in range(session.screen.total_lines))
        if want in seen:
            return seen
        time.sleep(0.01)
    raise AssertionError(f"{want!r} never appeared; screen:\n{seen}")


def test_spawn_runs_the_command_and_produces_output():
    session = spawn([sys.executable, "-c", "print('hello-terminal')"])
    try:
        assert drain(session, "hello-terminal")
        assert session.alive
    finally:
        session.close()


def test_write_reaches_the_child():
    session = spawn([sys.executable, "-u", "-c", "line = input(); print('got', line)"])
    try:
        drain(session, "")  # let it start
        session.write(b"ping\r")
        assert drain(session, "got ping")
    finally:
        session.close()


def test_close_terminates_the_child():
    session = spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    session.close()
    end = time.monotonic() + 5.0
    while session.alive and time.monotonic() < end:
        time.sleep(0.02)
    assert not session.alive


def test_resize_updates_the_screen_geometry():
    session = spawn([sys.executable, "-c", "print('r')"], columns=40, rows=10)
    try:
        drain(session, "r")
        session.resize(100, 30)
        assert session.screen.columns == 100
        assert session.screen.rows == 30
    finally:
        session.close()


def test_exit_status_is_collected():
    session = spawn([sys.executable, "-c", "raise SystemExit(3)"])
    session.wait(timeout=10.0)
    assert session.exit_status == 3
    assert not session.alive
    session.close()


def test_wait_blocks_until_the_child_exits():
    session = spawn([sys.executable, "-c", "print('bye')"])
    try:
        session.wait(timeout=10.0)
        assert not session.alive
        assert drain(session, "bye")
    finally:
        session.close()
