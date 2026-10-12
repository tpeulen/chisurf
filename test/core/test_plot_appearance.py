"""``gui.plot`` read live, and old settings files cleaned of what no longer exists.

The plots read the plot settings through :mod:`chisurf.core.plotting.appearance` when
they draw. A copy taken at import (``colors = settings["gui"]["plot"]["colors"]``) kept
the start-up palette for the whole session: Settings ▸ Plots replaced the dictionary
and every colour, the line width and the fit-range band looked ignored.
"""

from __future__ import annotations

import copy
import pathlib

import pytest
import yaml

from chisurf.core.plotting import appearance

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGED = ROOT / "chisurf" / "core" / "settings" / "settings_chisurf.yaml"


@pytest.fixture
def plot(monkeypatch):
    import chisurf.core.settings as css

    gui = copy.deepcopy(css.cs_settings.get("gui", {}))
    monkeypatch.setitem(css.cs_settings, "gui", gui)
    return gui.setdefault("plot", {})


def test_a_change_is_seen_by_the_next_read_even_when_the_dictionary_is_replaced(plot):
    plot["colors"] = {"model": "#010203"}
    assert appearance.curve_color("model") == "#010203"
    plot["colors"] = {"model": "#040506"}  # what an editor that rebuilds the block does
    assert appearance.curve_color("model") == "#040506"


def test_the_data_trace_is_drawn_at_half_the_line_width(plot):
    plot["line_width"] = 3.0
    assert appearance.line_width("model") == 3.0
    assert appearance.line_width("data") == 1.5


def test_the_fit_range_band_and_its_switch(plot):
    plot["colors"] = {"region_selector": "#102030", "region_selector_alpha": 77}
    plot["enable_region_selector"] = True
    assert appearance.region_rgba() == (16, 32, 48, 77)
    plot["enable_region_selector"] = False
    assert appearance.region_rgba() is None


def test_the_grid_is_off_when_disabled_globally_or_per_panel(plot):
    plot.update({"enable_grid": True, "grid_alpha": 0.6, "show_residual_grid": False})
    assert appearance.grid_alpha("data") == 0.6
    assert appearance.grid_alpha("residuals") is None
    plot["enable_grid"] = False
    assert appearance.grid_alpha("data") is None
    assert appearance.grid_strength(appearance.GRID_REFERENCE_ALPHA) == 1.0
    assert appearance.grid_strength(0.0) == 0.0
    assert appearance.grid_strength(1.0) == pytest.approx(appearance.GRID_FULL_STRENGTH)


def test_the_shipped_defaults_are_the_packaged_settings():
    """``appearance.DEFAULTS`` stands in for a missing key; it must say what the file ships."""
    shipped = yaml.safe_load(PACKAGED.read_text(encoding="utf-8"))["gui"]["plot"]
    for key, value in appearance.DEFAULTS.items():
        assert shipped[key] == value, key


def test_no_setting_key_or_value_names_pyqtgraph():
    """The packaged settings name no removed renderer: a key nobody reads looks like a setting."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if "pyqtgraph" in str(key).lower():
                    found.append(path + (key,))
                walk(value, path + (key,))
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, path + (i,))
        elif isinstance(node, str) and "pyqtgraph" in node.lower():
            found.append(path)

    walk(yaml.safe_load(PACKAGED.read_text(encoding="utf-8")), ())
    assert not found, found


def test_an_old_settings_file_loads_without_the_retired_plot_keys(tmp_path):
    """A user file written before the cleanup opens without error and loses only the dead keys."""
    from chisurf.core.settings.settings_utils import get_chisurf_settings

    user = tmp_path / "settings_chisurf.yaml"
    user.write_text(
        yaml.safe_dump(
            {
                "gui": {
                    "plot": {
                        "backend": "pyqtgraph",
                        "hideTitle": False,
                        "pyqtgraph_config": {"antialias": True, "background": "w"},
                        "line_width": 3.5,
                        "colors": {"inactive_transparency": 0.2, "model": "#123456"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    plot = get_chisurf_settings(user)["gui"]["plot"]
    assert not {"backend", "hideTitle", "pyqtgraph_config"} & set(plot)
    assert plot["line_width"] == 3.5 and plot["colors"]["model"] == "#123456"
    # 0.2 was the shipped value while nothing read it: the file held the old default.
    assert plot["colors"]["inactive_transparency"] == 0.4
    rewritten = yaml.safe_load(user.read_text(encoding="utf-8"))["gui"]["plot"]
    assert "pyqtgraph_config" not in rewritten and "backend" not in rewritten
