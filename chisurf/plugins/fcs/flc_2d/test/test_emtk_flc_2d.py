"""The native flc-2d port: model, spec, drawing, workflow, no Qt."""

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
REAL_STREAM = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

#: A 10 s simulated two-state stream (seed 1, the plugin's own simulator, taus 1/3 ns,
#: k12 30, k21 10) through the default NNLS run with the 1D-MEM on. Taken from the Qt tool
#: (``FlcTwoDTool._on_simulate`` then ``_on_run``) before its work moved into the model.
SHORT = dict(
    n_photons=199717,
    tmax_ns=12.508,
    spectrum_sum=65726.62155920308,
    spectrum_shape=(32, 32),
    residual_abs_sum=2006808.3147592419,
    tau=[0.3, 0.6962324531720666, 1.615798762833313, 8.0],  # grid points 0, 10, 20, 39
    amp=[3.3212772022186057, 10.232069737980911, 23.748930511678953, 0.0],  # points 5, 15, 25, 35
    lcurve_corner=7,
    lcurve_residual_3=77.29749431033059,
    mem_sum=3109.5190791496216,
)

#: The same simulator for 60 s: the species correlation and the rate fit exist. The
#: ground truth is relaxation 40/s (25 ms); the analysis measures 34.5/s, as the Qt tool did.
LONG = dict(
    n_photons=1200718,
    rate_sum=34.48251307,
    relaxation_s=0.02900021,
    status="tau = 0.90, 3.17 ns; relaxation 29.0 ms (k12+k21=34.5/s)",
    series=["auto 0", "auto 1", "cross 0-1"],
)


def settle(app, size=(1200, 800), limit=180.0):
    """Draw frames until the app's worker is done (the job is polled inside ``render``)."""
    start = time.time()
    while app.job.busy and time.time() - start < limit:
        time.sleep(0.02)
        app.draw(RecordingPainter(), 0, 0, *size)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, *size)
    assert not app.job.busy


def run_through_app(app, sim_time_s, mem=False, size=(1200, 800)):
    """Press Sim and Run the way the buttons do (``model.request_*``) and wait for each."""
    app.model.sim_time_s = sim_time_s
    app.model.run_1d_mem = mem
    app.model.request_simulate()
    settle(app, size)
    assert not app.model.error_text, app.model.error_text
    app.model.request_run()
    settle(app, size)
    assert not app.model.error_text, app.model.error_text


@pytest.fixture(scope="module")
def short_app():
    """An app that simulated and analysed the 10 s stream (1D-MEM on)."""
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    run_through_app(app, 10.0, mem=True)
    return app


@pytest.fixture(scope="module")
def long_app():
    """An app that simulated and analysed the 60 s stream (dynamics, default settings)."""
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    run_through_app(app, 60.0)
    return app


# 1. the model does the science without any GUI
def test_model_produces_the_reference_result(short_app, long_app):
    m = short_app.model
    assert m.tttr.n_photons == SHORT["n_photons"]
    assert m.tmax_ns == SHORT["tmax_ns"]
    assert m.spectrum_image().shape == SHORT["spectrum_shape"]
    assert np.isclose(m.spectrum_image().sum(), SHORT["spectrum_sum"], rtol=1e-6)
    assert np.isclose(np.abs(m.residual_image()).sum(), SHORT["residual_abs_sum"], rtol=1e-6)
    tau, amp = m._lifetime["tau"], m._lifetime["amp"]
    assert np.allclose(tau[[0, 10, 20, 39]], SHORT["tau"], rtol=1e-9)
    assert np.allclose(amp[[5, 15, 25, 35]], SHORT["amp"], rtol=1e-6)
    lcurve = m.lcurve_data()
    assert lcurve.corner_index == SHORT["lcurve_corner"]
    assert np.isclose(lcurve.residual_norm[3], SHORT["lcurve_residual_3"], rtol=1e-6)
    assert np.isclose(m._mem1d["amp"].sum(), SHORT["mem_sum"], rtol=1e-6)
    assert "gauss" in m._mem1d
    assert [s["name"] for s in m.irf_series()] == ["decay", "IRF"]
    # the 60 s stream: species correlation and the interconversion fit
    long = long_app.model
    assert long.tttr.n_photons == LONG["n_photons"]
    assert [s["name"] for s in long.correlation_series()] == LONG["series"]
    assert np.isclose(long.kinetics.relaxation_rates[0], LONG["rate_sum"], rtol=1e-6)
    assert np.isclose(long.kinetics.relaxation_times_s[0], LONG["relaxation_s"], rtol=1e-6)
    assert long.status_text == LONG["status"]


