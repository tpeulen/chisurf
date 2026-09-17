"""Tests for the plot settings plugin."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.gui

pytest.importorskip("qtpy")

from qtpy import QtWidgets  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_manifest_loads():
    from pathlib import Path

    from chisurf.core.plugin import load_manifest

    m = load_manifest(Path(__file__).parent.parent / "manifest.json")
    assert m is not None
    assert m.id == "plot_settings"
    assert "gui" in m.entrypoints.__dict__ or m.entrypoints.gui


def test_widget_constructs(qapp):
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    assert w.windowTitle() == "Plot Settings"
    assert w.backend_combo.count() >= 2


def test_backend_combo_lists_all_backends(qapp):
    from chisurf.gui.chiplot import available_backends
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    items = {w.backend_combo.itemText(i) for i in range(w.backend_combo.count())}
    assert items == set(available_backends())


def test_color_buttons_exist(qapp):
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    for key in ("data", "model", "irf", "residuals", "auto_corr", "region_selector"):
        assert key in w._color_buttons
        btn = w._color_buttons[key]
        assert btn.color.startswith("#")


def test_collect_settings_round_trip(qapp):
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    w._color_buttons["data"].color = "#ff0000"
    w.line_width.setValue(3.0)
    w.enable_grid.setChecked(False)
    settings = w._collect_settings()
    assert settings["colors"]["data"] == "#ff0000"
    assert settings["line_width"] == 3.0
    assert settings["enable_grid"] is False


def test_loading_does_not_overwrite_what_it_is_reading(qapp):
    """Every control comes back with the value the settings held.

    Each ``setChecked``/``setValue`` emits, and the handler applied the *whole*
    dialog to the settings — the same dict the loader was reading, not a copy.
    So the first control to emit wrote every not-yet-loaded control's default
    over the real value: the panel opened with everything unchecked and the
    sliders at zero, and pressing Save then persisted that. This is how a
    settings file ends up with a black foreground on a black background.
    """
    import chisurf.core.settings as css
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    known = {
        "backend": "pyqtgraph",
        "line_width": 2.0,
        "font_size": 9,
        "enable_grid": True,
        "grid_alpha": 0.4,
        "show_data_grid": True,
        "show_residual_grid": False,
        "show_acorr_grid": True,
        "enable_region_selector": True,
        "show_legend": True,
        "hideTitle": False,
        "label_axis": True,
        "colors": {
            "data": "#ffa629",
            "model": "#d400cd",
            "irf": "#4284f5",
            "residuals": "#df0101",
            "auto_corr": "#ff00ff",
            "region_selector": "#26a298",
            "region_selector_alpha": 60,
            "active_transparency": 1.0,
            "inactive_transparency": 0.2,
        },
        "pyqtgraph_config": {
            "antialias": True,
            "background": "k",
            "foreground": "d",
            "leftButtonPan": True,
        },
    }
    previous = css.cs_settings.get("gui", {}).get("plot")
    css.cs_settings.setdefault("gui", {})["plot"] = dict(known)
    try:
        got = PlotSettingsWidget()._collect_settings()
        for key, value in known.items():
            if isinstance(value, dict):
                for sub, expected in value.items():
                    assert got[key][sub] == expected, f"{key}.{sub}"
            else:
                assert got[key] == value, key
    finally:
        if previous is not None:
            css.cs_settings["gui"]["plot"] = previous


def test_every_plot_setting_the_dialog_writes_is_reachable(qapp):
    """The dialog covers the settings the plots read.

    A setting the plots honour but the dialog cannot reach is one a user can
    only change by editing YAML — which is how the grid opacity, the per-panel
    grids and the fit-range selector sat unreachable.
    """
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    written = set(PlotSettingsWidget()._collect_settings())
    for key in (
        "backend",
        "font_size",
        "line_width",
        "enable_grid",
        "grid_alpha",
        "show_data_grid",
        "show_residual_grid",
        "show_acorr_grid",
        "enable_region_selector",
        "show_legend",
        "hideTitle",
        "label_axis",
    ):
        assert key in written, key


def test_apply_settings_updates_cs_settings(qapp):
    import chisurf.core.settings as css
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    w.backend_combo.setCurrentText("pyqtgraph")
    w._apply_settings()
    assert css.cs_settings["gui"]["plot"]["backend"] == "pyqtgraph"


def test_grab_non_null(qapp):
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    w = PlotSettingsWidget()
    pm = w.grab()
    assert not pm.isNull()
    assert pm.width() > 0


def test_plots_panel_in_settings_navigation(qapp):
    """The Plots panel is registered in the Settings navigation host."""
    from chisurf.plugins.core.setup.gui.tool import SETTINGS_PANELS

    names = [p["name"] for p in SETTINGS_PANELS]
    assert "Plots" in names
    plots = [p for p in SETTINGS_PANELS if p["name"] == "Plots"][0]
    assert plots["class_path"] == "chisurf.plugins.core.plot_settings.gui.tool"
    assert plots["class_name"] == "PlotSettingsWidget"


def test_manifest_menu_hidden(qapp):
    """The plugin is menu-hidden (opened via Settings, not as standalone)."""
    from pathlib import Path

    from chisurf.core.plugin import load_manifest

    m = load_manifest(Path(__file__).parent.parent / "manifest.json")
    assert m.menu_hidden is True


def test_settings_tool_loads_plots_panel(qapp):
    """Selecting the Plots row in Settings shows PlotSettingsWidget."""
    from chisurf.plugins.core.setup.gui.tool import UnifiedSettingsTool

    tool = UnifiedSettingsTool()
    tool.show()
    qapp.processEvents()
    # Find the Plots row
    row = None
    for i in range(tool.nav_list.count()):
        if "Plots" in tool.nav_list.item(i).text():
            row = i
            break
    assert row is not None, "Plots row not found in settings nav"
    tool.nav_list.setCurrentRow(row)
    qapp.processEvents()
    qapp.processEvents()
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    psw = tool.stacked_widget.findChild(PlotSettingsWidget)
    assert psw is not None, "PlotSettingsWidget did not load"
    assert psw.isVisible()
    tool.close()
