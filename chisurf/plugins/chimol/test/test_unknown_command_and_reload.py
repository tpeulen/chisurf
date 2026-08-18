"""A command a session does not have, and how it gets one.

The report was "Command 'fps_circle' is not implemented in Moview/Viewer cmd
(PyMOL compatibility layer)" -- about a command that *is* implemented, in a
plugin, in the file on disk. The session had been running since before it was
added, and neither the message nor `plugins reload` could get to it: the
message said only that the name was unknown, and reload re-registered the
plugin modules that were already imported rather than re-importing them.

Both halves are fixed here, and both are worth pinning:

* the message names near misses and says that plugins can be reloaded, which is
  the answer whenever chimol has been updated under a running session;
* `plugins reload` re-imports the shipped plugin packages, so it means what it
  says -- new code, not the same code registered twice.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from chimol.commands.command import Cmd
from chimol.testing.mock_viewer import MockViewer, MockWindow


def _cmd() -> Cmd:
    return Cmd(MockWindow(MockViewer()))


def _error(cmd, line: str) -> str:
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do(line)
    return said[0] if said else ""


def test_an_unknown_name_suggests_the_one_that_was_meant():
    message = _error(_cmd(), "fps_cirlce")
    assert "not implemented" in message
    assert "fps_circle" in message, message


def test_it_says_plugins_can_be_reloaded():
    """The answer when the session is older than the code."""
    message = _error(_cmd(), "zzzz_not_a_command")
    assert "plugins reload" in message
    assert "labelling" in message, "the message does not say what is loaded"


def test_a_command_that_exists_is_not_reported_as_missing():
    cmd = _cmd()
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do("fps_circle")
    assert not any("not implemented" in line for line in said), said


def test_reload_re_imports_the_shipped_plugins(tmp_path):
    """Not "register the same modules again": *new code* has to take effect.

    Written by changing a shipped plugin module on disk and asking for the new
    attribute back -- the only check that distinguishes a reload from a
    re-registration. The file is restored whatever happens.
    """
    import chimol.plugins.dbg.commands as module

    source = pathlib.Path(module.__file__)
    original = source.read_text()
    cmd = _cmd()
    assert getattr(module, "_RELOAD_PROBE", None) is None
    try:
        source.write_text(original + '\n\n_RELOAD_PROBE = "new"\n')
        cmd.do("plugins reload")
        again = sys.modules["chimol.plugins.dbg.commands"]
        assert getattr(again, "_RELOAD_PROBE", None) == "new", (
            "`plugins reload` re-registered the plugin without re-importing it"
        )
    finally:
        source.write_text(original)
        cmd.do("plugins reload")            # put the module back as it was


def test_reload_leaves_the_commands_and_panels_working():
    cmd = _cmd()
    cmd.do("plugins reload")
    for name in ("fps_circle", "dbg", "density_panel", "add_dye"):
        assert cmd._registry.resolve(name) is not None, name
    for key in ("fps_circle", "dbg", "density", "hierarchy"):
        assert key in cmd.panels.keys(), cmd.panels.why_not(key, cmd)


def test_reload_does_not_multiply_the_registrations():
    """Reloading twice must not leave two of everything behind it."""
    cmd = _cmd()
    before = len(cmd._registry.names())
    cmd.do("plugins reload")
    cmd.do("plugins reload")
    assert len(cmd._registry.names()) == before