def test_model_matches_the_qt_tool(short_app, qapp, qtbot):
    """The Qt tool, which now delegates to the same model, gives the same arrays."""
    from chisurf.plugins.fcs.flc_2d.gui.tool import FlcTwoDTool

    tool = FlcTwoDTool()
    qtbot.addWidget(tool)
    tool._model.sim_time_s = 10.0
    tool._model.run_1d_mem = True
    tool._on_simulate()
    assert tool._tttr.n_photons == SHORT["n_photons"]
    tool._on_run()
    ours, theirs = short_app.model, tool._model
    assert np.array_equal(ours.spectrum_image(), theirs.spectrum_image())
    assert np.array_equal(ours.residual_image(), theirs.residual_image())
    assert np.array_equal(ours._lifetime["amp"], theirs._lifetime["amp"])
    assert ours.lcurve_data().corner_index == theirs.lcurve_data().corner_index
    assert np.array_equal(ours._mem1d["amp"], theirs._mem1d["amp"])
    assert tool.statusBar().currentMessage() == theirs.status_text


# 2. the model's actions
def test_actions_change_state_and_report_errors(tmp_path):
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    model = app.model
    events = []
    model.add_observer(events.append)
    assert not model.enabled("request_run")  # no stream yet
    assert model.enabled("request_open") and model.enabled("request_simulate")
    model.request_open()
    assert model.dialog == "open_tttr"
    model.dialog = ""
    model.request_open_irf()
    assert model.dialog == "open_irf"
    model.dialog = ""
    model.request_run()  # the app turns the announcement into work; with no stream it does nothing
    settle(app)
    assert "start_run" in events and model.spectrum_image() is None
    model.run()  # no stream: a no-op, not an exception
    assert model.spectrum_image() is None
    # a file that is not there: a readable error, the state is untouched
    with pytest.raises(RuntimeError, match="not found"):
        model.open_tttr(str(tmp_path / "missing.ptu"))
    assert model.tttr is None
    app._dialog_done("open_tttr", [str(tmp_path / "missing.ptu")])
    settle(app)
    assert "not found" in model.error_text and model.status_line() == model.error_text
    assert model.tttr is None
    # the app's Open for a real file works and clears the error
    copy = Path(shutil.copy(REAL_STREAM, tmp_path / "stream.spc"))
    app._dialog_done("open_tttr", [str(copy)])
    settle(app)
    assert model.error_text == "" and model.tttr is not None
    assert model.folder == str(tmp_path)
    assert model.enabled("request_run")
    # everything is greyed while a worker runs
    model.busy = True
    assert not model.enabled("request_run") and not model.enabled("request_simulate")
    model.busy = False
    # an unusable IRF file is an error, the IRF mode is not switched
    with pytest.raises(RuntimeError):
        model.open_irf(str(tmp_path / "no_irf.ptu"))
    assert model.irf_mode == "synthetic"


