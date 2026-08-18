"""Nerd mode belongs to the viewer you switched it on in, not to the disk.

The report was "now stats for nerds is always on. nerd mode on/off not
working", and the cause was in the user's settings file: ``layout.nerd: true``.
The switch wrote itself into the persisted display config and the renderer
re-read it into ``gui.nerd`` on every frame, so switching it on made it a
property of the *installation* -- on at the next launch, and the one after --
while the "off" that had just been typed applied only until the next start.
Nothing about the readout is a preference: it is an instrument you switch on to
look at one slow frame.

So the state is the chrome's (``InternalGui.nerd``), the command sets it on the
viewer it was typed into, and it is listed in ``BASELINE_FIELDS`` so ``reinit``
clears it with the rest of the session. What that buys, and what is pinned
here: a stale flag on disk no longer forces it on, the switch is symmetric, a
second viewer does not inherit it, and nothing is written to the user's
settings by switching an instrument on.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from types import SimpleNamespace

from chimol.commands.command import Cmd
from chimol.testing.mock_viewer import MockViewer, MockWindow
from chimol.ui.gui import InternalGui


def _cmd() -> Cmd:
    """A viewer with a real chrome behind it -- the chrome is what owns the flag."""
    viewer = MockViewer()
    viewer.renderer = SimpleNamespace(_internal_gui=InternalGui())
    return Cmd(MockWindow(viewer))


def test_the_flag_is_part_of_the_sessions_baseline():
    """Which is what makes `reinit` put it back to off."""
    assert "nerd" in InternalGui.BASELINE_FIELDS


def test_the_renderer_does_not_re_read_it_from_the_settings():
    """The line that made a session switch into a saved preference."""
    import inspect

    from chimol.viewport.canvas import CanvasRenderer

    source = inspect.getsource(CanvasRenderer._publish_nerd)
    assert '_layout_flag("nerd"' not in source, (
        "the readout is being re-read from the display config again"
    )


def test_the_command_does_not_write_to_the_users_settings(tmp_path, monkeypatch):
    import inspect

    from chimol.plugins.dbg.commands import DbgCommands

    source = inspect.getsource(DbgCommands.nerd_mode)
    assert "save_user_display_config" not in source, (
        "switching an instrument on writes to the user's settings again"
    )


def test_switching_it_on_and_off_is_symmetric():
    cmd = _cmd()
    gui = cmd.window.viewer.gui
    assert not gui.nerd
    cmd.do("nerd on")
    assert gui.nerd
    cmd.do("nerd off")
    assert not gui.nerd
    cmd.do("nerd")            # no argument toggles
    assert gui.nerd
    cmd.do("nerd")
    assert not gui.nerd


def test_switching_it_off_takes_the_published_readout_with_it():
    cmd = _cmd()
    gui = cmd.window.viewer.gui
    cmd.do("nerd on")
    gui.nerd_lines = ("  30.0 fps   frame  33.3 ms",)
    gui.nerd_graphs = (object(),)
    cmd.do("nerd off")
    assert gui.nerd_lines == () and gui.nerd_graphs == ()


def test_a_second_viewer_does_not_inherit_it():
    """A process-wide setting made this impossible; ownership makes it free."""
    first, second = _cmd(), _cmd()
    first.do("nerd on")
    assert first.window.viewer.gui.nerd
    assert not second.window.viewer.gui.nerd, (
        "switching the readout on in one viewer switched it on in another"
    )


def test_a_flag_left_in_an_old_settings_file_is_not_read(tmp_path, monkeypatch):
    """The user's own file still says ``layout.nerd: true``; it must not matter."""
    from chimol.core.settings import config

    monkeypatch.setitem(config._DISPLAY_CONFIG.setdefault("layout", {}), "nerd", True)
    cmd = _cmd()
    assert not cmd.window.viewer.gui.nerd, (
        "a leftover saved flag switches the readout on again"
    )


def test_reinit_puts_it_back_to_off():
    cmd = _cmd()
    gui = cmd.window.viewer.gui
    gui._baseline = gui.capture_baseline()      # taken on the first paint
    cmd.do("nerd on")
    assert gui.nerd
    gui.reset_session()
    assert not gui.nerd, "reinit left the instrument running"
