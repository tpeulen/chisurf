"""The native PSF calculator against the Qt tool it replaces (the committed gui/tool.py).

The Qt tool needs a 3-D volume renderer that the emtk chiplot backend does not have, so it is driven with a recording stand-in for
the renderer: what the tool hands the renderer (the volume, the colormap, threshold and gamma, the polarization segments) is
compared; the rendered 3-D image itself is not comparable. Hermetic: temporary HOME and settings.
"""

from __future__ import annotations

import json
import re
import time

import numpy as np
import pytest

from .driving import BIG, SMALL, PSFDriver, clipped_texts, draw_clip, hermetic_env, layout_problems
from chisurf.plugins.calculator.psf_calculator.gui.app import PSFApp, SETTINGS, SPEC, make_app

QT_SPEC = json.loads((__import__("pathlib").Path(__file__).parents[1] / "psf_calculator.view.json").read_text())


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def app():
    a = make_app()
    yield a
    a.close()
    a._executor.shutdown(wait=True)


def small(app):
    """A small grid (fast), the Qt defaults otherwise."""
    app.model.nxy, app.model.nz = 24, 7


def settle(app, size=BIG):
    d = PSFDriver(app, size)
    d.settle()
    return d


# -- the same numbers as the Qt tool ------------------------------------------------------------------------ #


class StubView:
    """What the Qt tool hands its 3-D renderer."""

    def __init__(self):
        self.calls = []

    def set_scale(self, *a):
        self.calls.append(("scale", a))

    def set_volume(self, volume, colormap=None, threshold=None, gamma=None):
        self.calls.append(("volume", np.asarray(volume).copy(), colormap, threshold, gamma))

    def set_vectors(self, segments, color=None, width=None):
        self.calls.append(("vectors", None if segments is None else np.asarray(segments).copy()))


_QAPP = []


@pytest.fixture
def qt_tool():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    _QAPP[:] = [QtWidgets.QApplication.instance() or QtWidgets.QApplication([])]  # kept: a collected application aborts the process
    import chisurf.gui.chiplot as cp
    from chisurf.plugins.calculator.psf_calculator.gui.tool import PSFCalculator

    stub = StubView()
    real = cp.VolumeView
    cp.VolumeView = lambda *a, **k: __import__("qtpy.QtWidgets", fromlist=["QWidget"]).QWidget()
    try:
        tool = PSFCalculator()
    finally:
        cp.VolumeView = real
    tool.view = stub
    yield tool
    tool.close()


def run_qt(tool, **params):
    for k, v in params.items():
        setattr(tool.model, k, v)
    tool.model.compute()
    tool._show(tool.model.volume)
    return tool


SCENARIOS = [
    {"nxy": 24, "nz": 7},
    {"nxy": 24, "nz": 7, "model": "airy", "polarization": "linear", "angle_deg": 45.0},
    {"nxy": 24, "nz": 7, "model": "gaussian"},
    {"nxy": 24, "nz": 7, "polarization": "radial"},
    {"nxy": 16, "nz": 5, "na": 1.2, "n_immersion": 1.333, "wavelength_nm": 640.0, "polarization": "x", "show_polarization": False},
]


@pytest.mark.parametrize("params", SCENARIOS, ids=lambda p: "-".join(f"{k}={v}" for k, v in p.items() if k not in ("nxy", "nz"))[:60] or "defaults")
def test_the_volume_the_summary_and_what_the_renderer_gets_equal_the_qt_tools(app, qt_tool, params):
    run_qt(qt_tool, **params)
    for k, v in params.items():
        setattr(app.model, k, v)
    app.model.compute()
    assert np.array_equal(app.model.volume, qt_tool.model.volume)
    qt_lines = [re.sub(r"^- ", "", line).replace("**", "") for line in qt_tool.model.summary_text().splitlines()]
    assert app.panel.summary_lines().splitlines() == qt_lines
    volume_call = next(c for c in qt_tool.view.calls if c[0] == "volume")
    vectors_call = next(c for c in qt_tool.view.calls if c[0] == "vectors")
    assert volume_call[2:] == (app.model.colormap, app.model.threshold, app.model.gamma)
    segments = app.model.polarization_segments() if app.model.show_polarization else None
    assert (vectors_call[1] is None) == (segments is None)
    if segments is not None:
        assert np.array_equal(vectors_call[1], segments)


def test_every_field_of_the_qt_spec_is_in_the_emtk_spec_with_the_same_range_step_and_choices():
    def leaves(sections):
        for s in sections:
            if "attr" in s:
                yield s
            yield from leaves(s.get("sections", []))

    qt = {s["attr"]: s for s in leaves(QT_SPEC["sections"])}
    ours = {s["attr"]: s for s in leaves(SPEC["parameters"]["sections"])}
    assert set(qt) - {"psf_volume_view"} <= set(ours) and set(ours) <= set(qt)
    for name, theirs in ours.items():
        for key in ("kind", "minimum", "maximum", "step", "decimals", "options", "labels", "label"):
            assert theirs.get(key) == qt[name].get(key), (name, key)
        if name == "quality":
            assert theirs.get("style") is None and qt[name].get("style") == "radio"  # deliberate: the inline radios were cut at 800 px
        else:
            assert theirs.get("style") in (qt[name].get("style"), "spin")  # the number fields gain the Qt spin arrows