# 3. spec and model agree
def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.fcs.flc_2d.gui.model import FlcModel

    spec = json.loads((GUI / "flc_2d_emtk.view.json").read_text())
    model = FlcModel()

    def walk(sections):
        for s in sections:
            for key in ("attr", "source", "target"):
                if s.get(key):
                    assert hasattr(model, s[key]), s[key]
            if s.get("call"):
                assert callable(getattr(model, s["call"])), s["call"]
            for b in s.get("buttons", []):
                assert callable(getattr(model, b["action"])), b["action"]
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_custom_sections_are_all_drawn_by_the_app():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    spec = json.loads((GUI / "flc_2d_emtk.view.json").read_text())
    keys = set()

    def walk(sections):
        for s in sections:
            if s.get("type") == "custom":
                keys.add(s["key"])
            walk(s.get("sections", []))

    walk(spec["sections"])
    assert keys == {"image", "series_plot", "lcurve"}
    assert keys <= set(app.form.custom)


def test_the_spec_keeps_every_qt_field():
    """Every field of the Qt spec is in the native one, with the same attribute and range."""
    qt = json.loads((GUI / "flc_2d.view.json").read_text())
    native = json.loads((GUI / "flc_2d_emtk.view.json").read_text())

    def fields(node, out):
        for s in node:
            if s.get("attr"):
                out[s["attr"]] = (
                    s.get("kind"),
                    s.get("minimum"),
                    s.get("maximum"),
                    s.get("options"),
                )
            fields(s.get("sections", []), out)
        return out

    assert fields(qt["sections"], {}) == fields(native["sections"], {})
    assert len(fields(qt["sections"], {})) == 29


# 4. the app draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_empty_and_populated(size, short_app):
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    empty = make_app()
    painter = RecordingPainter()
    for _ in range(3):
        painter = RecordingPainter()
        empty.draw(painter, 0, 0, *size)
    assert any("Open a TTTR file to begin." in s for s in painter.strings)
    for title in ("Settings", "2D-FLCS map", "L-curve", "IRF"):
        assert any(title in s for s in painter.strings), title
    # the populated app: every result window, in front in turn
    seen = {}
    for key, expect in (
        ("settings", "Lifetime inversion"),
        ("spectrum_image", "Colormap"),
        ("residual_image", "Colormap"),
        ("lifetime_series", "1D-MEM"),
        ("correlation_series", "lag t_c (s)"),
        ("lcurve_data", "chosen"),
        ("irf_series", "IRF"),
    ):
        short_app.docks.focus(key)
        for _ in range(3):
            painter = RecordingPainter()
            short_app.draw(painter, 0, 0, *size)
        seen[key] = any(expect in s for s in painter.strings)
    assert all(seen.values()), seen
    assert any(short_app.model.status_text in s for s in painter.strings)


# 5. the workflow through the UI path
def test_main_action_end_to_end(tmp_path):
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    # a real measurement opened by dropping it on the window (a temp copy: the run is read-only
    # but the repository's test data is never the working copy)
    copy = Path(shutil.copy(REAL_STREAM, tmp_path / "BH_SPC132.spc"))
    app.on_paths_dropped([str(copy)])
    settle(app)
    m = app.model
    assert m.tttr is not None and m.tttr.n_photons == 183657
    assert m.tttr_path == str(copy)
    assert m.tmax_ns == 13.5  # 4096 channels x 3.2959 ps, set from the file
    assert m.status_text.startswith("Loaded BH_SPC132.spc: 183,657 photons")
    m.request_run()
    settle(app)
    assert not m.error_text, m.error_text
    assert m.spectrum_image().shape == (32, 32)
    assert m.status_text == "Resolved lifetimes: tau = 8.00 ns"
    assert m.lifetime_series() and m.irf_series()
    # opening an IRF switches the IRF source to the file, and the run then uses it
    irf_copy = Path(shutil.copy(REAL_STREAM, tmp_path / "irf.spc"))
    app._dialog_done("open_irf", [str(irf_copy)])
    settle(app)
    assert m.irf_mode == "file" and m.irf_file.size == 4096
    assert m.status_text.startswith("Loaded IRF from irf.spc")
    m.request_run()
    settle(app)
    assert m.irf is not None and m.irf.size == 4096 and not m.error_text
    # the simulator path: a known answer, the model arrays feed the plots
    run_through_app(app, 10.0)
    assert m.tttr_path is None and m.tttr.n_photons == SHORT["n_photons"]
    series = m.lifetime_series()
    assert series[0]["name"] == "lifetime distribution"
    assert m.lcurve_data() is not None


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("flc-2d")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("flc-2d"))
    assert inv["controls_without_tooltip"] == []
    spec = json.loads((GUI / "flc_2d_emtk.view.json").read_text())

    def walk(sections):
        for s in sections:
            if s.get("type") in (
                "value",
                "choice",
                "toggle",
                "table",
                "data_table",
                "custom",
                "info",
                "button_row",
                "panel",
            ):
                assert s.get("description"), s.get("attr") or s.get("title") or s
            for c in s.get("columns", []):
                assert c.get("description"), c
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


