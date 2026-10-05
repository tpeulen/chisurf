"""The State Scheme page drawn by emtk: the scheme read from the model, and its gestures."""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.plots.state_scheme_emtk import (  # noqa: E402
    SchemeBinding,
    SchemeCanvas,
    edge_route,
)


class _Dark:
    def __init__(self, n, rates):
        self.n_states = n
        self.rate_values = list(rates)


class _Saturation:
    def __init__(self):
        # S0 -> S1 driven by the laser, S1 -> S0 250000, S1 -> T1 2500, T1 -> S0 500
        n = 3
        rates = np.zeros(n * n)
        rates[1 * n + 0] = 250000.0
        rates[1 * n + 2] = 2500.0
        rates[2 * n + 0] = 500.0
        self.dark = _Dark(n, rates)
        self.n_states = n
        self.state_labels = ["S0 ground", "S1 excited", "T1 triplet"]
        self.excitation_edge = (0, 1)


class _Model:
    def __init__(self):
        self.saturation = _Saturation()
        self.scheme_preset = "Jablonski"
        self.loaded = None

    def scheme_names(self):
        return ["Jablonski", "Cis-trans"]

    def load_scheme_from_file(self, path):
        self.loaded = path


@pytest.fixture
def canvas():
    from emtk.testing import RecordingPainter

    changed = []
    binding = SchemeBinding(_Model(), on_changed=lambda: changed.append(1))
    canvas = SchemeCanvas(binding)
    canvas.draw(RecordingPainter(), 0.0, 0.0, 600.0, 400.0)
    canvas.changed = changed
    return canvas


def _centre(canvas, i):
    return canvas.to_canvas(canvas.coords[i])


def test_the_scheme_is_read_from_the_model(canvas):
    binding = canvas.binding
    assert binding.n_states() == 3
    assert binding.labels() == ["S0", "S1", "T1"]
    edges = {(e.i, e.j): e for e in binding.edges(canvas.coords, canvas.bows)}
    # every non-zero rate, and the pumped edge although its rate is zero
    assert set(edges) == {(0, 1), (1, 0), (1, 2), (2, 0)}
    assert edges[(0, 1)].label == "k_exc" and edges[(0, 1)].excitation
    assert edges[(1, 2)].label == "2500.00"


def test_a_badge_is_drawn_for_every_edge(canvas):
    assert set(canvas._badges) == {(0, 1), (1, 0), (1, 2), (2, 0)}


def test_dragging_a_node_moves_it(canvas):
    x, y = _centre(canvas, 2)
    canvas.press(x, y)
    canvas.drag(x + 40.0, y - 30.0)
    canvas.release()
    nx, ny = _centre(canvas, 2)
    assert (nx, ny) == pytest.approx((x + 40.0, y - 30.0))


def test_dragging_the_background_pans_everything(canvas):
    before = _centre(canvas, 0)
    canvas.press(5.0, 5.0)
    canvas.drag(25.0, 15.0)
    canvas.release()
    assert _centre(canvas, 0) == pytest.approx((before[0] + 20.0, before[1] + 10.0))


def test_dragging_a_badge_bends_its_arrow(canvas):
    bx, by, bw, bh = canvas._badges[(1, 2)]
    canvas.press(bx + bw / 2, by + bh / 2)
    canvas.drag(bx + bw / 2, by + bh / 2 + 40.0)
    canvas.release()
    assert (1, 2) in canvas.bows


def test_the_wheel_zooms_about_the_pointer(canvas):
    x, y = _centre(canvas, 1)
    canvas.hover(x, y)
    canvas.scroll(-3)          # one notch up
    assert canvas.zoom > 1.0
    assert _centre(canvas, 1) == pytest.approx((x, y)), "the node under the pointer moved"


def test_a_double_click_on_a_badge_opens_the_rate_for_typing(canvas):
    bx, by, bw, bh = canvas._badges[(1, 2)]
    canvas.press(bx + bw / 2, by + bh / 2, clicks=2)
    assert canvas.editing == (1, 2)


def test_writing_a_rate_changes_the_model_and_says_so(canvas):
    canvas.binding.set_rate(1, 2, 1234.0)
    assert canvas.binding.rates()[1 * 3 + 2] == 1234.0
    assert canvas.changed


def test_presets_and_load_go_to_the_model(canvas):
    binding = canvas.binding
    assert binding.preset_names() == ["Jablonski", "Cis-trans"]
    binding.set_preset("Cis-trans")
    assert binding.model.scheme_preset == "Cis-trans"
    binding.load("/tmp/x.json")
    assert binding.model.loaded == "/tmp/x.json"


def test_edges_end_on_the_rims_not_the_centres():
    p0, _, _, p3, _ = edge_route((0.0, 0.0), (100.0, 0.0))
    assert p0[0] == pytest.approx(26.0) and p3[0] == pytest.approx(74.0)


def test_a_model_without_a_scheme_draws_a_note():
    from emtk.testing import RecordingPainter

    canvas = SchemeCanvas(SchemeBinding(object()))
    canvas.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    assert canvas.coords == {}


def test_the_page_draws_on_the_fit_window_surface(qapp, qtbot):
    """Inside a real ControlHost: the page is emtk, typing a rate writes it."""
    from emtk.qt_host import ControlHost
    from qtpy import QtCore
    from qtpy.QtTest import QTest

    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot
    from chisurf.gui.plots.emtk_page import page_body
    from chisurf.gui.widgets.fitting.fit_plots_area import make_surface

    fit = type("Fit", (), {"model": _Model()})()
    page = StateSchemePlot(fit)
    body = page_body(page)
    assert body.draw is not None and body.missing == []

    surface = make_surface()
    surface.add_page("0:State Scheme", "State Scheme", lambda: page)
    host = ControlHost(surface)
    qtbot.addWidget(host)
    host.resize(700, 500)
    host.show()
    for _ in range(3):
        qapp.processEvents()
        host.repaint()
    bx, by, bw, bh = page.canvas._badges[(1, 2)]
    point = QtCore.QPoint(int(bx + bw / 2), int(by + bh / 2))
    QTest.mouseDClick(host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point)
    for _ in range(3):
        qapp.processEvents()
        host.repaint()
    assert page.canvas.editing == (1, 2)
    QTest.keyClick(host, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
    QTest.keyClicks(host, "777")
    host.repaint()
    QTest.keyClick(host, QtCore.Qt.Key_Return)
    for _ in range(3):
        qapp.processEvents()
        host.repaint()
    assert page.binding.rates()[1 * 3 + 2] == 777.0
    assert page.canvas.editing is None


def test_the_default_layout_follows_the_canvas_until_arranged():
    """A first frame drawn small must not cram the layout into a corner for good."""
    from emtk.testing import RecordingPainter

    canvas = SchemeCanvas(SchemeBinding(_Model()))
    canvas.draw(RecordingPainter(), 0.0, 0.0, 10.0, 10.0)
    small = dict(canvas.coords)
    canvas.draw(RecordingPainter(), 0.0, 0.0, 900.0, 600.0)
    assert canvas.coords[2][0] > small[2][0] + 100
    # once the user moves something, the layout is theirs
    x, y = canvas.to_canvas(canvas.coords[0])
    canvas.press(x, y)
    canvas.drag(x + 10, y)
    canvas.release()
    arranged = dict(canvas.coords)
    canvas.draw(RecordingPainter(), 0.0, 0.0, 1200.0, 800.0)
    assert canvas.coords == arranged
