"""The plugin system: discovery, registration, teardown, and the browser zip.

A plugin adds commands, menu rows and panels through ``PluginAPI`` and
nothing else; the in-tree plugins are ordinary plugins. What is pinned:

* a fresh ``Cmd`` carries every ``BUILTIN`` plugin, and one command per
  plugin resolves;
* ``Cmd(plugins=False)`` carries none -- a bare command object for tests;
* a plugin's registrations are reversed by ``unload``; a plugin registered on
  a second command object does not double its menu rows;
* the registry keeps the *first* owner of a name (core outranks a plugin);
* ``CHIMOL_PLUGINS=none`` loads nothing; a name list loads only those;
* the browser zip ships every ``BUILTIN`` package and no ``hosts/qt``.
"""
from __future__ import annotations

import pathlib
import zipfile

import pytest

import chimol
from chimol.chrome import menus
from chimol.chrome.panels import PANELS
from chimol.commands.command import Cmd, DEFAULT_GROUPS, compose
from chimol.commands.registry import CommandGroup, command
from chimol.plugins import BUILTIN, PluginAPI, load_plugins
from chimol.testing.mock_viewer import MockViewer, MockWindow

ONE_COMMAND_PER_PLUGIN = {
    "labelling": "add_dye",
    "symmetry": "symexp",
    "density": "density_panel",
    "hierarchy": "hierarchy_panel",
    "history": "history_panel",
    "dbg": "dbg",
}


def _cmd(**kw) -> Cmd:
    return Cmd(MockWindow(MockViewer()), **kw)


def test_a_fresh_cmd_carries_every_builtin_plugin():
    cmd = _cmd()
    assert set(cmd.plugins.names()) == set(ONE_COMMAND_PER_PLUGIN)
    assert cmd.plugins.failed == {}
    for plugin, name in ONE_COMMAND_PER_PLUGIN.items():
        spec = cmd._registry.resolve(name)
        assert spec is not None, f"{plugin}: {name} did not register"
        # the command reaches the plugin's group, and is callable as an attribute
        assert isinstance(spec.func.__self__, CommandGroup)
        assert getattr(cmd, name) is spec.func


def test_builtin_names_match_the_packages():
    for ref in BUILTIN:
        module, _, attr = ref.partition(":")
        assert module.startswith("chimol.plugins.")
        assert attr == "plugin"


def test_a_bare_cmd_has_no_plugin_commands():
    cmd = _cmd(plugins=False)
    assert cmd.plugins is None
    for name in ONE_COMMAND_PER_PLUGIN.values():
        assert cmd._registry.resolve(name) is None
    with pytest.raises(AttributeError):
        cmd.add_dye  # noqa: B018
    # the core groups are still all there
    assert cmd._registry.resolve("load") is not None
    assert len(DEFAULT_GROUPS) == 14


class _Greeting(CommandGroup):
    @command("greet", aliases=("hello",))
    def greet(self, who: str = "world") -> None:
        """Say hello (a test command)."""
        self._emit_message(f"hello {who}")

    @command("load")   # clashes with core: must lose
    def load(self, *_a) -> None:
        raise AssertionError("a plugin must not shadow a core command")


class _FakePlugin:
    name = "fake"

    def __init__(self):
        self.opened = 0

    def register(self, api: PluginAPI) -> None:
        api.add_group(_Greeting)
        api.add_menu("Tools", [("Greet", "greet")])
        api.add_panel("fake", self._make, title="Fake")

    def _make(self, ctx):
        self.opened += 1
        raise RuntimeError("no chrome in this test")


def test_a_plugin_registers_and_unloads_cleanly():
    cmd = _cmd(plugins=False)
    got: list[str] = []
    cmd.set_message_callback(got.append)
    plugin = _FakePlugin()
    loaded = load_plugins(cmd, [plugin])
    assert "fake" in loaded
    assert cmd._registry.resolve("hello").name == "greet"
    cmd.do("greet chimol")
    assert got[-1] == "hello chimol"
    # first owner keeps a name: core `load` is untouched
    assert cmd._registry.resolve("load").func.__self__ is cmd
    # the menu row and the panel are there
    tools = dict(menus.menu_bar())["Tools"]
    assert any(e.label == "Greet" and e.command == "greet" for e in tools)
    assert "fake" in PANELS.keys()
    # a second command object registering the same plugin does not double the row
    cmd2 = _cmd(plugins=False)
    load_plugins(cmd2, [plugin])
    tools = dict(menus.menu_bar())["Tools"]
    assert sum(1 for e in tools if e.label == "Greet") == 1
    # unload reverses it
    loaded.unload("fake")
    assert cmd._registry.resolve("greet") is None
    assert cmd._registry.resolve("hello") is None
    assert "fake" not in PANELS.keys()
    assert not any(e.label == "Greet" for e in dict(menus.menu_bar())["Tools"])
    # a name resolves by unique prefix again once the plugin is gone
    assert "greet" not in cmd.command_names()


