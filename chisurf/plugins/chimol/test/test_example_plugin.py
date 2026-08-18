"""The shipped example plugin (examples/chimol_stars_plugin) exercises the whole PluginAPI.

Loaded from its source directory -- the way `pip install -e` would make it
importable -- and through a fake entry point, the way an installed one is
found. If this breaks, the example a plugin author copies is broken.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

import numpy as np
import pytest

import chimol
from chimol.plugins import discover_entry_points, load_plugins

_EXAMPLE = pathlib.Path(chimol.__file__).resolve().parents[1] / "examples" / "chimol_stars_plugin"


@pytest.fixture
def stars_module(monkeypatch):
    monkeypatch.syspath_prepend(str(_EXAMPLE))
    sys.modules.pop("chimol_stars", None)
    return importlib.import_module("chimol_stars")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_example_plugin_does_everything_it_says(stars_module, qapp, tmp_path):
    from chimol.ui.input import keybindings
    from chimol.ui.menus import bar as menus
    from chimol.commands.command import Cmd
    from chimol.core.services.representations import REPRESENTATIONS
    from chimol.core.settings.registry import get_setting
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.io.registry import FORMATS
    from chimol.viewport.headless import SceneSink

    viewer = Viewer(renderer_factory=SceneSink)
    host = ViewerHost(viewer)
    cmd = Cmd(None, plugins=False)
    host.cmd = cmd
    cmd.set_window(host)
    errors: list[str] = []
    said: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.set_message_callback(said.append)

    plugin = stars_module.StarsPlugin()
    loaded = load_plugins(cmd, [plugin])
    try:
        assert "stars" in loaded and loaded.failed == {}
        assert "stars" in REPRESENTATIONS and "stars" in cmd.panels.keys()
        assert FORMATS.kind_of("a.xyzs") == "structure"
        assert get_setting("star_size") == 0.3
        assert keybindings.action_for_key("j") == "stars_toggle"
        assert any(e.label == "Stars: count" for e in dict(menus.menu_bar())["Tools"])

        f = tmp_path / "four.xyzs"
        f.write_text("0 0 0\n2 0 0\n0 2 0\n0 0 2\n")
        cmd.do(f'load "{f}"')
        cmd.do("show stars")
        cmd.do("set star_size, 0.5")
        cmd.do("star_count")
        assert errors == [], errors
        assert said[-1] == "stars on 1 object(s)"
        stars = [o for o in viewer._scene.objects if "stars" in str(o.id)]
        assert stars and stars[0].geometry.positions.shape[0] == 4
        assert float(stars[0].geometry.radii[0]) == pytest.approx(0.5)
        assert plugin.commands_seen >= 4
    finally:
        loaded.unload("stars")
    assert "stars" not in REPRESENTATIONS and FORMATS.kind_of("a.xyzs") is None
    assert keybindings.action_for_key("j") is None


def test_the_example_plugin_is_found_through_an_entry_point(stars_module, monkeypatch):
    """A fake distribution's entry point in the chimol.plugins group is loaded."""
    import importlib.metadata as md

    class _EP:
        name = "stars"
        value = "chimol_stars:plugin"
        group = "chimol.plugins"

        def load(self):
            return stars_module.plugin

    real = md.entry_points

    def fake(group=None, **kw):
        if group == "chimol.plugins":
            return [_EP()]
        return real(group=group, **kw) if group else real(**kw)

    monkeypatch.setattr(md, "entry_points", fake)
    found = discover_entry_points()
    assert any(p is stars_module.plugin for _ref, p in found)


def test_a_folder_dropped_into_the_user_plugin_dir_loads_without_installing(tmp_path, monkeypatch):
    """No pip, no entry point: copy the folder in, start chimol (or `plugins reload`)."""
    import shutil

    from chimol.commands.command import Cmd
    from chimol.plugins import discover_dropins, plugin_dirs

    dropin = tmp_path / "plugins"
    dropin.mkdir()
    shutil.copytree(_EXAMPLE / "chimol_stars", dropin / "stars_dropin")
    (dropin / "stars_dropin" / "manifest.json").write_text('{"name": "stars", "description": "dropped in"}')
    # a single-file plugin with a bare register(api) counts too
    (dropin / "hello.py").write_text(
        "from chimol.commands.registry import command, CommandGroup\n"
        "class G(CommandGroup):\n"
        "    @command('hello_dropin')\n"
        "    def hello_dropin(self):\n"
        "        self._emit_message('hi')\n"
        "def register(api):\n"
        "    api.add_group(G)\n"
    )
    # and a disabled one is left alone
    (dropin / "off").mkdir()
    (dropin / "off" / "__init__.py").write_text("plugin = None\nraise RuntimeError('must not import')\n")
    (dropin / "off" / "manifest.json").write_text('{"disabled": true}')

    monkeypatch.setenv("CHIMOL_PLUGIN_DIRS", str(dropin))
    assert plugin_dirs()[0] == dropin
    found = {getattr(p, "name", "?") for _path, p in discover_dropins()}
    assert {"stars", "hello"} <= found and "off" not in found

    cmd = Cmd(None)                        # the default load: built-ins + drop-ins
    try:
        assert "stars" in cmd.plugins and "hello" in cmd.plugins
        assert cmd.plugins.loaded["stars"].source == "drop-in"
        assert cmd._registry.resolve("hello_dropin") is not None
        assert cmd._registry.resolve("star_count") is not None
        # edit the drop-in and reload without a restart
        (dropin / "hello.py").write_text(
            "from chimol.commands.registry import command, CommandGroup\n"
            "class G(CommandGroup):\n"
            "    @command('hello_again')\n"
            "    def hello_again(self):\n"
            "        self._emit_message('hi')\n"
            "def register(api):\n"
            "    api.add_group(G)\n"
        )
        said: list[str] = []
        cmd.set_message_callback(said.append)
        cmd.do("plugins reload")
        assert cmd._registry.resolve("hello_again") is not None
        assert cmd._registry.resolve("hello_dropin") is None
        cmd.do("plugins")
        assert any("drop-in" in line for line in said)
    finally:
        cmd.plugins.unload_all()
