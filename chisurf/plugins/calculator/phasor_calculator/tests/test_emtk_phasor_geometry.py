"""The phasor calculator window: overlay geometry and reference table against the phasor formulas.

A single-exponential decay of lifetime tau at angular frequency omega has the phasor
``g = 1 / (1 + (omega tau)^2)``, ``s = omega tau / (1 + (omega tau)^2)``, on the universal semicircle.
Every overlay drawn for the ``ON`` settings is checked against that geometry (iso-phase rays,
iso-modulation arcs, polar grid, FRET trajectory, components, mixture and cursor); the form is
``gui/phasor_emtk.view.json``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.phasor_calculator.gui.app import SPEC as VIEW
from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
#: The controls the window draws, as declared in ``gui/phasor_emtk.view.json``.
SPEC = VIEW["controls"]

ON = {
    "show_fret": True,
    "show_component": True,
    "show_mixing": True,
    "show_cursor": True,
    "show_polar_grid": True,
    "frequency": 40.0,
    "harmonic": 2,
    "taus": "1, 3",
}
#: omega in rad/ns: the effective frequency is 40 MHz x harmonic 2 = 80 MHz.
OMEGA = 2 * np.pi * 80e6 * 1e-9


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


def _phasor(tau):
    wt = OMEGA * tau
    return np.array([1 / (1 + wt**2), wt / (1 + wt**2)])


def _xy(overlay):
    return np.asarray(overlay["x"], float), np.asarray(overlay["y"], float)


# 1. the overlays are the phasor geometry of the settings
def test_overlays_are_the_single_exponential_phasor_geometry():
    app = _app()
    m = app.tool._model
    ours = {o["name"]: o for o in app.phasor_gui._overlays()}

    x, y = _xy(ours["universal semicircle"])
    np.testing.assert_allclose((x - 0.5) ** 2 + y**2, 0.25, atol=1e-12)

    ticks = np.column_stack(_xy(ours["lifetime ticks"]))
    np.testing.assert_allclose(ticks, [_phasor(1.0), _phasor(3.0)], rtol=1e-12)
    for tau in (1.0, 3.0):
        end = _phasor(tau)
        x, y = _xy(ours[f"tau_phi={tau:g} ns"])  # iso-phase: the ray at phase atan(omega tau)
        np.testing.assert_allclose([x[0], y[0]], [0.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(y, OMEGA * tau * x, atol=1e-12)
        np.testing.assert_allclose(np.hypot(x[-1], y[-1]), 1.0, rtol=1e-12)  # out to the unit circle
        x, y = _xy(ours[f"tau_m={tau:g} ns"])  # iso-modulation: the arc of radius |P(tau)|
        np.testing.assert_allclose(np.hypot(x, y), np.hypot(*end), rtol=1e-12)
        np.testing.assert_allclose([x[-1], y[-1]], end, rtol=1e-12)

    for r in (1 / 3, 2 / 3, 1.0):  # the polar grid: circles of radius r and rays every 30 degrees
        name = "unit circle" if r == 1.0 else f"r={r:g}"
        np.testing.assert_allclose(np.hypot(*_xy(ours[name])), r, rtol=1e-12)
    for angle in range(0, 360, 30):
        x, y = _xy(ours[f"angle={angle}"])
        a = np.radians(angle)
        np.testing.assert_allclose([x[-1], y[-1]], [np.cos(a), np.sin(a)], atol=1e-12)

    # FRET: tau_DA = tau_D0 (1 - E) stays on the semicircle, from the donor-only phasor to (1, 0)
    x, y = _xy(ours["FRET trajectory"])
    np.testing.assert_allclose((x - 0.5) ** 2 + y**2, 0.25, atol=1e-12)
    np.testing.assert_allclose([x[0], y[0]], _phasor(m.tau_d0), rtol=1e-12)
    assert x[-1] > 0.99 and y[-1] < 0.03

    c1, c2 = np.array([m.g1, m.s1]), np.array([m.g2, m.s2])
    np.testing.assert_allclose(np.column_stack(_xy(ours["component line"])), [c1, c2])
    np.testing.assert_allclose(np.column_stack(_xy(ours["components"])), [c1, c2])
    mix = m.frac1 * c1 + (1 - m.frac1) * c2  # phasors add linearly with the intensity fractions
    np.testing.assert_allclose(np.column_stack(_xy(ours["mixture"])), [mix])
    for name, c in (("mix line 1", c1), ("mix line 2", c2)):
        np.testing.assert_allclose(np.column_stack(_xy(ours[name])), [c, mix])

    x, y = _xy(ours["cursor"])  # the gate: a circle around the cursor
    np.testing.assert_allclose(np.hypot(x - m.cursor_g, y - m.cursor_s), m.cursor_radius, rtol=1e-9)


def test_the_reference_table_holds_the_single_exponential_phasors():
    app = _app()
    rows = app.phasor_gui._rows()
    assert [t for t, _g, _s in rows] == [1.0, 3.0]
    for tau, g, s in rows:
        assert (g, s) == pytest.approx(tuple(_phasor(tau)))


# 3. one spec: every field drawn, its description the tooltip, the groups folded as declared
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)  # the form calls it here
    app = _app()
    for panel in app.phasor_gui._controls_spec()["sections"]:  # open every group to draw all fields
        if panel.get("type") == "panel":
            app.phasor_gui.form.folds[panel["title"]] = True
    _draw(app)
    fields = [f for f in _fields(SPEC["sections"]) if f.get("type") in ("value", "toggle")]
    assert {f["attr"] for f in fields} <= set(app.phasor_gui.form.rects)
    assert all(f["description"] in tips for f in fields)


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
    monkeypatch.setattr(
        implot,
        "begin_plot",
        lambda title, size=(-1.0, 0.0), f=0: (flags.append(f), original(title, size, f))[1],
    )
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


# 6/7. no Qt import, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("phasor_calculator")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("phasor_calculator"))["controls_without_tooltip"] == []