# 8. persistence round trip
def test_settings_round_trip():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    m = app.model
    m.dT_ms, m.ddT_ms, m.max_bins = 7.5, 3.25, 64
    m.fit_mode, m.irf_mode, m.log10_reg = "mem", "detect", -2.5
    m.run_1d_mem, m.compute_dynamics, m.mem_mi_type = True, False, 2
    m.sim_k12, m.sim_time_s, m.colormap = 55.0, 12.0, "gray"
    m.folder = "/data/flc"
    state = json.loads(json.dumps(app.export_settings()))  # plain JSON
    other = make_app()
    other.restore_settings(state)
    o = other.model
    assert (o.dT_ms, o.ddT_ms, o.max_bins) == (7.5, 3.25, 64)
    assert (o.fit_mode, o.irf_mode, o.log10_reg) == ("mem", "detect", -2.5)
    assert o.run_1d_mem is True and o.compute_dynamics is False and o.mem_mi_type == 2
    assert (o.sim_k12, o.sim_time_s, o.colormap, o.folder) == (55.0, 12.0, "gray", "/data/flc")
    # unusable entries are ignored, not raised
    other.restore_settings({"dT_ms": "not a number", "max_bins": None, "folder": None})
    assert other.model.dT_ms == 7.5 and other.model.max_bins == 64 and other.model.folder == ""


# guide and help
def test_guide_targets_are_reachable_and_tour_waits_for_outcomes():
    from chisurf.plugins.fcs.flc_2d.gui.app import WINDOW_KEYS, make_app

    app = make_app()
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    assert len(steps) == 8
    tour = app.tour
    titles = {w["title"] for w in app.windows}
    # every target is a spec field, a toolbar button (Sim, Run), or a window's title
    known = set(app._settings_keys) | titles | {"Sim", "Run", "IRF", "Open"}
    keys = [tour._target_key(s.get("target")) for s in steps if tour._target_key(s.get("target"))]
    assert [k for k in keys if k not in known] == []
    # each step, in turn, finds a rect for its target after the tour brought the window forward
    for i, step in enumerate(steps):
        key = tour._target_key(step.get("target"))
        tour.start(i)
        for _ in range(4):
            app.draw(RecordingPainter(), 0, 0, 1200, 800)
        if key:
            assert app.item_rects.get(key) or app.form.rects.get(key), (i, key)
    tour.stop()
    assert len(WINDOW_KEYS) == len(app.windows) == 8
    # the Sim step waits for the stream to be there, not for the press alone
    sim_step = next(i for i, s in enumerate(steps) if tour._target_key(s.get("target")) == "Sim")
    tour.start(sim_step)
    assert tour.awaiting
    app.model.sim_time_s = 1.0
    app.model.request_simulate()
    assert tour.awaiting
    settle(app)
    assert not tour.awaiting
    # the step texts name controls of this app (no emoji labels, no Qt toolbar)
    text = json.dumps(steps, ensure_ascii=False)
    assert "📈" not in text and "QAction" not in text


def test_help_window_shows_from_the_button():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    app.model.request_help()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    assert any("2D-FLCS" in s for s in painter.strings)
    app.model.request_guide()
    assert app.tour.active
