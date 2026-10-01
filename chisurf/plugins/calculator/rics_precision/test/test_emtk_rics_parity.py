"""The native RICS-precision app at parity with the Qt tool (AutoForm over the same view model).

Reference numbers: the Qt tool as committed (HEAD ``gui/tool.py``,
``okf/plugins/emtk-ports/rics_precision/scripts/capture_qt.py``) with n_repeats=10, n_images=20
and every other setting at its default (seed 1) printed the nine rows, the verdict and the CSV
pinned below; its failure for ``n_lags=15`` on an 8x8 image printed the message pinned below.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import implot
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.rics_precision import core
from chisurf.plugins.calculator.rics_precision.gui import app as app_module
from chisurf.plugins.calculator.rics_precision.gui.app import RicsPrecisionApp, finite_runs, make_app
from chisurf.plugins.calculator.rics_precision.gui.view_model import PrecisionViewModel

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

QT_ROWS = [
    {"dwell": "0.5", "line": "0.0384", "error": "314.8", "frame": "2.46"},
    {"dwell": "1.19", "line": "0.0911", "error": "45.8", "frame": "5.83"},
    {"dwell": "2.81", "line": "0.216", "error": "12.1", "frame": "13.8"},
    {"dwell": "6.67", "line": "0.512", "error": "8.5", "frame": "32.8"},
    {"dwell": "15.8", "line": "1.21", "error": "4.5", "frame": "77.7"},
    {"dwell": "37.5", "line": "2.88", "error": "6.3", "frame": "184"},
    {"dwell": "88.9", "line": "6.83", "error": "10.1", "frame": "437"},
    {"dwell": "211", "line": "16.2", "error": "18.3", "frame": "1.04e+03"},
    {"dwell": "500", "line": "38.4", "error": "9.8", "frame": "2.46e+03"},
]
QT_STATUS = "At 8 µs: 7.3 % error (usable) — about 1.7x worse than the best dwell (15.8 µs)."
QT_CSV = (
    "dwell_us,line_ms,frame_ms,error_percent\n0.5,0.0384,2.46,314.8\n1.19,0.0911,5.83,45.8\n"
    "2.81,0.216,13.8,12.1\n6.67,0.512,32.8,8.5\n15.8,1.21,77.7,4.5\n37.5,2.88,184,6.3\n"
    "88.9,6.83,437,10.1\n211,16.2,1.04e+03,18.3\n500,38.4,2.46e+03,9.8\n"
)
QT_FAILURE = (
    "Prediction failed: n_lags=15 is too large for a 8x8 image: the covariance needs "
    "2 * n_lags < min(nx, ny), so at most n_lags=3"
)


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _settle(app, limit=120.0):
    """Draw frames, as the host does, until the sweep has finished."""
    t0 = time.time()
    while app.job.busy and time.time() - t0 < limit:
        if app.job.thread is not None:
            app.job.thread.join(timeout=0.2)
        _draw(app, times=1)
    _draw(app, times=1)
    assert not app.job.busy


def _small(app):
    app.model.n_repeats, app.model.n_images = 10, 20


@pytest.fixture
def app():
    app = RicsPrecisionApp()
    yield app
    app.close()


# 1. Predict gives the Qt tool's rows, verdict and CSV
def test_predict_gives_the_qt_tools_numbers(app, tmp_path):
    _small(app)
    assert app.model.enabled("request_predict")
    assert app.predict()
    _settle(app)
    assert app.model.sweep_rows() == QT_ROWS
    assert app.model.status == QT_STATUS and app.status_line() == QT_STATUS
    painter = _draw(app)
    for text in ("0.0384", "314.8", "1.04e+03", "Dwell [µs]", QT_STATUS):    # the table cells and the verdict
        assert text in painter.strings, text
    out = tmp_path / "sweep.csv"
    app.write_csv(out)
    assert out.read_text() == QT_CSV
    # the same through the button: the request is carried out by the next frame
    other = RicsPrecisionApp()
    _small(other)
    other.model.request_predict()
    _draw(other, times=1)
    _settle(other)
    assert other.model.sweep_rows() == QT_ROWS
    other.close()


# 2. the sweep is a worker: Predict is refused and greyed meanwhile, progress is on the status line
def test_a_running_sweep_is_shown_and_not_started_twice(app, monkeypatch):
    gate = threading.Event()
    real = core.sweep_dwell

    def slow(*args, progress=None, **kwargs):
        progress(0.5, "Sweeping dwell times")
        assert gate.wait(60)
        return real(*args, progress=progress, **kwargs)

    monkeypatch.setattr(core, "sweep_dwell", slow)
    _small(app)
    assert app.predict() is True
    assert app.predict() is False                                      # one sweep at a time
    t0 = time.time()
    while "50 %" not in app.status_line() and time.time() - t0 < 30:
        time.sleep(0.05)
        _draw(app, times=1)
    assert app.status_line() == "Sweeping dwell times (50 %)"
    assert app.model.busy and not app.model.enabled("request_predict")
    assert "Sweeping dwell times (50 %)" in _draw(app).strings
    assert app.continuous                                              # frames follow while it runs
    gate.set()
    _settle(app)
    assert app.model.sweep is not None and not app.model.busy
    assert app.model.enabled("request_predict") and app.model.status == QT_STATUS
    _draw(app, times=1)
    assert not app.continuous                                          # idle again


# 3. the failure paths: the Qt message, no stale curve, nothing to export
def test_a_bad_setting_is_reported_and_leaves_no_curve(app, tmp_path):
    _small(app)
    app.predict()
    _settle(app)
    assert app.model.sweep is not None
    app.model.nx, app.model.ny, app.model.n_lags = 8, 8, 15
    app.predict()
    _settle(app)
    assert app.model.status == QT_FAILURE and app.model.sweep is None
    assert app.model.sweep_rows() == [] and app.model.sweep_series() == []
    painter = _draw(app)
    assert any("Prediction failed: n_lags=15" in s for s in painter.strings)     # on screen, wrapped
    assert not app.start_export() and app.notice == "Predict something first." and app.dialog is None
    with pytest.raises(ValueError, match="Predict something before exporting"):
        app.write_csv(tmp_path / "x.csv")
    assert not (tmp_path / "x.csv").exists()


def test_a_sweep_with_no_realisable_dwell_is_reported(app, monkeypatch):
    real = core.sweep_dwell

    def all_nan(*args, **kwargs):
        sweep = real(*args, **kwargs)
        sweep.relative_error = np.full_like(np.asarray(sweep.relative_error, dtype=float), np.nan)
        return sweep

    monkeypatch.setattr(core, "sweep_dwell", all_nan)
    _small(app)
    app.predict()
    _settle(app)
    assert app.model.sweep is None
    assert app.model.status.startswith("Prediction failed: no dwell time is realisable")


def test_an_unexpected_error_in_the_worker_is_reported(app, monkeypatch):
    def boom(self):
        raise RuntimeError("worker broke")

    monkeypatch.setattr(PrecisionViewModel, "predict", boom)
    app.predict()
    _settle(app)
    assert app.model.status == "Prediction failed: worker broke" and not app.model.busy


# 4. Export CSV: before a prediction, the dialog, the suffix, the content, errors, cancel
def test_export_csv_paths(app, tmp_path):
    assert app.model.enabled("request_export")
    app.model.request_export()                                          # nothing predicted yet
    _draw(app, times=1)
    assert app.dialog is None and app.notice == "Predict something first."
    assert "Predict something first." in _draw(app).strings
    _small(app)
    app.predict()
    _settle(app)
    assert app.notice == ""
    app.model.request_export()
    _draw(app)
    assert app.dialog is not None and app.continuous
    app.dialog.draw = lambda: False                                      # Cancel
    _draw(app, times=1)
    assert app.dialog is None and not list(tmp_path.iterdir())
    app.start_export()
    _draw(app)
    chosen = tmp_path / "plan"                                           # no suffix: .csv is added
    app.dialog.draw = lambda: [str(chosen)]
    _draw(app, times=1)
    assert (tmp_path / "plan.csv").read_text() == QT_CSV
    assert app.notice == f"Wrote {tmp_path / 'plan.csv'}" and app.dialog is None
    assert any("Wrote" in s for s in _draw(app).strings)
    app.start_export()
    _draw(app)
    app.dialog.draw = lambda: [str(tmp_path / "plan.csv" / "x.csv")]     # the folder is a file
    _draw(app, times=1)
    assert app.notice.startswith("Could not write x.csv:") and app.dialog is None


# 5. the form is the Qt spec's: same fields, ranges, decimals, labels and descriptions
def _values(spec):
    found = {}

    def walk(sections, panel=""):
        for s in sections:
            if s.get("attr"):
                found[s["attr"]] = (s["type"], s.get("kind"), s.get("minimum"), s.get("maximum"),
                                    s.get("decimals"), s.get("label"), s.get("description"), panel)
            walk(s.get("sections", []), s.get("title", panel) if s.get("type") == "panel" else panel)

    walk(spec["sections"])
    return found


def test_the_form_has_the_qt_specs_fields():
    qt = json.loads((GUI / "precision.view.json").read_text(encoding="utf-8"))
    native = json.loads((GUI / "precision_emtk.view.json").read_text(encoding="utf-8"))
    assert _values(native) == _values(qt)
    assert len(_values(native)) == 15
    estimator = next(s for p in native["sections"][0]["sections"] if p.get("title") == "Estimator" for s in [p])
    assert estimator["collapsed"] is True                                # folded at first, as in Qt
    model = PrecisionViewModel()
    for attr in _values(native):
        assert hasattr(model, attr), attr


def test_the_estimator_panel_unfolds_and_draws_its_fields(app):
    assert "Lags fitted" not in _draw(app).strings
    app.form.folds["Estimator"] = True
    painter = _draw(app)
    for label in ("Lags fitted", "Repeats", "Seed"):
        assert label in painter.strings, label


# 6. persistence
def test_settings_round_trip():
    model = PrecisionViewModel()
    model.diffusion_coefficient, model.two_d, model.nx, model.n_lags = 42.5, True, 128, 6
    saved = json.loads(json.dumps(model.export_settings()))
    other = PrecisionViewModel()
    other.restore_settings(saved)
    assert other.export_settings() == model.export_settings()
    other.restore_settings({"nx": "not a number", "two_d": 0, "unknown": 1, "w_r": "0.5"})
    assert other.nx == 128 and other.two_d is False and other.w_r == 0.5
    a = RicsPrecisionApp()
    a.restore_settings(saved)
    assert a.export_settings() == saved
    a.close()


# 7. draws, empty / populated / failed, both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_populated_and_failed(app, size):
    painter = _draw(app, size)
    assert "Predict" in painter.strings and "Export CSV" in painter.strings
    assert app.model.status in painter.strings                          # the initial hint
    assert "Dwell [µs]" in painter.strings                              # the table header, no rows
    _small(app)
    app.predict()
    _settle(app)
    painter = _draw(app, size)
    assert "7.3 % error (usable)" in " ".join(painter.strings) and "314.8" in painter.strings   # the verdict may wrap
    app.model.nx = app.model.ny = 8
    app.model.n_lags = 15
    app.predict()
    _settle(app)
    assert any("Prediction failed" in s for s in _draw(app, size).strings)


# 8. the curve is a line through its points, with gaps where a dwell is not realisable
def test_the_curve_is_drawn_as_a_line_and_your_setting_as_a_marker(app, monkeypatch):
    _small(app)
    app.predict()
    _settle(app)
    lines, scatters = [], []
    monkeypatch.setattr(implot, "plot_line", lambda label, x, y, *a, **k: lines.append((label, len(x))))
    monkeypatch.setattr(implot, "plot_scatter", lambda label, x, y, *a, **k: scatters.append((label, len(x))))
    _draw(app, times=1)
    assert lines == [("predicted error", 9)]                            # connected, all nine points
    assert scatters == [("your setting", 1)]


def test_finite_runs_split_at_gaps():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    y = np.array([1.0, 2.0, np.nan, 4.0, 0.0, 6.0])                     # a NaN and a point log axes cannot show
    runs = finite_runs(x, y)
    assert [(list(a), list(b)) for a, b in runs] == [([1.0, 2.0], [1.0, 2.0]), ([4.0], [4.0]), ([6.0], [6.0])]
    assert finite_runs(x, np.full(6, np.nan)) == []


# 9. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("rics_precision")
    assert result["ok"], result["output"]


# 10. tooltips: recorded controls plus every spec section, button and table column
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("rics_precision")
    app.form.folds["Estimator"] = True
    inv = emtk_inventory(app)
    assert inv["controls_without_tooltip"] == []
    spec = json.loads((GUI / "precision_emtk.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            assert s.get("description"), s.get("attr") or s.get("title") or s
            for c in (s.get("options") or {}).get("columns", []):
                assert c.get("tooltip"), c
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


# 11. every attr, call, action and source of the spec is on the model
def test_the_spec_names_exist_on_the_model():
    model = PrecisionViewModel()
    spec = json.loads((GUI / "precision_emtk.view.json").read_text(encoding="utf-8"))
    missing = []

    def walk(sections):
        for s in sections:
            for key in ("attr", "call", "source"):
                if s.get(key) and not hasattr(model, s[key]):
                    missing.append((key, s[key]))
            for key in ("source", "selected_call", "delete_call"):
                name = (s.get("options") or {}).get(key)
                if name and not hasattr(model, name):
                    missing.append((key, name))
            for b in s.get("buttons", []):
                if not hasattr(model, b["action"]):
                    missing.append(("action", b["action"]))
            walk(s.get("sections", []))

    walk(spec["sections"])
    assert missing == []


# 12. help and guide: the tour waits for the controls it names
def test_guide_waits_for_the_user_and_points_at_drawn_controls(app):
    tour = app.tour
    assert tour.wait_for_controls and len(tour.steps) >= 5 and any(s.get("await") for s in tour.steps)
    _small(app)
    app.predict()
    _settle(app)
    _draw(app)
    for step in tour.steps:
        key = tour._target_key(step["target"])
        if key:
            assert key in app.item_rects or key in app.form.rects, step["title"]
    tour.start(1)
    assert tour.awaiting and tour.steps[1]["target"] == {"attr": "diffusion_coefficient"}
    tour.notify_used("request_predict")                                  # another control: still waiting
    assert tour.awaiting
    app.form.on_used("diffusion_coefficient")                            # what the form reports on a commit
    assert not tour.awaiting
    predict_step = next(i for i, s in enumerate(tour.steps) if s["target"] == {"action": "request_predict"})
    tour.start(predict_step)
    assert tour.awaiting
    app.form.on_used("request_predict")
    assert not tour.awaiting
    app.show_help()
    _draw(app)
    assert app.help_window.open
    assert (GUI / "help.md").stat().st_size > 400


# 13. the factory the manifest names, and the hub's embedding keep working
def test_make_app_and_write_csv_before_a_prediction(tmp_path):
    app = make_app(restore=False)
    with pytest.raises(ValueError, match="Predict"):
        app.write_csv(tmp_path / "precision.csv")
    assert callable(app.gui) and isinstance(app, RicsPrecisionApp)
    assert _draw(app, times=1).strings
    app.close()
