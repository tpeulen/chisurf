"""The native IRF & BG calibration at parity with the Qt ImgCalibrationTool.

The Qt tool runs in a subprocess (this process stays Qt-free) on real photons -- the
micro-time shifter's demo SPC as source and IRF, one detector from channels 0 (parallel)
and 8 (perpendicular) -- and its decay, windows and backgrounds are compared with the
emtk app's; the backgrounds also with the mean counts of a histogram made here from
the photons directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402

from chisurf.plugins.microscopy.img_calibration.gui.app import make_app  # noqa: E402
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build  # noqa: E402
# isort: on

SETUP = {"detectors": {"green": {"chs": [0, 8], "ch_p": [0], "ch_s": [8]}}}
SPEC = json.loads((HERE.parent / "gui" / "calibration.view.json").read_text())


@pytest.fixture(scope="module")
def spc(tmp_path_factory):
    return str(build(tmp_path_factory.mktemp("cal") / "demo"))


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _binned(app, timeout=60.0):
    end = time.monotonic() + timeout
    _draw(app, n=1)
    while app.busy or app.model.needs_histograms():
        assert time.monotonic() < end, "the histograms were not binned"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _loaded(spc):
    app = make_app()
    app.apply_setup_settings(SETUP)
    app.apply_pipeline_context({"source": spc})
    app.add_irfs([spc])
    _binned(app)  # by drawn frames alone: the worker bins
    app.model.set_conv_range(500, 3000)
    app.model.set_irf_range(550, 700)
    app.model.set_bg_range(0, 400)
    return app


def _fields(sections):
    for section in sections:
        if section.get("attr"):
            yield section
        yield from _fields(section.get("sections", []))


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.microscopy.img_calibration.gui.tool import ImgCalibrationTool
spc, setup = sys.argv[1], json.loads(sys.argv[2])
w = ImgCalibrationTool()
m = w.model
m.apply_setup_settings(setup); m.apply_pipeline_context({"source": spc}); m.sel_irf_files = [spc]
m.ensure_histograms()
m.set_conv_range(500, 3000); m.set_irf_range(550, 700); m.set_bg_range(0, 400)
published = []
m.publish = published.append
m.apply()
d = m.decay_data()
print("FACTS" + json.dumps({"n": d["n"], "data": d["data"].tolist(), "irf_vv": d["irf_vv"].tolist(),
                            "conv": d["conv"], "irf_range": d["irf_range"], "bg": [m.sel_bg_vv, m.sel_bg_vh],
                            "status": m.status_text, "published": published}))
"""


@pytest.fixture(scope="module")
def qt(spc):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, spc, json.dumps(SETUP)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


# 1. the Qt tool's decay, windows and backgrounds; the backgrounds are the photons' mean counts
def test_the_calibration_is_the_qt_tools_and_the_backgrounds_are_the_photons(qt, spc):
    import tttrlib

    app = _loaded(spc)
    try:
        d = app.model.decay_data()
        assert d["n"] == qt["n"] == 4096
        np.testing.assert_allclose(d["data"], qt["data"])
        np.testing.assert_allclose(d["irf_vv"], qt["irf_vv"])
        assert (
            list(d["conv"]) == qt["conv"] == [500, 3000] and list(d["irf_range"]) == qt["irf_range"]
        )
        assert [app.model.sel_bg_vv, app.model.sel_bg_vh] == pytest.approx(qt["bg"])
        data = tttrlib.TTTR(spc)
        micro, routing = np.asarray(data.micro_times), np.asarray(data.routing_channels)
        for channel, value in ((0, app.model.sel_bg_vv), (8, app.model.sel_bg_vh)):
            counts = np.bincount(micro[routing == channel], minlength=4096)
            assert value == pytest.approx(counts[:400].mean())  # the grey region's mean
    finally:
        app.close()


# 2. apply: the Qt status, a deep copy, and refusals the Qt tool did not make
def test_apply_publishes_a_snapshot_as_the_qt_tool_does(qt, spc):
    app = _loaded(spc)
    try:
        published = []
        app.model.publish = published.append
        assert app.apply()
        assert app.model.status_text == qt["status"] == "Applied calibration (1 detector(s) set)."
        assert json.loads(json.dumps(published[0])) == json.loads(json.dumps(qt["published"][0]))
        app.model.sel_irf_files = []
        assert published[0]["green"]["irf"] == [spc]  # an edit after Apply stays out
        app.model.set_conv_range(3000, 3000)
        assert not app.apply() and len(published) == 1
        assert app.model.status_text == "Not applied: green: range start must be smaller than stop"
        assert app.model.status_text in _draw(app).strings
    finally:
        app.close()


# 3. one spec: every field drawn with its description; edits reach the model
def test_every_spec_field_is_drawn_with_its_description(spc, monkeypatch):
    from emtk import im, im_widgets
    from emtk.view_form import _commit

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    app = _loaded(spc)
    try:
        _draw(app)
        fields = list(_fields(SPEC["sections"]))
        assert {f["attr"] for f in fields} <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        assert (
            "Conv start" in _draw(app).strings and "Fit start" not in _draw(app).strings
        )  # the spec's labels
        field = next(f for f in fields if f["attr"] == "sel_shift_vv")
        _commit(app.model, field, 12.5, app.form)
        assert app.model.sel_shift_vv == 12.5
    finally:
        app.close()


