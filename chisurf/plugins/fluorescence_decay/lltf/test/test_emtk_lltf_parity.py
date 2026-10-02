"""The native Lazy Lifetime Analysis at parity with the Qt LLTFGUIWizard.

Both hosts run the LLTF command line in a subprocess, so parity is first the command:
the Qt wizard runs in a subprocess here (this process stays Qt-free) and the command
it builds is compared with the emtk model's for the same inputs and options. Then one
real fit of the shipped example is checked against the data itself (the starting
values are random, so two runs agree only to a tolerance -- a known issue), and the
two command-line defects the port fixed are pinned down: ``-n`` now wins over the
configuration's own ``find_optimal``, and no figure is shown on screen.
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
EXAMPLE = HERE.parent / "example"
DECAY, IRF, CONFIG = (str((EXAMPLE / n).resolve()) for n in ("5-44_D0.dat", "IRF_D0.dat", "config.yml"))
SPEC = json.loads((HERE.parent / "gui" / "lltf.view.json").read_text())

from chisurf.plugins.fluorescence_decay.lltf.gui.app import LLTFApp  # noqa: E402
from chisurf.plugins.fluorescence_decay.lltf.gui.model import LLTFModel  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=240.0):
    end = time.monotonic() + timeout
    while app.model.process is not None:
        assert time.monotonic() < end, "the fit did not finish"
        time.sleep(0.05)
        _draw(app, n=1)
    _draw(app, n=1)


def _loaded(output_dir, **options):
    app = LLTFApp()
    m = app.model
    m.decay_file, m.irf_file, m.output_dir = DECAY, IRF, str(output_dir)
    m.load_config(CONFIG)
    m.n_lifetimes = 2
    for key, value in options.items():
        setattr(m, key, value)
    return app


def _fields(sections):
    for section in sections:
        if section.get("attr"):
            yield section
        yield from _fields(section.get("sections", []))


_QT = r"""
import json, subprocess, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.gui import dialogs
from chisurf.plugins.fluorescence_decay.lltf import lltf_gui
decay, irf, config, out = sys.argv[1:5]
warned, launched = [], []
dialogs.warning = lambda parent, title, text, *a, **k: warned.append([title, text])

class FakePopen:                                       # record what the wizard would run, run nothing
    def __init__(self, cmd, **kwargs):
        launched.append({"cmd": cmd, "mpl": (kwargs.get("env") or {}).get("MPLBACKEND")})
        self.stdout = iter(())
        self.returncode = 0
    def poll(self):
        return 0
    def wait(self, timeout=None):
        return 0

lltf_gui.subprocess.Popen = FakePopen
w = lltf_gui.LLTFGUIWizard()
w.on_fit()                                             # nothing loaded
w.decay_file, w.irf_file, w.output_dir = decay, irf, out
w.config_file_edit.setText(config)
w.n_lifetimes_spin.setValue(2); w.verbose_check.setChecked(False)
w._update_fit_button_state()
fit_enabled = w.fit_button.isEnabled()
w.analysis_tab.running = False
w.on_fit()
w.analysis_tab.running = False
w.find_optimal_check.setChecked(True); w.max_lifetimes_spin.setValue(3); w.prob_threshold_spin.setValue(0.7)
greyed = [w.n_lifetimes_spin.isEnabled(), w.max_lifetimes_spin.isEnabled(), w.prob_threshold_spin.isEnabled()]
w.verbose_check.setChecked(True)
w.on_fit()
print("FACTS" + json.dumps({"warned": warned, "launched": launched, "fit_enabled": fit_enabled, "greyed": greyed}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    out = tmp_path_factory.mktemp("qt")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, DECAY, IRF, CONFIG, str(out)], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"the Qt wizard could not be built here: {proc.stderr[-800:]}")
    facts = json.loads(line[len("FACTS"):])
    facts["out"] = out
    return facts


def _without_config(cmd):
    cmd = list(cmd)
    i = cmd.index("-c")
    return cmd[:i] + cmd[i + 2:], cmd[i + 1]


