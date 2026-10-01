"""The shared launcher must honour the EMTK/Qt runtime selection.

Three launch paths reach a plugin window: the registry menus
(``registry._show_plugin``), the menu/macro launcher
(``misc_helpers._show_manifest_gui``, via ``load_and_show_plugin``), and the
ribbon's plugin categories (which used to execute the plugin's ``__init__.py``
as a macro — its ``__name__ == "plugin"`` block instantiates the Qt widget
directly, bypassing any native factory). All three now dispatch through
:func:`chisurf.core.plugin.registry.build_plugin_widget`.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.gui import misc_helpers


def _manifest(root_name: str):
    from chisurf.core.plugin import load_manifest

    root = pathlib.Path(__file__).resolve().parents[5]
    return load_manifest(root / "chisurf" / "plugins" / root_name / "manifest.json")


def test_build_plugin_widget_prefers_emtk(qapp, qtbot):
    from emtk.qt_host import host_class

    from chisurf.core.plugin.registry import build_plugin_widget

    widget = build_plugin_widget(_manifest("modelling/structure_tools"))
    qtbot.addWidget(widget)
    assert isinstance(widget, host_class()), (
        "Structure Tools must open as an EMTK ControlHost, not the Qt widget"
    )


def test_build_plugin_widget_chimol(qapp, qtbot):
    from emtk.qt_host import host_class

    from chisurf.core.plugin.registry import build_plugin_widget

    widget = build_plugin_widget(_manifest("chimol"))
    qtbot.addWidget(widget)
    assert isinstance(widget, host_class())


def test_show_manifest_gui_routes_through_dispatch(qapp, qtbot, monkeypatch):
    """The menu/macro launcher opens the EMTK app for a native plugin."""
    import chisurf.core.plugin.registry as registry

    opened = {}

    class _Main:
        pass

    _Main._plugin_windows = {}

    real_build = registry.build_plugin_widget

    def _spy(manifest, widget_class=None):
        widget = real_build(manifest, widget_class)
        opened["kind"] = type(widget).__name__
        opened["title"] = widget.windowTitle()
        qtbot.addWidget(widget)
        # Do not actually raise a window in the test run.
        widget.show = lambda: None
        widget.raise_ = lambda: None
        widget.activateWindow = lambda: None
        return widget

    monkeypatch.setattr(registry, "build_plugin_widget", _spy)
    root = pathlib.Path(__file__).resolve().parents[5]
    shown = misc_helpers._show_manifest_gui(_Main(), root / "chisurf" / "plugins" / "modelling" / "structure_tools")
    assert shown
    assert "ControlHost" in opened["kind"], opened
    assert "Structure Tools" in opened["title"]


def test_ribbon_callback_targets_the_launcher():
    """The ribbon's plugin callbacks call load_and_show_plugin, not onRunMacro."""
    source = pathlib.Path(__file__).resolve().parents[5] / "chisurf" / "gui" / "widgets" / "ribbon" / "ribbon_categories.py"
    text = source.read_text()
    assert "load_and_show_plugin" in text
    assert 'globals={"__name__": "plugin"}' not in text, (
        "ribbon plugin entries must not execute plugin files as macros"
    )


@pytest.mark.parametrize("root_name", ["modelling/structure_tools", "chimol", "modelling/hydropro"])
def test_runtime_selection_defaults_to_emtk(root_name):
    from chisurf.core.plugin.registry import select_gui_entrypoint

    selected = select_gui_entrypoint(_manifest(root_name), "auto")
    assert selected == ("emtk", selected[1])
    assert selected[1]
