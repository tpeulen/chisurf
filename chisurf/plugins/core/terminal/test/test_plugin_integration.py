"""The whole terminal plugin against real PTYs and the shell's plugin host.

Three layers, each with its own concern:

* the **app** with real sessions (typing reaches the child; output is drawn;
  the exit is noticed);
* the **shell** hosting it as a core plugin (discovery from the manifest,
  ``open_plugin`` wiring, the dock window, close killing the sessions);
* the **manifest** conforming to the shipped-plugin rules (ids, entrypoints,
  the preview gate).
"""

from __future__ import annotations

import sys
import time

import pytest
from emtk.testing import Driver

pytest.importorskip("emtk")

from chisurf.plugins.core.terminal.app import TerminalApp
from chisurf.plugins.core.terminal.workspace import TerminalWorkspace


def _python_argv(code: str) -> list[str]:
    return [sys.executable, "-u", "-c", code]


def make_app(argv=None, size=(680, 420)):
    from chisurf.plugins.core.terminal.session import spawn

    argv = argv or _python_argv("print('pty-ok')\nimport sys; sys.stdin.read()")
    app = TerminalApp(session_factory=lambda: spawn(argv, columns=90, rows=26))
    return app, Driver(app, size)


def _pane_text(app) -> str:
    return "\n".join(
        app.workspace.panes[key].control.screen.line_text(i)
        for key in list(app.workspace.panes)[:1]
        for i in range(app.workspace.panes[key].control.screen.total_lines)
    )


# ── the app with real sessions ───────────────────────────────────────────


def test_a_real_pty_prints_into_the_pane():
    app, driver = make_app()
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and "pty-ok" not in _pane_text(app):
            driver.frame(1)
        assert "pty-ok" in _pane_text(app)
    finally:
        app.close()


def test_typing_reaches_the_real_child():
    app, driver = make_app(
        _python_argv("line = input(); print('echo:', line)\nimport sys; sys.stdin.read()")
    )
    try:
        # let the child start, then focus the pane and type
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not app.workspace.panes:
            driver.frame(1)
        control = app.workspace.panes[app.workspace.active_key].control
        driver.click((60, 200))  # into the pane: focus
        driver.type("hi\r")  # the CR ends input()'s line
        deadline = time.monotonic() + 10.0
        text = ""
        while time.monotonic() < deadline:
            driver.frame(2)
            text = _pane_text(app)
            if "echo: hi" in text:
                break
        assert "echo: hi" in text
        assert control.has_focus
    finally:
        app.close()


def test_close_kills_the_real_sessions():
    from chisurf.plugins.core.terminal.session import spawn

    app, _driver = make_app(
        _python_argv("import time; time.sleep(120)")
    )
    sessions = [pane.session for pane in app.workspace.panes.values()]
    app.close()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and any(s.alive for s in sessions):
        time.sleep(0.02)
    assert not any(s.alive for s in sessions)


# ── the workspace's layout against the dock manager ──────────────────────


def test_split_then_close_restores_a_single_region():
    from chisurf.plugins.core.terminal.session import spawn

    ws = TerminalWorkspace(
        session_factory=lambda: spawn(_python_argv("import time; time.sleep(60)"))
    )
    ws.new_pane()
    ws.split_active("right")
    keys = list(ws.panes)
    assert len({ws.docks.region_of(k) for k in keys}) == 2
    ws.close(keys[1])
    assert list(ws.docks.regions) == ["root"]  # the split region pruned
    ws.close_all()


# ── the shell hosts it like any core plugin ──────────────────────────────


def _make_shell(monkeypatch):
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.plugins import manifests

    catalog = manifests()
    assert "terminal" in catalog
    made = {}

    def loader(plugin_id):
        app = TerminalApp()
        made[plugin_id] = app
        return app

    shell = EmtkShellApp(catalog, loader=loader, console_history=False,
                         console_session_file=False)
    return shell, made


@pytest.mark.parametrize("mode", ["open_plugin"])
def test_the_shell_opens_the_terminal_plugin(mode):
    shell, made = None, {}
    try:
        shell, made = _make_shell(None)
        hosted = shell.open_plugin("terminal")
        assert hosted is not None
        # the app is built asynchronously; settle it
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and "terminal" not in made:
            time.sleep(0.05)
        assert "terminal" in made
        app = made["terminal"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not app.workspace.panes:
            time.sleep(0.05)
        assert app.workspace.panes  # a live pane
        driver = Driver(shell, (1440, 900))
        driver.frame(3)
        assert shell.hosted["terminal"].key in shell.docks.windows
    finally:
        if shell is not None:
            shell.close()


def test_the_menu_lists_the_terminal_tool():
    from chisurf.emtk.main_app import menu_entries
    from chisurf.emtk.plugins import manifests

    entries = {e.plugin_id: e for e in menu_entries(manifests())}
    assert "terminal" in entries
    entry = entries["terminal"]
    assert entry.path == ("Tools", "System", "Terminal")
    assert not entry.action  # it opens a window, it is not a command


def test_closing_the_plugin_kills_the_sessions(monkeypatch):
    shell, made = None, {}
    try:
        shell, made = _make_shell(monkeypatch)
        shell.open_plugin("terminal")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and "terminal" not in made:
            time.sleep(0.05)
        app = made["terminal"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not app.workspace.panes:
            time.sleep(0.05)
        sessions = [pane.session for pane in app.workspace.panes.values()]
        shell.close_plugin("terminal")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and any(s.alive for s in sessions):
            time.sleep(0.02)
        assert not any(s.alive for s in sessions)
    finally:
        if shell is not None:
            shell.close()


# ── the manifest ─────────────────────────────────────────────────────────


def test_the_manifest_declares_the_entrypoint():
    import json
    import pathlib

    manifest = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[1] / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["id"] == "terminal"
    assert manifest["entrypoints"]["emtk"].endswith(":make_app")
    assert manifest["display_name"].startswith("Tools:")
    assert "Thomas-Otavio Peulen" in manifest["authors"]


def test_the_plugin_is_not_a_preview():
    from chisurf.core.plugin import emtk_readiness

    assert not emtk_readiness.is_preview("terminal")


def test_the_native_factory_resolves():
    from chisurf.emtk.plugins import native_factory

    assert native_factory("terminal") == (
        "chisurf.plugins.core.terminal.app:make_app"
    )


def test_the_python_console_entrypoint_resolves_and_menus_list_it():
    import importlib

    from chisurf.emtk.main_app import menu_entries
    from chisurf.emtk.plugins import manifests, native_factory

    assert native_factory("python_terminal") == (
        "chisurf.plugins.core.terminal.app:make_console_app"
    )
    module, attribute = native_factory("python_terminal").split(":")
    factory = getattr(importlib.import_module(module), attribute)
    app = factory()
    try:
        pane = app.workspace.panes[app.workspace.active_key]
        assert pane.kind == "python"
    finally:
        app.close()
    entries = {e.plugin_id: e for e in menu_entries(manifests())}
    assert entries["python_terminal"].path == ("Tools", "System", "Python Terminal")
