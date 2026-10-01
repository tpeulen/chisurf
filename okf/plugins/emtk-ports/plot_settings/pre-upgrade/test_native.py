from __future__ import annotations

import json

from emtk.testing import RecordingPainter

from ..gui.app import PlotSettingsApp


def test_native_plot_settings_controls_and_state():
    app = PlotSettingsApp()
    app.model.backend = "pyqtgraph"
    app.model.colors["data"] = "#123456"
    state = app.export_settings()
    assert state["backend"] == "pyqtgraph"
    assert state["colors"]["data"] == "#123456"
    app.restore_settings({"backend": "matplotlib", "line_width": 2.5})
    assert app.model.backend == "matplotlib"
    assert app.model.line_width == 2.5
    app.restore_settings({"enable_grid": False, "pyqtgraph_config": {"background": "w"}})
    assert app.model.enable_grid is False
    assert app.model.pyqtgraph_config["background"] == "w"
    json.dumps(app.export_settings())


def test_native_plot_settings_renders_with_tooltips(monkeypatch):
    app = PlotSettingsApp()
    tips = []
    import emtk.im as im
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 760, 700)
    assert "Rendering Backend" in painter.strings
    assert len(tips) >= 8


def test_native_node_graph_section_round_trips_and_applies():
    """The node-graph section exports, restores, and lands in ``gui.plot``."""
    import chisurf.core.settings as css

    app = PlotSettingsApp()
    app.model.node_graph["grid_line_width"] = 2.0
    state = app.export_settings()
    assert state["node_graph"]["grid_line_width"] == 2.0

    app.restore_settings({"node_graph": {"grid_line_width": 0.25, "show_grid": False}})
    assert app.model.node_graph["grid_line_width"] == 0.25
    assert app.model.node_graph["show_grid"] is False

    app.model.apply()
    stored = css.cs_settings["gui"]["plot"]["node_graph"]
    assert stored["grid_line_width"] == 0.25
    assert stored["show_grid"] is False
    json.dumps(state)


def test_native_node_graph_section_renders():
    app = PlotSettingsApp()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 760, 700)
    assert "Node Graphs (Global View)" in painter.strings
    assert "Grid line width" in painter.strings
