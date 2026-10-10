"""Tests for the plot settings plugin (manifest and the settings the model reads and writes)."""

from __future__ import annotations

from pathlib import Path

import chisurf.core.settings as css
from chisurf.core.plugin import load_manifest
from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

MANIFEST = Path(__file__).parent.parent / "manifest.json"


def test_manifest_loads_with_only_the_native_entrypoint():
    m = load_manifest(MANIFEST)
    assert m is not None and m.id == "plot_settings"
    assert m.entrypoints.emtk and not m.entrypoints.gui


def test_manifest_menu_hidden():
    """The plugin is menu-hidden: it is opened from Settings, not as a standalone tool."""
    assert load_manifest(MANIFEST).menu_hidden is True


def test_the_model_collects_the_color_and_values_it_was_given():
    model = PlotSettingsModel(load=False)
    model.line_width = 3.0
    model.enable_grid = False
    settings = model.collect()
    assert settings["line_width"] == 3.0 and settings["enable_grid"] is False


def test_loading_does_not_overwrite_what_it_is_reading():
    """Every control comes back with the value the settings held, not a default."""
    known = {
        "backend": "emtk",
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
        got = PlotSettingsModel().collect()
        for key, value in known.items():
            if isinstance(value, dict):
                for sub, expected in value.items():
                    assert got[key][sub] == expected, f"{key}.{sub}"
            else:
                assert got[key] == value, key
    finally:
        if previous is not None:
            css.cs_settings["gui"]["plot"] = previous


def test_every_plot_setting_the_editor_writes_is_reachable():
    """A setting the plots honour but the editor cannot reach can only be changed in YAML."""
    written = set(PlotSettingsModel(load=False).collect())
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


def test_apply_settings_updates_cs_settings():
    previous = css.cs_settings.get("gui", {}).get("plot")
    model = PlotSettingsModel()
    model.apply()
    assert css.cs_settings["gui"]["plot"]["backend"] == "emtk"
    if previous is not None:
        css.cs_settings["gui"]["plot"] = previous
