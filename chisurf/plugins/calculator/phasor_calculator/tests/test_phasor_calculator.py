"""Headless + offscreen-GUI tests for the phasor calculator."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_model_overlays_track_toggles():
    from chisurf.plugins.calculator.phasor_calculator.gui.model import _PhasorCalcModel

    m = _PhasorCalcModel()
    m.show_grid = False
    m.show_ticks = True
    m.show_fret = False
    m.show_component = False
    names = {o.get("name") for o in m.phasor_overlays()}
    assert "lifetime ticks" in names

    m.show_fret = True
    m.show_component = True
    names = {o.get("name") for o in m.phasor_overlays()}
    assert "FRET trajectory" in names
    assert "component line" in names


def test_model_tau_parsing_is_robust():
    from chisurf.plugins.calculator.phasor_calculator.gui.model import _PhasorCalcModel

    m = _PhasorCalcModel()
    m.taus = "1, 2 ; 4 , bad,"
    assert m._tau_list() == [1.0, 2.0, 4.0]
    m.taus = "garbage"
    assert m._tau_list() == [1.0]  # falls back to a sane default


def test_results_html_lists_reference_points():
    from chisurf.plugins.calculator.phasor_calculator.gui.model import _PhasorCalcModel

    m = _PhasorCalcModel()
    html = m.results_html()
    assert "MHz" in html and "<table>" in html


def test_is_a_button_of_tools_calculators():
    import json
    from pathlib import Path

    from chisurf.plugins.calculator import phasor_calculator

    manifest = json.loads((Path(phasor_calculator.__file__).parent / "manifest.json").read_text())
    assert manifest["display_name"] == "Tools:Calculators:Phasor Calculator"
    assert not manifest.get("menu_hidden")


def test_view_spec_loads():
    from chisurf.plugins.calculator.phasor_calculator.gui.app import SPEC

    assert SPEC["controls"] and SPEC["results"]


def test_native_app_constructs_and_renders():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app

    app = make_app()
    # Toggle overlays and refresh without error.
    app.tool._model.show_fret = True
    app.tool._model.show_component = True
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 860, 660)
    assert painter.texts