def test_a_failing_plugin_is_rolled_back_not_fatal(caplog):
    class _Bad:
        name = "bad"

        def register(self, api):
            api.add_group(_Greeting)
            raise ValueError("boom")

    cmd = _cmd(plugins=False)
    loaded = load_plugins(cmd, [_Bad()])
    assert "bad" not in loaded
    assert loaded.failed["bad"].startswith("ValueError")
    assert cmd._registry.resolve("greet") is None


def test_chimol_plugins_env_filters(monkeypatch):
    monkeypatch.setenv("CHIMOL_PLUGINS", "none")
    assert _cmd().plugins.names() == []
    monkeypatch.setenv("CHIMOL_PLUGINS", "symmetry,history")
    cmd = _cmd()
    assert set(cmd.plugins.names()) == {"symmetry", "history"}
    assert cmd._registry.resolve("symexp") is not None
    assert cmd._registry.resolve("add_dye") is None


def test_compose_builds_a_smaller_cmd():
    Small = compose(DEFAULT_GROUPS[:2], name="SmallCmd")
    cmd = Small(MockWindow(MockViewer()), plugins=False)
    assert cmd._registry.resolve("load") is not None
    assert cmd._registry.resolve("ray") is None


@pytest.mark.slow
def test_the_browser_zip_ships_the_builtin_plugins_and_no_qt(tmp_path):
    from chimol.hosts.web import serve

    archive = serve.pack(tmp_path / "chimol.zip")
    names = zipfile.ZipFile(archive).namelist()
    for ref in BUILTIN:
        pkg = ref.partition(":")[0].replace(".", "/")
        assert f"{pkg}/__init__.py" in names, f"{pkg} is not in the zip"
    assert not [n for n in names if n.startswith("chimol/hosts/qt/")]
    assert not [n for n in names if n.startswith("chimol/hosts/native/")]
    assert "chimol/plugins/api.py" in names


class _KeysAndSettingsPlugin:
    name = "ks"

    def register(self, api):
        assert api.add_setting("stars_size", path="stars.size", kind="float", default=0.3, doc="star radius")
        assert api.add_keybinding("stars_toggle", "j", "toggle_rep stars", label="Toggle the stars")


def test_a_plugin_adds_a_setting_and_a_keybinding():
    from chimol.chrome import keybindings
    from chimol.core.settings import registry as settings

    cmd = _cmd(plugins=False)
    loaded = load_plugins(cmd, [_KeysAndSettingsPlugin()])
    try:
        assert settings.get_setting("stars_size") == 0.3
        cmd.do("set stars_size, 0.5")
        assert settings.get_setting("stars_size") == 0.5
        cmd.do("unset stars_size")
        assert settings.get_setting("stars_size") == 0.3
        assert keybindings.action_for_key("j") == "stars_toggle"
        assert keybindings.command_for("stars_toggle") == "toggle_rep stars"
        assert any(b.action == "stars_toggle" for b in keybindings.bindings())
    finally:
        loaded.unload("ks")
    assert keybindings.action_for_key("j") is None
    with pytest.raises(settings.UnknownSettingError):
        settings.resolve("stars_size")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_a_plugin_hears_the_viewer_through_the_bus(qapp):
    """objects.changed and command.executed reach a subscriber; unload cancels it."""
    from chimol.core.viewer import MolView

    viewer = MolView()
    heard: list[tuple[str, object]] = []

    class _Ears:
        name = "ears"

        def register(self, api):
            api.on("objects.changed", lambda c: heard.append(("objects", c.kind)))
            api.on("command.executed", lambda line: heard.append(("cmd", line)))

    try:
        cmd = Cmd(MockWindow(viewer), plugins=False)
        loaded = load_plugins(cmd, [_Ears()])
        assert viewer.bus.count("objects.changed") == 1
        viewer.objects.touch("touch", "", "probe")
        cmd.do("bg_color white")
        assert ("objects", "touch") in heard
        assert ("cmd", "bg_color white") in heard
        loaded.unload("ears")
        assert viewer.bus.count("objects.changed") == 0
    finally:
        viewer.deleteLater()


def test_a_plugin_adds_a_wizard_and_a_menu_generator():
    from chimol.chrome import menus
    from chimol.chrome.object_menus import MenuEntry
    from chimol.chrome.wizards import WIZARDS, Wizard

    class _Hello(Wizard):
        name = "hello"
        title = "Hello"

    class _P:
        name = "gen"

        def register(self, api):
            assert api.add_wizard("hello", _Hello, aliases=("hi",))
            assert api.add_menu_generator("greetings", lambda: (MenuEntry("Say hi", "wizard hello"),))
            api.add_menu("Tools", [{"generate": "greetings"}])

    cmd = _cmd(plugins=False)
    loaded = load_plugins(cmd, [_P()])
    try:
        assert "hello" in WIZARDS and "hi" in WIZARDS
        assert isinstance(WIZARDS.create("hi"), _Hello)
        tools = dict(menus.menu_bar())["Tools"]
        assert any(e.label == "Say hi" and e.command == "wizard hello" for e in tools)
    finally:
        loaded.unload("gen")
    assert "hello" not in WIZARDS
    assert not any(e.label == "Say hi" for e in dict(menus.menu_bar())["Tools"])
