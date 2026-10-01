"""The native phasor calculator at parity with the Qt PhasorCalculatorTool.

The committed Qt tool rendered ``phasor.view.json`` with AutoForm over an inline model;
the model moved unchanged to ``gui/model.py`` and the Qt window now hosts this emtk app.
The Qt window runs in a subprocess (this process stays Qt-free): its model's overlay
geometry and results are compared with the emtk app's, the reference table against the
phasor formulas.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SPEC = json.loads((HERE.parent / "gui" / "phasor.view.json").read_text())

from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app  # noqa: E402

ON = {"show_fret": True, "show_component": True, "show_mixing": True, "show_cursor": True, "show_polar_grid": True,
      "frequency": 40.0, "harmonic": 2, "taus": "1, 3"}


def _app(**settings):
    app = make_app()
    for key, value in {**ON, **settings}.items():
        setattr(app.tool._model, key, value)
    return app


def _draw(app, size=(1200, 800), n=2):
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _fields(sections):
    for section in sections:
        if "attr" in section:
            yield section
        yield from _fields(section.get("sections", []))


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.calculator.phasor_calculator.gui.tool import PhasorCalculatorTool
w = PhasorCalculatorTool()
for k, v in json.loads(sys.argv[1]).items():
    setattr(w._model, k, v)
w._form.sync_fields(); w._form.refresh_plots()
overlays = [{"name": o.get("name"), "x": [float(v) for v in o.get("x", [])], "y": [float(v) for v in o.get("y", [])]}
            for o in w._model.phasor_overlays()]
print("FACTS" + json.dumps({"overlays": overlays, "html": w._model.results_html(),
                            "hosts": type(w.app).__name__, "same_model": w.app.tool._model is w._model}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, json.dumps(ON)], capture_output=True, text=True, timeout=300,
                          env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"the Qt tool could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS"):])


# 1. the same geometry and the same reference table as the Qt tool
def test_overlays_equal_the_qt_tools(qt):
    app = _app()
    ours = {o["name"]: o for o in app.phasor_gui._overlays()}
    for theirs in qt["overlays"]:
        mine = ours[theirs["name"]]
        assert np.asarray(mine["x"], float) == pytest.approx(np.asarray(theirs["x"]))
        assert np.asarray(mine["y"], float) == pytest.approx(np.asarray(theirs["y"]))
    assert "universal semicircle" in ours                     # the emtk plot draws the circle itself


def test_the_reference_table_holds_the_qt_results(qt):
    app = _app()
    rows = app.phasor_gui._rows()
    assert [t for t, _g, _s in rows] == [1.0, 3.0]
    for tau, g, s in rows:
        assert f"<td>{tau:g}</td><td>{g:.3f}</td><td>{s:.3f}</td>" in qt["html"]
        omega_tau = 2 * np.pi * 80e6 * tau * 1e-9            # effective f = 40 MHz x harmonic 2
        assert g == pytest.approx(1 / (1 + omega_tau ** 2)) and s == pytest.approx(omega_tau / (1 + omega_tau ** 2))


# 3. one spec: every field drawn, its description the tooltip, the groups folded as declared
def test_every_spec_field_is_drawn_with_its_description(monkeypatch, qt):
    from emtk import im, im_widgets

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)   # the form calls it here
    app = _app()
    for panel in app.phasor_gui._controls_spec()["sections"]:     # open every group to draw all fields
        if panel.get("type") == "panel":
            app.phasor_gui.form.folds[panel["title"]] = True
    _draw(app)
    fields = [f for f in _fields(SPEC["sections"]) if f.get("type") in ("value", "toggle")]
    assert {f["attr"] for f in fields} <= set(app.phasor_gui.form.rects)
    assert all(f["description"] in tips for f in fields)
    assert qt["hosts"] == "PhasorCalcApp" and qt["same_model"]  # the Qt window hosts this app


def test_groups_start_folded_as_the_spec_declares():
    app = _app()
    _draw(app)
    rects = app.phasor_gui.form.rects
    assert "show_fret" in rects and "frac1" not in rects and "cursor_g" not in rects


def test_an_edit_in_the_form_reaches_the_table():
    from emtk.view_form import _commit

    app = _app()
    field = next(f for f in _fields(SPEC["sections"]) if f.get("attr") == "frequency")
    _commit(app.tool._model, field, 20.0, app.phasor_gui.form)
    assert app.phasor_gui._rows()[0][1] == pytest.approx(1 / (1 + (2 * np.pi * 40e6 * 1e-9) ** 2))


# 4. the plot: equal scale, a legend of the references only
def test_the_plot_is_drawn_at_equal_scale_with_a_short_legend(monkeypatch):
    from emtk import implot

    flags = []
    original = implot.begin_plot
    monkeypatch.setattr(implot, "begin_plot", lambda title, size=(-1.0, 0.0), f=0: (flags.append(f), original(title, size, f))[1])
    app = _app()
    strings = _draw(app).strings
    assert flags and all(f & implot.FLAGS_EQUAL for f in flags)
    assert {"universal semicircle", "FRET trajectory", "cursor"} <= set(strings)
    assert not [s for s in strings if s.startswith(("angle=", "r=", "tau_m="))]


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws(size):
    strings = _draw(_app(), size).strings
    assert {"Effective f = 80 MHz", "Frequency", "Lifetimes (ns)"} <= set(strings)


# guide: every target reachable, a step into a folded group unfolds it
def test_every_guide_target_is_drawn_and_folded_targets_unfold():
    app = _app()
    gui = app.phasor_gui
    _draw(app)
    for index, step in enumerate(gui.tour.steps):
        key = gui.tour._target_key(step.get("target"))
        if not key:
            continue
        gui.tour.start(index)
        _draw(app)
        assert key in gui.item_rects or key in gui.form.rects, key
    gui.tour.active = False


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("phasor_calculator")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("phasor_calculator"))["controls_without_tooltip"] == []
