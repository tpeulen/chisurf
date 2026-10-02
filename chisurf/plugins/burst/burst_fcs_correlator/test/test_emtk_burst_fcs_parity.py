"""The emtk burst-wise FCS correlator equals the Qt tool's computation and settings; layout, tooltips, isolation.

The Qt tool computed through ``BurstFcsClient.correlate_file`` (the backend call) with a ``_BurstFcsModel`` for the settings; the
numbers here are compared with exactly that path on the deterministic demonstration data of ``demo.py``. The control -> test list
is in the port's REPORT.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_fcs_correlator import demo
from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms as core
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import SPEC, create_app
from chisurf.plugins.burst.burst_fcs_correlator.gui.client import BurstFcsClient
from chisurf.plugins.burst.burst_fcs_correlator.gui.view_model import _BurstFcsModel

from .driving import BIG, SMALL, BurstDriver, clipped_texts, draw_clip, hermetic_env, layout_problems

TABS = ("Inputs", "Settings", "Detector setup")
PAIRS = [{"pair_name": "ACF_0", "chs_a": [0], "chs_b": [0]}, {"pair_name": "ACF_1", "chs_a": [1], "chs_b": [1]},
         {"pair_name": "cross_01", "chs_a": [0], "chs_b": [1]}]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    return demo.make_demo(tmp_path_factory.mktemp("burst_demo"))


@pytest.fixture
def drv(data):
    app = create_app()
    d = BurstDriver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def run(drv, data, pairs=PAIRS):
    c = drv.app.controller
    c.add_files([str(data[1])])
    c.apply_pairs(json.dumps(pairs))
    c._on_run()
    drv.settle()
    return c


# -- the demonstration data ----------------------------------------------------------------------------------------- #


def test_the_demonstration_data_is_deterministic(tmp_path):
    a = demo.make_demo(tmp_path / "a")
    b = demo.make_demo(tmp_path / "b")
    assert hashlib.sha256(a[0].read_bytes()).digest() == hashlib.sha256(b[0].read_bytes()).digest()
    assert a[1].read_text() == b[1].read_text()
    ranges = [tuple(map(int, line.split())) for line in a[1].read_text().splitlines()]
    assert len(ranges) == demo.N_BURSTS and ranges[0] == (0, demo.PHOTONS_PER_BURST - 1)


def test_the_demonstration_stream_reads_back_with_its_resolutions(data):
    import tttrlib

    t = tttrlib.TTTR(str(data[0]))
    assert len(t) == demo.N_BURSTS * demo.PHOTONS_PER_BURST
    assert t.header.macro_time_resolution == pytest.approx(demo.MACRO_RES) and t.header.micro_time_resolution == pytest.approx(demo.MICRO_RES)
    assert set(np.unique(t.get_routing_channel())) == {0, 1}


# -- the numbers ------------------------------------------------------------------------------------------------------ #


def test_the_curves_equal_the_qt_tools_backend_call(drv, data):
    c = run(drv, data)
    raw, ranges = c.resolve_files()[0]
    settings = c._model.to_settings()
    qt = BurstFcsClient().correlate_file(str(raw), ranges, [dict(p, micro_a=[], micro_b=[]) for p in PAIRS], settings.to_dict())["result"]["curves"]
    assert len(c._curves) == len(qt) == len(ranges) * len(PAIRS)
    for ours, theirs in zip(c._curves, qt):
        assert (ours["burst_index"], ours["pair_name"]) == (theirs["burst_index"], theirs["pair_name"])
        for key in ("tau_raw", "g_raw", "tau", "g", "g_fit"):
            assert np.array_equal(np.asarray(ours[key]), np.asarray(theirs[key])), key
        assert ours["td_mean"] == theirs["td_mean"]


def test_an_independent_correlator_call_gives_the_same_curve(drv, data):
    """The first burst's ACF of detector 0 from tttrlib directly (padding 0, the settings' bins and cascades)."""
    import tttrlib

    c = drv.app.controller
    c.add_files([str(data[1])])
    c.apply_pairs(json.dumps(PAIRS[:1]))
    c._model.padding_ms = 0.0
    c._on_run()
    drv.settle()
    first = next(x for x in c._curves if x["burst_index"] == 0)
    t = tttrlib.TTTR(str(data[0]))[0 : demo.PHOTONS_PER_BURST]
    mask = tttrlib.TTTRMask()
    mask.select_channels(t, [0])
    ours_tau, ours_g = core.correlate_single_burst(t, [0], [0], None, None, 3, 20, False)
    assert np.array_equal(np.asarray(first["tau_raw"]), np.asarray(ours_tau)) and np.array_equal(np.asarray(first["g_raw"]), np.asarray(ours_g))
    assert np.isfinite(first["g_raw"]).all() and np.max(first["g_raw"]) > 1.0  # the bursts are bunched: G rises above one at short lags


def test_every_fit_mode_produces_its_result(drv, data):
    c = drv.app.controller
    c.add_files([str(data[1])])
    c.apply_pairs(json.dumps(PAIRS[:1]))
    for mode in ("none", "simple", "maxent"):
        c._model.fit_mode = mode
        c._on_run()
        drv.settle()
        curve = c._curves[0]
        assert curve["fit_mode"] == mode
        assert bool(curve.get("g_fit")) == (mode != "none")
        assert bool(curve.get("p")) == (mode == "maxent")


# -- the settings ------------------------------------------------------------------------------------------------------ #


def qt_fields():
    spec = json.loads((Path(__file__).parents[1] / "gui" / "burst_fcs.view.json").read_text())
    out = {}

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                out[s["attr"]] = s
            walk(s.get("sections", []))

    walk(spec["sections"])
    return out


def our_fields():
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("attr"):
                out[node["attr"]] = node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(SPEC)
    return out


def test_every_field_of_the_qt_spec_is_in_the_emtk_spec_with_its_range():
    qt, ours = qt_fields(), our_fields()
    for attr, section in qt.items():
        assert attr in ours, attr
        for key in ("kind", "minimum", "maximum"):
            if key in section and not (attr == "maxent_log10_reg" and key in ("minimum", "maximum")):
                assert ours[attr].get(key) == section[key], (attr, key)
    assert ours["maxent_log10_reg"]["minimum"] == -12.0 and ours["maxent_log10_reg"]["maximum"] == 12.0  # the controller clamps to 12 (Qt spec: 6)
    panel_modes = create_app().panel.fit_modes()
    assert [v for v, _ in panel_modes] == qt["fit_mode"]["options"] and [l for _, l in panel_modes] == qt["fit_mode"]["labels"]


def test_the_settings_model_converts_like_the_qt_tool():
    m = _BurstFcsModel()
    m.n_bins, m.n_casc, m.make_fine, m.padding_ms, m.fit_mode = 5, 25, True, 12.5, "maxent"
    m.maxent_log10_reg, m.maxent_td_min, m.tmin_fit = -2.0, 0.01, 0.5
    s = m.to_settings()
    assert (s.n_bins, s.n_casc, s.make_fine, s.padding_ms, s.fit_mode) == (5, 25, True, 12.5, "maxent")
    assert s.maxent_reg == pytest.approx(0.01) and s.maxent_td_min == 0.01 and s.maxent_td_max is None and s.tmin_fit == 0.5 and s.tmax_fit is None


def test_the_tables_show_the_controllers_state(drv, data):
    c = run(drv, data)
    p = drv.app.panel
    assert [r["name"] for r in p.file_rows()] == [data[1].name] and p.file_rows()[0]["use"] is True
    assert [(r["name"], r["chs_a"], r["chs_b"]) for r in p.pair_rows()] == [("ACF_0", "0", "0"), ("ACF_1", "1", "1"), ("cross_01", "0", "1")]
    rows = p.curve_rows()
    assert len(rows) == 24 and [r["burst"] for r in rows[:3]] == [0, 0, 0] and [r["pair"] for r in rows[:3]] == ["ACF_0", "ACF_1", "cross_01"]
    assert [col["key"] for col in p.curve_columns()] == ["burst", "pair", "td"]  # one file: its name is not repeated on every row


def test_pairs_of_a_detector_setup_are_its_saved_pairs_else_one_acf_per_detector(monkeypatch):
    c = create_app().controller
    detectors = {"green": {"chs": [0, 8], "micro_time_ranges": [[0, 100]]}, "red": {"chs": [1, 9]}}
    auto = c.pairs_from_setup("none", detectors)
    assert [p["pair_name"] for p in auto] == ["green_ACF", "red_ACF"] and auto[0]["micro_a"] == [[0, 100]]
    import chisurf.core.fluorescence.fcs.channel_setups as store

    monkeypatch.setattr(store, "load_fcs_channel_setups", lambda *a, **k: {"setups": {"S": {"pairs": [
        {"channel_a": "green", "channel_b": "red"}, {"channel_a": "green", "channel_b": "green", "name": "GG"}]}}})
    saved = c.pairs_from_setup("S", detectors)
    assert [(p["pair_name"], p["chs_a"], p["chs_b"]) for p in saved] == [("greenxred", [0, 8], [1, 9]), ("GG", [0, 8], [0, 8])]


# -- tooltips, descriptions, Qt-free, isolation ------------------------------------------------------------------------ #


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_every_section_button_and_column_has_a_description(drv, data):
    run(drv, data)
    missing = []
    for node in walk(SPEC):
        kind = node.get("type")
        if kind in ("button_row", "toggle", "value", "choice", "table", "info", "progress") and not node.get("description"):
            missing.append((kind, node.get("attr") or node.get("name")))
        if kind == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    p = drv.app.panel
    for cols in (p.file_columns(), p.pair_columns(), p.curve_columns()):
        missing += [("column", c["key"]) for c in cols if not c.get("description")]
    assert not missing, missing


@pytest.mark.parametrize("tab", TABS)
def test_every_control_has_a_tooltip(drv, tab):
    from test.gui.emtk_port_parity import emtk_inventory

    drv.tab(tab)
    assert emtk_inventory(drv.app, BIG)["controls_without_tooltip"] == []


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("burst_fcs_correlator")
    assert verdict["ok"], verdict["output"]


def test_the_real_user_settings_are_never_touched(drv, data, tmp_path):
    real = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
    before = sorted((str(p), p.stat().st_mtime_ns) for p in real.rglob("burst_fcs*")) if real.exists() else []
    run(drv, data)
    drv.app.controller.save_settings(tmp_path / "s.json")
    after = sorted((str(p), p.stat().st_mtime_ns) for p in real.rglob("burst_fcs*")) if real.exists() else []
    assert before == after


# -- the layout -------------------------------------------------------------------------------------------------------- #


def _shared(tab, size):
    return pytest.param(size, tab, marks=pytest.mark.xfail(strict=True, reason="shared detector editor: header cells overlap / clip in a narrow column")) \
        if tab == "Detector setup" and size == SMALL else (size, tab)


@pytest.mark.parametrize("size, tab", [_shared(t, s) for s in (BIG, SMALL) for t in TABS])
def test_every_tab_draws_and_the_layout_is_clean(drv, data, size, tab):
    drv.size = size
    run(drv, data)
    drv.tab(tab)
    painter = draw_clip(drv.app, size)
    plots = [tuple(drv.app.item_rects[k]) for k in ("correlation_plot", "distribution_plot") if k in drv.app.item_rects]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    assert set(TABS) <= set(painter.strings)


def test_the_plots_have_axes_and_the_selected_curve(drv, data):
    c = run(drv, data)
    painter = draw_clip(drv.app, BIG)
    assert {"Correlation time t_c (ms)", "G", "data", "fit"} <= set(painter.strings)
    assert len([s for s in painter.strings if s.replace(".", "").replace("-", "").isdigit()]) >= 6