def test_the_irf_list_adds_removes_and_clears(spc, tmp_path):
    app = _loaded(spc)
    try:
        app.choose("irf")
        assert app.dialog.multiselect and app.dialog.filters[0][0] == "Photon data"
        other = tmp_path / "second.spc"
        other.write_bytes(Path(spc).read_bytes())
        app.dialog.draw = lambda: [str(other)]
        _draw(app, n=1)
        assert app.model.sel_irf_files == [spc, str(other)]
        app.file_selection = 1
        app.remove_irf()
        assert app.model.sel_irf_files == [spc]
        app.on_files_dropped([str(other)])  # a drop adds to this detector's IRF
        assert app.model.sel_irf_files == [spc, str(other)]
        app.model.sel_irf_files = []
        assert "No IRF file: the raw data are used" in _draw(app).strings
    finally:
        app.close()


def test_the_plot_shows_the_peaks_and_frames_follow_the_binning(spc, monkeypatch):
    from emtk import implot
    from emtk import implot_internal as I

    app = _loaded(spc)
    try:
        seen = {}
        end = implot.end_plot

        def record():
            plot = I.gp.current_plot
            if plot is not None:
                seen["y"] = (plot.axes[I.AXIS_Y1].range_min, plot.axes[I.AXIS_Y1].range_max)
            return end()

        monkeypatch.setattr(implot, "end_plot", record)
        _draw(app, n=2)
        assert seen["y"][1] >= float(
            np.max(app.model.decay_data()["data"])
        )  # the peaks are not clipped
    finally:
        app.close()
    app = make_app()
    try:
        app.apply_setup_settings(SETUP)
        app.apply_pipeline_context({"source": spc})
        _draw(app, n=1)
        assert app.busy and app.animating()  # binning: frames are requested
        _binned(app)
        assert not app.animating()
    finally:
        app.close()


# guide: every target drawn; Open TTTR and Apply wait for presses
def test_the_guide_points_at_real_controls_and_waits(spc):
    app = _loaded(spc)
    size = (1200, 800)
    try:
        _draw(app, size, painter=PixelPainter)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys == {
            "open_source",
            "display_detector",
            "path_list",
            "sel_conv_start",
            "sel_bg_vv",
            "decay_conv",
            "apply",
        }
        assert keys <= set(app.item_rects) | set(app.form.rects)

        def press(key):
            x, y, w, h = app.item_rects.get(key) or app.form.rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        published = []
        app.model.publish = published.append
        for key in ("open_source", "apply"):
            index = next(
                i for i, s in enumerate(steps) if app.tour._target_key(s.get("target")) == key
            )
            app.tour.start(index)
            assert app.tour.awaiting and steps[index]["title"] in " ".join(
                _draw(app, size, n=1).strings
            )
            _draw(app, size, n=1, painter=PixelPainter)
            press(key)
            assert not app.tour.awaiting, key
            app.dialog = None
        assert len(published) == 1  # the Apply press applied
    finally:
        app.tour.active = False
        app.close()


# 4. draws, empty and populated, at both sizes; every toolbar button inside the dock
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(spc, size, monkeypatch):
    from emtk import im

    empty = make_app()
    try:
        strings = _draw(empty, size).strings
        assert (
            "Configure detector windows in Imaging Tools" in " ".join(strings)
            and "Guide" in strings
        )
    finally:
        empty.close()
    app = _loaded(spc)
    try:
        strings = _draw(app, size).strings
        assert {"Conv start", "Background VV (∥)", "Apply →", "IRF files (this detector)"} <= set(
            strings
        )
        cut = []
        original = im.button

        def button(text, *a, **k):  # rects are clipped to the dock: compare with the natural width
            pressed = original(text, *a, **k)
            natural = (
                im.calc_text_size(str(text).split("##")[0])[0] + 2 * im.get_style().frame_padding[0]
            )
            if im.get_item_rect()[2] < natural - 1.0:
                cut.append(text)
            return pressed

        monkeypatch.setattr(im, "button", button)
        _draw(app, size, n=1)
        assert not cut, cut
        bx, by, bw, bh = app.item_rects["controls"]  # and every toolbar button inside the dock
        for key in (
            "guide",
            "help",
            "open_source",
            "refresh",
            "add_irf",
            "database_irf",
            "remove_irf",
            "clear_irf",
        ):
            x, y, w, h = app.item_rects[key]
            assert x + w <= bx + bw + 0.5, (key, x + w, bx + bw)
    finally:
        app.close()


def test_settings_round_trip(spc):
    app = _loaded(spc)
    state = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(state)
    assert other.export_settings() == state
    assert other.model.sel_conv_start == 500 and other.model.sel_irf_files == [spc]


def test_help_opens_with_its_page():
    app = make_app()
    app.help.show()
    assert app.help.open and len(_draw(app).strings) > 10


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("img_calibration")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("img_calibration")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
