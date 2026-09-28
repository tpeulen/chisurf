"""The menu and the ribbon open the same ndX window: the emtk app in a Qt host.

The menu opens ndX through the manifest's ``entrypoints.gui``; the ribbon
executes the plugin's ``__init__.py``. They used to build different Qt windows,
and then both built the legacy Qt window while the emtk app was finished. Both
now call :func:`~chisurf.plugins.ndxplorer.window.build_ndxplorer_window`, which
hosts :class:`ndxplorer.app.frame.NdxApp` in a ``ChisurfDockTool``.
"""

from __future__ import annotations

import os
import pathlib
import types

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    """The QApplication every window here needs."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def _scratch_settings(tmp_path, monkeypatch):
    """ndX's settings folder (dock layout, session store) is a scratch one."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))


def _open_from_menu():
    """Open ndX the way the menu does: through the manifest's GUI entry point."""
    from chisurf.gui import misc_helpers

    main_window = types.SimpleNamespace()
    assert misc_helpers._show_manifest_gui(main_window, PLUGIN_DIR)
    return main_window._plugin_windows[str(PLUGIN_DIR)]


def _open_from_ribbon():
    """Open ndX the way the ribbon's fallback does: execute ``__init__.py`` as ``plugin``."""
    from chisurf.gui import misc_helpers

    context = {"__name__": "plugin"}
    misc_helpers.run_macro(
        filename=str(PLUGIN_DIR / "__init__.py"),
        executor="exec",
        globals=context,
        main_window=None,
    )
    return context["ndx"]


def test_menu_and_ribbon_host_the_emtk_app(qapp):
    """Both routes give an ``NdxWindow`` around an ``NdxApp`` with ChiSurf's client."""
    from emtk.qt_host import host_class
    from ndxplorer.app.frame import NdxApp
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.window import NdxWindow, _constants_group, published_group

    for route, opener in (("menu", _open_from_menu), ("ribbon", _open_from_ribbon)):
        window = opener()
        try:
            # By name: the ribbon's macro runner reloads the plugin's modules.
            assert type(window).__name__ == NdxWindow.__name__, route
            assert isinstance(window.app, NdxApp), route
            assert isinstance(window.centralWidget(), host_class()), route
            assert window.app.chisurf_rpc is not None, f"{route}: no ChiSurf RPC client"
            assert window.app.session_autosave, f"{route}: the user's window keeps sessions"
            window.host.grab()  # one frame, as on screen
            group = _constants_group(window.app)
            assert group is not None
            # The app's own constants, through their one mirror -- not a copy.
            assert published_group() is not None, f"{route}: no Global View binding"
            assert published_group() is chisurf_group(group), route
        finally:
            window.close()
        assert published_group() is None, f"{route}: the closed window is still published"


def test_a_second_window_keeps_the_slot_when_the_first_closes(qapp):
    """Closing an older window does not withdraw a newer window's constants."""
    from ndxplorer.core.chisurf_binding import chisurf_group

    from chisurf.plugins.ndxplorer.window import (
        _constants_group,
        build_ndxplorer_window,
        published_group,
    )

    first = build_ndxplorer_window(session_autosave=False, layout_store=None)
    second = build_ndxplorer_window(session_autosave=False, layout_store=None)
    try:
        first.close()
        assert published_group() is not None
        assert published_group() is chisurf_group(_constants_group(second.app))
    finally:
        second.close()
    assert published_group() is None


def test_the_manifest_points_at_the_single_construction():
    """The manifest's GUI entry point is the function the ribbon calls."""
    from chisurf.core.plugin.manifest import load_manifest

    manifest = load_manifest(PLUGIN_DIR / "manifest.json")
    assert manifest.entrypoints.gui == "chisurf.plugins.ndxplorer.window:build_ndxplorer_window"
    assert "build_ndxplorer_window()" in (PLUGIN_DIR / "__init__.py").read_text()


def test_a_table_handed_over_is_shown(qapp):
    """A tool that computed bursts hands the table over; the app shows it."""
    from ndxplorer.core.data_source import DataSource

    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    source = DataSource.from_columns({"I_DD": [10.0, 20.0, 30.0], "I_DA": [4.0, 8.0, 3.0]})
    window = build_ndxplorer_window(
        data_source=source, session_autosave=False, layout_store=None
    )
    try:
        assert window.app.model.has_data
        assert window.app.model.source.size == 3
    finally:
        window.close()
