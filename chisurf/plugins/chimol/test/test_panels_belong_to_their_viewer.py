"""A panel registry belongs to a viewer, not to the process.

The reports, in order: "density: no such panel"; then, after the first fix,
"dbg: no such panel. Registered: settings. Plugins loaded: dbg, density,
hierarchy, history, labelling, scores, symmetry"; then "arch issue!".

All three are the same fault. Plugins are loaded **per viewer** -- ``register``
runs once per ``Cmd`` -- and they were registering into a table owned by the
*process*. Registration and lookup therefore had no shared owner, and anything
that ended one load's registrations emptied the table for every viewer: a
second window closing, a module reloaded under a running viewer, a teardown
that ran once too often. The second report is that state exactly: every plugin
loaded, and the registry holding nothing but the one panel registered at import
time.

Counting the owners was a patch on the same fault. The fix is ownership: the
registry is created by the ``Cmd``, filled by the core and by *that* viewer's
plugins, and collected with it. What this file pins is that property, in the
terms the bug appeared in -- because a property is checkable and a symptom is
only reproducible.
"""
from __future__ import annotations

import pytest

from chimol.commands.command import Cmd
from chimol.plugins import load_plugins
from chimol.testing.mock_viewer import MockViewer, MockWindow
from chimol.ui.panels import PanelRegistry, register_core


def _cmd(**kw) -> Cmd:
    return Cmd(MockWindow(MockViewer()), **kw)


class _Panelled:
    """A plugin whose whole job is to register one panel."""

    name = "panelled"

    def register(self, api):
        api.add_panel("panelled", lambda ctx: None, title="Panelled")


def test_there_is_no_process_wide_panel_registry():
    """The module global is gone; asking for it is the mistake this prevents."""
    import chimol.ui.panels as panels

    assert not hasattr(panels, "PANELS"), (
        "a module-global registry is back -- that is the fault this file is about"
    )
    assert hasattr(panels, "register_core")


def test_every_viewer_gets_its_own_registry_with_the_core_panels_in_it():
    first, second = _cmd(plugins=False), _cmd(plugins=False)
    assert first.panels is not second.panels
    assert "settings" in first.panels.keys() and "settings" in second.panels.keys()


def test_a_plugin_registers_into_the_viewer_it_was_loaded_on():
    first, second = _cmd(plugins=False), _cmd(plugins=False)
    load_plugins(first, [_Panelled()])
    assert "panelled" in first.panels.keys()
    assert "panelled" not in second.panels.keys(), (
        "a plugin loaded on one viewer registered into another's registry"
    )


def test_unloading_one_viewers_plugin_cannot_reach_another_viewer():
    """The reported bug, as an assertion."""
    first, second = _cmd(plugins=False), _cmd(plugins=False)
    loaded_first = load_plugins(first, [_Panelled()])
    load_plugins(second, [_Panelled()])

    loaded_first.unload("panelled")
    assert "panelled" not in first.panels.keys()
    assert "panelled" in second.panels.keys(), "the surviving viewer lost its panel"
    # ...and its command still opens it, which is what the user was doing.
    assert second.panels.specs["panelled"].factory is not None


def test_a_viewer_that_goes_away_takes_its_registry_with_it():
    """No teardown ordering to get wrong: the registry is the viewer's own."""
    import gc
    import weakref

    cmd = _cmd(plugins=False)
    load_plugins(cmd, [_Panelled()])
    ref = weakref.ref(cmd.panels)
    del cmd
    gc.collect()
    assert ref() is None, "the panel registry outlived its viewer"


def test_the_builtin_plugins_all_register_into_the_viewers_registry():
    """What the user typed: the panels their plugins say they registered are there."""
    cmd = _cmd()
    assert cmd.plugins is not None and cmd.plugins.failed == {}
    for name in ("dbg", "density", "hierarchy", "history", "scores"):
        assert name in cmd.panels.keys(), cmd.panels.why_not(name, cmd)
    # And the record agrees with the registry -- the check that named the fault
    # when it was still invisible.
    assert cmd.plugins.missing() == {}


@pytest.mark.parametrize("command,key", [
    ("dbg", "dbg"),
    ("density_panel", "density"),
    ("hierarchy_panel", "hierarchy"),
    ("history_panel", "history"),
    ("scores", "scores"),
    ("settings", "settings"),
])
def test_each_panel_command_finds_its_panel(command, key):
    """Not "no such panel": the command resolves to a registered key."""
    cmd = _cmd()
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do(command)
    assert not any("no such panel" in line for line in said), said
    assert key in cmd.panels.keys()


def test_register_core_is_what_puts_the_shipped_panels_in():
    registry = register_core(PanelRegistry())
    # Settings, and the section (clip) panel core gained with containers.
    assert registry.keys() == ["section", "settings"]
