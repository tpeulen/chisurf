"""When something is missing, the viewer says *why* -- not just "no such panel".

The reports that prompted this were "density: no such panel", then "dbg: no
such panel, many issues, seems like tests do not catch issues". Both are true
and neither could be reproduced here: the Qt dock, the toolkit-free window and
the page all open both panels, by command and by menu click. That is exactly
when a message has to carry its own diagnosis -- a report from a session I
cannot reproduce is only as good as what the session was able to say.

So two things are pinned here:

* ``cmd.panels.toggle`` on an unknown key answers with what *is* registered, which
  plugins loaded, and which failed **with the reason**. Three sentences that
  distinguish "the plugin crashed on import", "``CHIMOL_PLUGINS`` filtered it
  out" and "nothing loaded at all", which are the three causes there have ever
  been;
* ``doctor`` prints the whole picture in one paste-able block: which chimol,
  which host, whether there is a chrome, the plugins (loaded, failed, and how
  many viewers hold each), the registries, the open windows, the objects and
  the movie clock.
"""
from __future__ import annotations

import pytest

from chimol.commands.command import Cmd
from chimol.plugins import load_plugins
from chimol.testing.mock_viewer import MockViewer, MockWindow


def _cmd(**kw) -> Cmd:
    return Cmd(MockWindow(MockViewer()), **kw)


def _lines(cmd) -> list[str]:
    out: list[str] = []
    cmd.set_message_callback(out.append)
    cmd.set_error_callback(out.append)
    return out


def test_an_unknown_panel_says_what_is_registered():
    cmd = _cmd()
    said = _lines(cmd)
    cmd.do("nonesuch_panel")          # not a command at all
    said.clear()
    cmd.panels.toggle(cmd, "nonesuch")
    message = " ".join(said)
    assert "no such panel" in message
    assert "Registered:" in message and "settings" in message
    assert "Plugins loaded:" in message


def test_a_plugin_that_failed_is_named_as_the_reason():
    """The case that matters: the panel is missing *because* its plugin broke."""

    class _Broken:
        name = "broken"

        def register(self, api):
            raise RuntimeError("no numpy for you")

    cmd = _cmd(plugins=False)
    cmd.plugins = load_plugins(cmd, [_Broken()])
    said = _lines(cmd)
    cmd.panels.toggle(cmd, "broken")
    message = " ".join(said)
    assert "broken" in message and "no numpy for you" in message
    assert "That is why" in message


def test_a_command_object_with_no_plugins_says_so():
    """`Cmd(plugins=False)` is a bare command object -- a test's, or a broken load."""
    cmd = _cmd(plugins=False)
    said = _lines(cmd)
    cmd.panels.toggle(cmd, "not_a_panel_anyone_registered")
    assert "carries no plugins" in " ".join(said)


def test_doctor_prints_what_a_report_needs():
    cmd = _cmd()
    said = _lines(cmd)
    cmd.do("doctor")
    block = "\n".join(said)
    for expected in ("chimol", "host:", "chrome:", "settings:", "plugins:",
                     "panels:", "commands:", "menus:"):
        assert expected in block, f"doctor said nothing about {expected!r}:\n{block}"
    # The plugins line carries how many viewers hold each one -- the number
    # that made "a window closing took another window's panels" visible.
    assert "density(" in block


def test_doctor_reports_a_failed_plugin_too():
    class _Broken:
        name = "broken"

        def register(self, api):
            raise RuntimeError("boom")

    cmd = _cmd(plugins=False)
    cmd.plugins = load_plugins(cmd, [_Broken()])
    said = _lines(cmd)
    cmd.do("doctor")
    assert any("FAILED broken" in line and "boom" in line for line in said), said


@pytest.mark.parametrize("name", ["density", "dbg", "hierarchy", "history", "scores"])
def test_every_builtin_plugin_panel_opens_on_a_viewer_with_a_chrome(name):
    """The reported failures, as an assertion: each panel opens from its command.

    A ``MockViewer`` has no chrome, so this is the registry half -- the panel is
    registered and its factory is reachable. `test_session_reset_asks_the_owners`
    and the browser suite cover the drawing half on real chromes.
    """
    cmd = _cmd()
    assert name in cmd.panels.keys(), f"{name} did not register: {cmd.panels.why_not(name, cmd)}"
    assert cmd.panels.specs[name].factory is not None