# 1. the same command as the Qt wizard, fixed count and search; the subprocess never shows figures
def test_the_fit_command_is_the_qt_wizards(qt):
    fixed, search = qt["launched"]
    model = LLTFModel()
    model.decay_file, model.irf_file, model.output_dir = DECAY, IRF, str(qt["out"])
    model.n_lifetimes, model.verbose = 2, False
    ours, config = _without_config(model.build_command("EDITED.yml"))
    theirs, qt_config = _without_config(fixed["cmd"])
    assert ours[1:] == theirs[1:] and config == "EDITED.yml" and qt_config == CONFIG     # emtk runs the edited buffer
    model.find_optimal, model.max_lifetimes, model.prob_threshold, model.verbose = True, 3, 0.7, True
    assert _without_config(model.build_command("x"))[0][1:] == _without_config(search["cmd"])[0][1:]
    assert fixed["mpl"] == search["mpl"] == "Agg"                     # the wizard's subprocess: no screen figures
    assert qt["warned"] == [["Warning", "Please load decay and IRF data first."]]


# a real fit: the example's two components, a model that follows the data
@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    out = tmp_path_factory.mktemp("fit")
    app = _loaded(out)
    app.start()
    _settle(app)
    yield app, out
    app.close()


def test_a_fixed_count_fit_returns_that_count_and_follows_the_data(fitted):
    app, out = fitted
    result = app.model.result
    assert app.model.status == "LLTF fit completed."
    assert result["n_lifetimes"] == 2                                   # -n 2 beats the file's find_optimal: true
    assert "optimal_fitting" not in result
    taus = sorted(row["lifetime"] for row in result["lifetimes"])
    assert taus[1] == pytest.approx(3.90, abs=0.03) and 0.6 < taus[0] < 1.0
    assert sum(row["amplitude"] for row in result["lifetimes"]) == pytest.approx(1.0, abs=1e-6)
    assert 1.2 < result["reduced_chi_square"] < 1.6
    assert (out / "5-44_D0_fit.json").is_file() and (out / "5-44_D0_fit.png").is_file()
    a = app.arrays                                                      # the plotted model is the data's
    observed = np.genfromtxt(DECAY)[:, 1][result["time_range"]["start_idx"]:result["time_range"]["stop_idx"]]
    assert len(a["fit"]) == len(observed) and abs(float(np.mean(a["residuals"]))) < 0.2
    assert np.std(a["residuals"]) == pytest.approx(np.sqrt(result["reduced_chi_square"]), rel=0.05)


def test_the_results_panel_is_the_spec_table(fitted, monkeypatch):
    app, _ = fitted
    app.pending_tab = "Results"
    drawn = _draw(app).strings
    assert {"Component", "Amplitude", "Lifetime (ns)"} <= set(drawn)            # the spec's column headers
    strings = " ".join(drawn)
    rows = app.model.lifetime_rows()
    for row, fitted_row in zip(rows, app.model.result["lifetimes"]):     # against the fit result, not itself
        assert (row["lifetime"], row["amplitude"]) == (fitted_row["lifetime"], fitted_row["amplitude"])
        assert f"{fitted_row['lifetime']:.3f}" in strings and f"{fitted_row['amplitude']:.3f}" in strings
    assert len(rows) == len(app.model.result["lifetimes"])
    assert f"Reduced chi-square: {app.model.result['reduced_chi_square']:.3f}" in strings
    assert "Number of lifetimes: 2" in strings


def test_the_command_line_shows_no_figures_and_search_still_works(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "MPLBACKEND"}      # no Agg: the old CLI waited on plt.show()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    out = tmp_path / "search.json"
    proc = subprocess.run([sys.executable, "-m", "chisurf.plugins.fluorescence_decay.lltf.core", "fit", DECAY, IRF,
                           "-sp", str(tmp_path), "-o", str(out), "-c", CONFIG, "-f", "-m", "2"],
                          capture_output=True, text=True, timeout=180, env=env, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-500:]
    result = json.loads(out.read_text())
    assert result["optimal_fitting"]["n_lifetimes_tried"] == [1, 2]


# 2. actions and errors
def test_fit_needs_both_files_and_says_so(qt, tmp_path):
    app = LLTFApp()
    try:
        assert qt["fit_enabled"] is True
        _draw(app)
        assert app.error(app.start) is None
        assert app.model.status == "Error: Load existing decay and IRF files first."
        assert app.model.status in _draw(app).strings
        app.model.decay_file, app.model.irf_file = DECAY, IRF
        app.model.config_text = "- not\n- a mapping\n"
        app.model.config_dirty = True
        app.error(app.start)
        assert app.model.status == "Error: LLTF configuration must be a YAML mapping."
    finally:
        app.close()


def test_fit_cannot_be_pressed_without_files():
    app = LLTFApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        before = app.model.status
        x, y, w, h = app.item_rects["Fit"]
        app.pointer_move(x + w / 2, y + h / 2)
        app.press(x + w / 2, y + h / 2)
        _draw(app, size, n=1, painter=PixelPainter)
        app.release()
        _draw(app, size, n=1, painter=PixelPainter)
        assert app.model.status == before and app.model.process is None      # greyed, as the Qt Fit button was
    finally:
        app.close()