def test_the_choice_lists_equal_the_qt_combo_labels(qt_tool):
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget

    qt = {cw._section.attr: ([cw.combo.itemText(i) for i in range(cw.combo.count())] if cw.combo is not None
                             else [b.text() for b in cw._radios]) for cw in qt_tool.auto_form.findChildren(ChoiceWidget)}
    ours = {s["attr"]: s.get("labels") or s["options"] for p in SPEC["parameters"]["sections"] for s in p["sections"] if s.get("type") == "choice"}
    assert qt == ours


def test_the_toolbar_offers_the_qt_export_formats_and_both_files_equal_the_qt_exports(app, qt_tool, tmp_path, monkeypatch):
    run_qt(qt_tool, nxy=16, nz=5)
    import chisurf.gui.widgets.general as G

    qt_files = {}
    for suffix, filt in ((".npy", "NumPy array (*.npy)"), (".tif", "TIFF stack (*.tif *.tiff)")):
        target = tmp_path / f"qt{suffix}"
        monkeypatch.setattr(G, "save_file", lambda description="", file_type="", _t=target: str(_t))
        qt_tool.export_volume(suffix, filt)
        qt_files[suffix] = target
    app.model.nxy, app.model.nz = 16, 5
    app.model.compute()
    assert app.model.save(tmp_path / "ours.npy").read_bytes() == qt_files[".npy"].read_bytes()
    ours_tif = app.model.save(tmp_path / "ours.tif")
    assert np.array_equal(__import__("tifffile").imread(ours_tif), __import__("tifffile").imread(qt_files[".tif"]))


# -- spec, tooltips, Qt-free --------------------------------------------------------------------------------- #


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_every_section_button_and_column_of_the_spec_has_a_description():
    missing = []
    for node in walk(SPEC):
        if node.get("type") in ("button_row", "toggle", "value", "choice", "info", "panel") and node.get("type") != "panel" and not node.get("description"):
            missing.append((node.get("type"), node.get("attr")))
        if node.get("type") == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    assert not missing, missing


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import emtk_inventory

    small(app)
    settle(app)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 14


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("psf_calculator")
    assert verdict["ok"], verdict["output"]


# -- the idle state and the layout ------------------------------------------------------------------------- #


def test_controls_that_mean_nothing_in_this_state_are_greyed(app):
    p = app.panel
    assert p.enabled("polarization") and not p.enabled("angle_deg") and p.enabled("show_polarization")  # vectorial, circular
    app.model.polarization = "linear"
    assert p.enabled("angle_deg")
    app.model.model = "airy"
    assert not p.enabled("polarization") and not p.enabled("angle_deg") and not p.enabled("show_polarization")
    assert not p.enabled("export_npy") and not p.enabled("export_tif")  # nothing computed yet


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("state", ["empty", "populated"])
def test_draws_and_the_layout_is_clean(app, size, state):
    if state == "populated":
        small(app)
        settle(app, size)
    painter = draw_clip(app, size)
    assert {"Parameters", "3-D PSF", "Orthogonal Slice", "NA", "Export .npy"} <= set(painter.strings)
    plots = [app.item_rects[k] for k in ("volume", "slice") if k in app.item_rects]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    # a choice shows its whole label (emtk shortens one that does not fit)
    assert {"Vectorial (Richards-Wolf)", "Circular", "magma", "Preview (fast)", "XY"} <= set(painter.strings)


def test_settings_round_trip_clamp_and_ignore_garbage(app):
    app.model.na, app.model.model, app.model.nxy, app.model.show_polarization, app.model.colormap = 1.2, "airy", 32, False, "gray"
    app.slice_plane = "XZ"
    saved = json.loads(json.dumps(app.export_settings()))
    assert set(saved) == set(SETTINGS) | {"slice_plane"}
    other = make_app()
    try:
        other.restore_settings(saved)
        m = other.model
        assert (m.na, m.model, m.nxy, m.show_polarization, m.colormap, other.slice_plane) == (1.2, "airy", 32, False, "gray", "XZ")
        other.restore_settings({"na": 99, "nxy": -4, "model": "bogus", "colormap": 5, "show_polarization": "yes", "slice_plane": "AB"})
        assert m.na == 1.7 and m.nxy == 16 and m.model == "airy" and m.colormap == "gray" and m.show_polarization is False and other.slice_plane == "XZ"
        other.restore_settings("garbage")  # does not raise
    finally:
        other.close()
        other._executor.shutdown(wait=True)
