"""The plot settings plugin: manifest, and the settings the model reads and writes live."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from chisurf.core.plugin import load_manifest

MANIFEST = Path(__file__).parent.parent / "manifest.json"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """A temporary settings folder and a private copy of the ``gui`` settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path))
    import chisurf.core.settings as css

    monkeypatch.setitem(css.cs_settings, "gui", copy.deepcopy(css.cs_settings.get("gui", {})))
    return tmp_path


def live() -> dict:
    import chisurf.core.settings as css

    return css.cs_settings["gui"]["plot"]


def make_model(**kw):
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    return PlotSettingsModel(**kw)


def test_manifest_loads_with_only_the_native_entrypoint():
    m = load_manifest(MANIFEST)
    assert m is not None and m.id == "plot_settings"
    assert m.entrypoints.emtk and not m.entrypoints.gui


def test_manifest_menu_hidden():
    """The plugin is menu-hidden: it is opened from Settings, not as a standalone tool."""
    assert load_manifest(MANIFEST).menu_hidden is True


def test_a_field_reads_and_writes_the_live_settings():
    model = make_model(persist=False)
    model.color_data = "#ABC"
    model.line_width = 3.0
    model.grid_alpha_pct = 60
    model.ng_grid_opacity_pct = 30
    assert live()["colors"]["data"] == "#aabbcc"
    assert live()["line_width"] == 3.0
    assert live()["grid_alpha"] == pytest.approx(0.6)
    assert live()["node_graph"]["grid_opacity"] == pytest.approx(0.3)
    assert make_model(persist=False).grid_alpha_pct == 60


def test_a_value_is_clamped_into_the_control_range():
    model = make_model(persist=False)
    model.region_alpha = 999
    model.inactive_transparency = -1
    model.font_size = 3.6
    assert live()["colors"]["region_selector_alpha"] == 255
    assert live()["colors"]["inactive_transparency"] == 0.0
    assert live()["font_size"] == 4


def test_a_missing_key_reads_as_the_shipped_value():
    live().clear()
    model = make_model(persist=False)
    assert model.line_width == 2.0 and model.show_legend is True
    assert model.ng_grid_spacing == 24.0 and model.inactive_transparency == 0.4


def test_the_node_graph_defaults_mirror_the_reader():
    from chisurf.emtk.node_editor.style_settings import NODE_GRAPH_DEFAULTS
    from chisurf.plugins.core.plot_settings.gui.model import NODE_GRAPH_DEFAULTS as ours

    assert ours == NODE_GRAPH_DEFAULTS


def test_flush_writes_only_what_differs_from_the_shipped_look(hermetic):
    model = make_model()
    model.color_model = "#00ff00"
    model.flush()
    stored = yaml.safe_load((hermetic / "settings_chisurf.yaml").read_text(encoding="utf-8"))
    assert stored["gui"]["plot"] == {"colors": {"model": "#00ff00"}}
    assert not model.unsaved


def test_reset_to_defaults_restores_the_shipped_look_and_saves_it(hermetic):
    model = make_model()
    model.line_width = 7.0
    model.show_legend = False
    model.flush()
    model.reset_defaults()
    assert model.line_width == 2.0 and model.show_legend is True
    stored = yaml.safe_load((hermetic / "settings_chisurf.yaml").read_text(encoding="utf-8"))
    assert stored["gui"]["plot"] == {}


def test_no_field_names_a_retired_setting():
    """The renderer choice, the pyqtgraph options and "hide titles" changed no plot."""
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    fields = PlotSettingsModel.fields()
    assert not {"backend", "hide_title"} & set(fields)
    assert not [name for name in fields if name.startswith("pg_")]