def test_the_options_grey_as_the_qt_wizard_greys_them(qt):
    m = LLTFModel()
    assert [m.enabled(n) for n in ("n_lifetimes", "max_lifetimes", "prob_threshold")] == [True, False, False]
    m.find_optimal = True
    assert [m.enabled(n) for n in ("n_lifetimes", "max_lifetimes", "prob_threshold")] == qt["greyed"] == [False, True, True]


def test_drops_route_data_config_and_folder(tmp_path):
    app = LLTFApp()
    try:
        app.on_paths_dropped([DECAY, IRF, CONFIG, str(tmp_path)])
        m = app.model
        assert (m.decay_file, m.irf_file, m.config_file, m.output_dir) == (DECAY, IRF, CONFIG, str(tmp_path))
    finally:
        app.close()


def test_the_config_editor_opens_on_the_file_and_saves_the_buffer(tmp_path):
    app = _loaded(tmp_path)
    try:
        app.edit_config()
        assert app.config_open and "find_optimal: true" in app.model.config_text
        strings = _draw(app).strings
        assert "Save configuration" in strings and "Close editor" in strings
        app.model.config_text = app.model.config_text.replace("find_optimal: true", "find_optimal: false")
        app.model.config_dirty = True
        app.model.save_config(str(tmp_path / "edited.yml"))
        assert "find_optimal: false" in (tmp_path / "edited.yml").read_text()
    finally:
        app.close()


# 3. one spec: every field drawn with its description
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    app = LLTFApp()
    try:
        _draw(app)
        fields = [f for f in _fields(SPEC["sections"])]
        assert {f["attr"] for f in fields} <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
    finally:
        app.close()


# guide: the Qt tour's targets are the emtk controls too; Load... and Fit wait for presses
def test_the_guide_points_at_real_controls_and_waits(tmp_path):
    app = LLTFApp()
    size = (1200, 800)
    try:
        _draw(app, size, painter=PixelPainter)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys == {"Load...", "Edit...", "Find Optimal", "Fit", "Results"} and keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        load = next(i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Load...")
        app.tour.start(load)
        assert app.tour.awaiting and steps[load]["title"] in " ".join(_draw(app, size, n=1).strings)
        _draw(app, size, n=1, painter=PixelPainter)
        press("Load...")
        assert not app.tour.awaiting and app.dialog is not None and app.dialog.title == "Load decay"
        app.dialog = None
        m = app.model
        m.decay_file, m.irf_file, m.output_dir = DECAY, IRF, str(tmp_path)
        m.load_config(CONFIG)
        m.n_lifetimes = 1
        fit = next(i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Fit")
        app.tour.start(fit)
        _draw(app, size, n=1, painter=PixelPainter)
        press("Fit")
        assert not app.tour.awaiting and app.model.process is not None
        app.model.stop()
    finally:
        app.tour.active = False
        app.close()


# 4. draws, empty and populated, at both sizes, every button inside its dock
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(fitted, size, monkeypatch):
    from emtk import im

    empty = LLTFApp()
    try:
        strings = _draw(empty, size).strings
        assert {"Input Files", "Fitting Options", "Decay File", "▶ Fit", "📖 Guide"} <= set(strings)
    finally:
        empty.close()
    app, _ = fitted
    _draw(app, size)
    edge = app.item_rects["Information"][0] - 4.0       # the inputs dock ends where the details dock's tabs begin
    for key in ("Load...", "load_irf", "Edit...", "Select...", "Fit"):
        x, y, w, h = app.item_rects[key]
        assert x + w <= edge, (key, x + w, edge)
    x, y, w, h = app.form.rects["find_optimal"]
    assert x + w <= edge                                                  # the toggle's label is not cut


def test_settings_round_trip(tmp_path):
    app = _loaded(tmp_path, find_optimal=True, max_lifetimes=3)
    other = LLTFApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.decay_file, m.irf_file, m.output_dir, m.find_optimal, m.max_lifetimes) == (DECAY, IRF, str(tmp_path),
                                                                                          True, 3)
    assert m.config_text == app.model.config_text


def test_help_opens_with_its_page():
    app = LLTFApp()
    app.help_window.show()
    assert app.help_window.open and "Before you believe it" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("lltf")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("lltf")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
