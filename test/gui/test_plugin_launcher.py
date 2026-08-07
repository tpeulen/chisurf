"""A menu entry must open a window, and a manifest is how a plugin says which.

The launcher used to execute a plugin's ``wizard.py`` or ``__init__.py`` as a
macro, which is how the older plugins open themselves. Every plugin written to
the current standard ships a ``manifest.json`` naming a widget class instead, and
its ``__init__.py`` only imports and documents — so executing it did nothing at
all and the menu entry was dead. Silently, because the launcher swallows every
exception: no window, no error, nothing in the log.

These pin the contract from both ends: the launcher prefers the manifest, and
every shipped manifest's GUI entry point actually resolves to something callable.
"""

from __future__ import annotations

import importlib
import json
import pathlib

import pytest

pytest.importorskip("qtpy")

from qtpy import QtWidgets  # noqa: E402

PLUGINS = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "plugins"


class _FakeMainWindow:
    """Stands in for the main window: the launcher only stores things on it."""

    def __init__(self) -> None:
        self.macros: list[str] = []

    def onRunMacro(self, filename, executor="exec", globals=None):  # noqa: A002
        self.macros.append(str(filename))


def test_a_manifest_plugin_opens_its_declared_window(qapp, tmp_path, monkeypatch):
    """The regression: a manifest GUI entry point must be used, not the macro."""
    from chisurf.gui import misc_helpers

    plugin_dir = tmp_path / "demo_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text('"""Docstring only, like every current plugin."""\n')
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "demo_plugin",
                "version": "1.0.0",
                "display_name": "Demo",
                "entrypoints": {"gui": "test.gui.test_plugin_launcher:_DemoWindow"},
            }
        )
    )
    window = _FakeMainWindow()
    misc_helpers.run_plugin_from_dir(window, plugin_dir)

    assert window.macros == [], "the macro path must not run when a manifest declares a GUI"
    opened = getattr(window, "_plugin_windows", {})
    assert str(plugin_dir) in opened
    assert isinstance(opened[str(plugin_dir)], _DemoWindow)
    opened[str(plugin_dir)].close()


def test_a_legacy_plugin_still_runs_its_macro(qapp, tmp_path):
    """No manifest, no regression: the old path must be untouched."""
    from chisurf.gui import misc_helpers

    plugin_dir = tmp_path / "legacy_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text('name = "Legacy"\n')
    window = _FakeMainWindow()
    misc_helpers.run_plugin_from_dir(window, plugin_dir)
    assert window.macros == [str(plugin_dir / "__init__.py")]


def test_a_broken_entry_point_falls_back_rather_than_opening_nothing(qapp, tmp_path):
    """An unimportable class must not leave the user with a dead menu entry."""
    from chisurf.gui import misc_helpers

    plugin_dir = tmp_path / "broken_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text('name = "Broken"\n')
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "broken_plugin",
                "version": "1.0.0",
                "entrypoints": {"gui": "no.such.module:Nope"},
            }
        )
    )
    window = _FakeMainWindow()
    misc_helpers.run_plugin_from_dir(window, plugin_dir)
    assert window.macros == [str(plugin_dir / "__init__.py")]


def _gui_entrypoints() -> list[tuple[str, str]]:
    """Return ``(plugin id, entrypoint)`` for every shipped manifest with a GUI."""
    out = []
    for path in sorted(PLUGINS.rglob("manifest.json")):
        if "{{" in str(path):  # the cookiecutter template
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        entry = (data.get("entrypoints") or {}).get("gui")
        if entry:
            out.append((data.get("id", path.parent.name), entry))
    return out


@pytest.mark.parametrize("plugin_id,entry", _gui_entrypoints(), ids=lambda v: str(v)[:40])
def test_every_declared_gui_entry_point_resolves(plugin_id: str, entry: str):
    """A menu entry naming a class that is not there is a button that does nothing."""
    module_path, _, attr = entry.partition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.skip(f"{plugin_id}: optional dependency missing ({exc})")
    target = getattr(module, attr) if attr else module
    assert callable(target), f"{plugin_id}: {entry} is not callable"


class _DemoWindow(QtWidgets.QWidget):
    """A window the fake manifest above points at."""
