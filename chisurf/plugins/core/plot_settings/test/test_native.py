"""The native plot settings app: state, rendering, tooltips (the earlier smoke tests, kept)."""

from __future__ import annotations

import copy
import json

import pytest
from emtk.testing import RecordingPainter

from ..gui.app import PlotSettingsApp


@pytest.fixture(autouse=True)
def private_settings(tmp_path, monkeypatch):
    """Run on a private copy of ``gui.plot`` and a temporary settings folder."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    import chisurf.core.settings as css

    monkeypatch.setitem(css.cs_settings, "gui", copy.deepcopy(css.cs_settings.get("gui", {})))


def test_native_plot_settings_controls_and_state():
    app = PlotSettingsApp()
    app.model.backend = "pyqtgraph"
    app.model.color_data = "#123456"
    app.model.apply()
    assert app.model.collect()["backend"] == "pyqtgraph"
    assert app.model.collect()["colors"]["data"] == "#123456"
    app.restore_settings({"folds": {"Appearance": True}})
    assert app.export_settings() == {"folds": {"Appearance": True}}
    json.dumps(app.export_settings())


def test_native_plot_settings_renders_with_tooltips(monkeypatch):
    app = PlotSettingsApp()
    tips = []
    import emtk.im as im

    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1200, 800)
    assert "Rendering Backend" in painter.strings
    assert len(tips) >= 2  # Help and Guide; the spec fields carry their own (see the parity tests)


def test_native_node_graph_section_round_trips_and_applies():
    """The node-graph section lands in ``gui.plot`` and loads back."""
    import chisurf.core.settings as css

    app = PlotSettingsApp()
    app.model.set_value("ng_line_width", 2.0)
    app.model.ng_show_grid = False
    app.model.apply()
    stored = css.cs_settings["gui"]["plot"]["node_graph"]
    assert stored["grid_line_width"] == 2.0 and stored["show_grid"] is False
    other = PlotSettingsApp()
    assert other.model.ng_line_width == 2.0 and other.model.ng_show_grid is False


def test_native_node_graph_section_renders():
    app = PlotSettingsApp()
    app.form.folds["Node Graphs (Global View)"] = True
    painter = RecordingPainter()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    assert "Node Graphs (Global View)" in painter.strings
    assert "Grid line width" in painter.strings
