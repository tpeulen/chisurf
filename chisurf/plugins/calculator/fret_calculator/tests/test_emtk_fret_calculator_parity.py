"""The native FRET calculator against the Qt tool it replaces, and against the backend services.

Hermetic: settings in a temporary folder, no files, no network. The Qt tool is the one committed
before the emtk migration (its source is kept in ``okf/plugins/emtk-ports/fret_calculator/
pre-upgrade/HEAD_tool.py``); it is built offscreen and driven with the same edits as the native
window, every edit typed into the real emtk field (click, type, Enter) so that the spec's ``call``
wiring is what is tested. The numbers of both must agree to the decimals of the Qt spin boxes.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import tempfile
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.fret_calculator.backend import services
from chisurf.plugins.calculator.fret_calculator.gui.app import FretCalcApp, make_app
from chisurf.plugins.calculator.fret_calculator.gui.model import (
    FretCalculatorModel,
    HeteroFretModel,
    HomoFretModel,
)

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BASELINE = REPO / "okf/plugins/emtk-ports/fret_calculator/pre-upgrade/HEAD_tool.py"
SIZE = (1200, 800)
SMALL = (800, 600)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture
def app():
    return make_app()


def draw(app, size=SIZE, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE, fx=0.5):
    x, y, w, h = rect
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def press(app, name, size=SIZE):
    draw(app, size)
    click(app, app.target_rect(name), size)


def type_into(app, name, text, size=SIZE):
    """Click the field, type *text*, press Enter: the way a user edits a value."""
    draw(app, size)
    click(app, app.active.form.rects[name], size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    app.key(0x41, "a", 0x04000000)  # select all
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    app.key(keys.KEY_RETURN, "\r")
    draw(app, size, frames=2)


def edit(app, name, value):
    """Set a field (or the toggle) through the UI."""
    if name == "use_chi":
        draw(app)
        click(app, app.active.form.rects["use_chi"])
    else:
        type_into(app, name, repr(float(value)))


def hetero_state(m):
    return {k: getattr(m, k) for k in ("tau0", "R0", "tau", "R", "sigma", "E", "kFRET", "use_chi")}


def homo_state(m):
    return {k: getattr(m, k) for k in ("tau0", "R0", "t_RM", "rho", "sigma", "k_homo", "R_DA", "use_chi")}


# -- the Qt tool, built from the committed source -------------------------------------------- #


def _load_qt_class():
    source = BASELINE.read_text(encoding="utf-8")
    real = f"Path({str(GUI)!r})\n"
    source = source.replace("Path(__file__).parent\n", real).replace(
        "Path(__file__).parents[1]", f"Path({str(GUI.parent)!r})"
    )
    path = Path(tempfile.mkdtemp()) / "qt_baseline.py"
    path.write_text(source, encoding="utf-8")
    name = "chisurf.plugins.calculator.fret_calculator.gui.qt_baseline"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FretCalculatorTool


@pytest.fixture
def qt_tool():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = _load_qt_class()()
    tool._qapp = qapp
    yield tool
    tool.close()


def qt_edit(tool, tab, attr, value):
    """The Qt tab's field takes the value and runs its editingFinished handler."""
    if attr == "use_chi":
        tab.check_chi.setChecked(bool(value))
    else:
        spin = {
            "tau0": "spin_tau0", "R0": "spin_R0", "R": "spin_R", "sigma": "spin_sigma",
            "tau": "spin_tau", "E": "spin_E", "kFRET": "spin_kFRET",
            "t_RM": "spin_tRM", "rho": "spin_rho", "R_DA": "spin_Rhomo",
        }[attr]
        widget = getattr(tab, spin)
        widget.setValue(value)
        widget.editingFinished.emit()
    tool._qapp.processEvents()


def qt_hetero(tab):
    return {
        "tau0": tab.spin_tau0.value(), "R0": tab.spin_R0.value(), "tau": tab.spin_tau.value(),
        "R": tab.spin_R.value(), "sigma": tab.spin_sigma.value(), "E": tab.spin_E.value(),
        "kFRET": tab.spin_kFRET.value(), "use_chi": tab.check_chi.isChecked(),
    }


def qt_homo(tab):
    return {
        "tau0": tab.spin_tau0.value(), "R0": tab.spin_R0.value(), "t_RM": tab.spin_tRM.value(),
        "rho": tab.spin_rho.value(), "sigma": tab.spin_sigma.value(), "k_homo": tab.spin_kHomo.value(),
        "R_DA": tab.spin_Rhomo.value(), "use_chi": tab.check_chi.isChecked(),
    }


def assert_same(native, qt, what):
    assert native.keys() == qt.keys()
    for key in native:
        if isinstance(native[key], bool):
            assert native[key] == qt[key], (what, key)
        else:
            assert native[key] == pytest.approx(qt[key], abs=1e-9), (what, key, native[key], qt[key])


# ── 1. numbers equal the Qt tool and the backend ----------------------------------------------- #

HETERO_EDITS = [
    ("tau0", 3.5), ("R0", 60.0), ("R", 55.0), ("sigma", 8.0), ("use_chi", True),
    ("E", 0.8), ("tau", 2.0), ("kFRET", 0.5), ("use_chi", False),
    ("E", 0.0), ("E", 1.0), ("tau", 0.0), ("kFRET", 0.0), ("R", 0.1), ("sigma", 0.1),
]
HOMO_EDITS = [
    ("tau0", 2.5), ("R0", 55.0), ("rho", 20.0), ("t_RM", 1.5), ("R_DA", 45.0),
    ("use_chi", True), ("sigma", 10.0), ("R_DA", 0.0), ("t_RM", 0.001), ("R_DA", 60.0),
]


def test_hetero_defaults_and_every_edit_equal_the_qt_tool(app, qt_tool):
    qt = qt_tool.tabs.widget(0)
    assert_same(hetero_state(app.model.hetero), qt_hetero(qt), "defaults")
    for attr, value in HETERO_EDITS:
        qt_edit(qt_tool, qt, attr, value)
        edit(app, attr, value)
        assert_same(hetero_state(app.model.hetero), qt_hetero(qt), f"after {attr}={value}")


def test_homo_every_edit_equals_the_qt_tool(app, qt_tool):
    app.select_tab(1)
    draw(app)
    qt = qt_tool.tabs.widget(1)
    # The Qt tab leaves the read-only k_homo field stale after an edit of tau0, R0 or rho (and shows 0 at
    # start) although R_DA was recomputed: the native field always shows the backend's rate. Everything else
    # agrees step by step, and k_homo agrees whenever the Qt field was refreshed (t_RM and R_DA edits).
    native, qt_values = homo_state(app.model.homo), qt_homo(qt)
    assert native["k_homo"] == pytest.approx(0.46875) and qt_values["k_homo"] == 0.0
    native.pop("k_homo"), qt_values.pop("k_homo")
    assert_same(native, qt_values, "defaults")
    for attr, value in HOMO_EDITS:
        qt_edit(qt_tool, qt, attr, value)
        edit(app, attr, value)
        native, qt_values = homo_state(app.model.homo), qt_homo(qt)
        if attr in ("tau0", "R0", "rho", "sigma", "use_chi"):
            if attr in ("tau0", "R0", "rho"):
                h = app.model.homo
                rate = services.homo_compute_handler(t_RM=h.t_RM, rho=h.rho, tau0=h.tau0, R0=h.R0)["result"]["k_homo"]
                assert native["k_homo"] == pytest.approx(rate, abs=5e-7), (attr, value)
            native.pop("k_homo"), qt_values.pop("k_homo")
        assert_same(native, qt_values, f"after {attr}={value}")


def test_the_numbers_the_qt_tool_showed_are_pinned(app):
    """Values read off the Qt window (okf/plugins/emtk-ports/fret_calculator/qt_values.json)."""
    m = app.model.hetero
    assert (m.tau, m.E, m.kFRET) == (1.7599, 0.560037, 0.31823)
    for attr, value in (("tau0", 3.5), ("R0", 60.0), ("R", 55.0), ("sigma", 8.0)):
        edit(app, attr, value)
    edit(app, "use_chi", True)
    assert (m.tau, m.E, m.kFRET) == (1.4182, 0.594792, 0.419391)
    edit(app, "E", 0.8)
    assert (m.R, m.tau, m.kFRET) == (47.62, 0.7, 1.143429)
    app.select_tab(1)
    h = app.model.homo
    for attr, value in (("tau0", 2.5), ("R0", 55.0), ("rho", 20.0), ("t_RM", 1.5)):
        edit(app, attr, value)
    assert (h.k_homo, h.R_DA) == (0.308333, 57.44)
    edit(app, "R_DA", 45.0)
    assert (h.t_RM, h.k_homo) == (0.3681, 1.333402)


def test_native_values_equal_the_backend_services_not_only_the_qt_tool():
    m = HeteroFretModel()
    m.R = 55.0
    m.compute_forward()
    expect = services.fret_compute_handler(R=55.0, R0=52.0, tau0=4.0, kappa2=0.667, sigma=6.0)["result"]
    assert m.E == pytest.approx(expect["E"], abs=5e-7)
    assert m.kFRET == pytest.approx(expect["kFRET"], abs=5e-7)
    assert m.tau == pytest.approx(expect["tau_DA"], abs=5e-5)
    # physics: sigma = 0 gives the textbook E = 1 / (1 + (R/R0)^6) and tau = tau0 (1 - E)
    m.sigma = 0.1
    m.R = 52.0
    m.compute_forward()
    assert m.E == pytest.approx(0.5, abs=1e-3)
    assert m.tau == pytest.approx(4.0 * (1.0 - m.E), abs=1e-3)
    # the inverse routes round-trip a single distance
    m.sigma = 0.1
    m.R = 47.0
    m.compute_forward()
    e, k = m.E, m.kFRET
    for route, field in ((m.from_efficiency, e), (m.from_rate, k)):
        m.R = 20.0
        route()
        assert m.R == pytest.approx(47.0, abs=0.2)


def test_homo_forward_and_backmap_are_inverse_on_the_time(app):
    h = app.model.homo
    t_rm = h.t_RM
    h.compute_forward()
    r_da = h.R_DA
    h.t_RM = 5.0
    h.backmap()
    assert h.R_DA == r_da
    assert h.t_RM == pytest.approx(t_rm, rel=2e-3)


def test_plot_series_equal_the_qt_plots(app, qt_tool):
    het, homo = qt_tool.tabs.widget(0), qt_tool.tabs.widget(1)
    for attr, value in (("tau0", 3.5), ("R0", 60.0), ("R", 55.0), ("sigma", 8.0)):
        qt_edit(qt_tool, het, attr, value)
        edit(app, attr, value)
    qt_edit(qt_tool, het, "use_chi", True)
    edit(app, "use_chi", True)
    het._sync_model()
    for native, qt in ((app.model.hetero.distance_plot_series(), het._model.distance_plot_series()),
                       (app.model.hetero.rate_plot_series(), het._model.rate_plot_series())):
        assert [s["name"] for s in native] == [s["name"] for s in qt]
        for a, b in zip(native, qt):
            np.testing.assert_allclose(a["x"], b["x"])
            np.testing.assert_allclose(a["y"], b["y"])
            assert (a["style"], a["width"]) == (b["style"], b["width"])
    app.select_tab(1)
    for attr, value in (("tau0", 2.5), ("rho", 20.0), ("R_DA", 45.0)):
        qt_edit(qt_tool, homo, attr, value)
        edit(app, attr, value)
    homo._sync_model()
    for native, qt in ((app.model.homo.distance_plot_series(), homo._model.distance_plot_series()),
                       (app.model.homo.aniso_time_plot_series(), homo._model.aniso_time_plot_series())):
        for a, b in zip(native, qt):
            np.testing.assert_allclose(a["x"], b["x"])
            np.testing.assert_allclose(a["y"], b["y"])


# ── 2. actions, errors -------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("attr", "value", "message"),
    [("E", 0.0, "FRET from efficiency failed"), ("E", 1.0, "FRET from efficiency failed"),
     ("tau", 0.0, "FRET from lifetime failed"), ("kFRET", 0.0, "FRET from rate failed")],
)
def test_a_failed_inverse_says_so_keeps_the_other_fields_and_the_next_edit_clears_it(app, attr, value, message):
    m = app.model.hetero
    before = hetero_state(m)
    edit(app, attr, value)
    assert m.status.startswith(message)
    assert message in " ".join(draw(app).strings)
    kept = {k: v for k, v in hetero_state(m).items() if k not in (attr,)}
    assert kept == {k: v for k, v in before.items() if k not in (attr,)}
    edit(app, "R", 40.0)
    assert m.status == ""
    assert message not in " ".join(draw(app).strings)


def test_a_lifetime_longer_than_the_donor_only_lifetime_is_an_error_not_an_exception(app):
    m = app.model.hetero
    edit(app, "tau", 9.0)  # tau_DA > tau0: no distance (the backend raises a complex-number error)
    assert m.status.startswith("FRET from lifetime failed")
    assert m.tau == 9.0 and m.R == 50.0


def test_homo_with_no_finite_distance_keeps_the_fields_and_is_not_an_error(app):
    app.select_tab(1)
    h = app.model.homo
    before = homo_state(h)
    edit(app, "R_DA", 0.0)
    assert h.status == ""
    assert (h.R_DA, h.t_RM, h.k_homo) == (0.0, before["t_RM"], before["k_homo"])


def test_a_failing_backend_is_reported_for_every_route():
    class Broken:
        def __getattr__(self, name):
            return lambda **kwargs: {"ok": False, "error": "backend down"}

    model = FretCalculatorModel(Broken())
    assert model.hetero.status == "FRET from distance failed: backend down"
    assert model.homo.status == "Homo-FRET rate failed: backend down"
    model.homo.backmap()
    assert model.homo.status == "Homo-FRET back-map failed: backend down"
    model.hetero.from_rate()
    assert model.hetero.status == "FRET from rate failed: backend down"
    assert model.hetero.R == 50.0  # nothing was written


def test_typed_garbage_is_ignored_and_out_of_range_values_are_clamped(app):
    m = app.model.hetero
    type_into(app, "R", "abc")
    assert m.R == 50.0 and m.status == ""
    type_into(app, "R", "5000000")
    assert m.R == 9999.0
    type_into(app, "R", "-3")
    assert m.R == 0.1
    type_into(app, "E", "7")
    assert m.E == 1.0 and m.status.startswith("FRET from efficiency failed")
    type_into(app, "R", "55 A")  # the unit the field shows is accepted back
    assert m.R == 55.0


def test_the_arrows_step_the_value_and_run_the_handler(app):
    m = app.model.hetero
    draw(app)
    r, e = m.R, m.E
    x, y, w, h = app.active.form.rects["R.stepper"]
    app.press(x + w / 2, y + h * 0.25)  # upper half = up
    draw(app, frames=1)
    app.release()
    draw(app, frames=2)
    assert m.R > r and m.E != e


def test_the_chi_toggle_recomputes_and_swaps_the_solid_curve(app):
    m = app.model.hetero
    e = m.E
    assert {s["name"]: s["style"] for s in m.distance_plot_series()} == {"Gaussian": "solid", "chi": "dash"}
    edit(app, "use_chi", True)
    assert m.use_chi and m.E != e
    assert {s["name"]: s["style"] for s in m.distance_plot_series()} == {"Gaussian": "dash", "chi": "solid"}
    app.select_tab(1)
    h = app.model.homo
    t = h.t_RM
    edit(app, "use_chi", True)  # homo: the toggle only changes the plot
    assert h.use_chi and h.t_RM == t
    assert {s["name"]: s["style"] for s in h.aniso_time_plot_series()} == {"Gaussian": "dash", "chi": "solid"}


def test_k_homo_is_an_output_it_cannot_be_typed_into(app):
    app.select_tab(1)
    draw(app)
    k = app.model.homo.k_homo
    click(app, app.active.form.rects["k_homo"], fx=0.3)
    app.key(ord("9"), "9")
    app.key(keys.KEY_RETURN, "\r")
    draw(app, frames=2)
    assert app.model.homo.k_homo == k


def test_the_tab_bar_switches_tabs(app):
    draw(app)
    assert app.active_tab == 0
    click(app, app.item_rects["tab_homofret"])
    assert app.active_tab == 1 and "Homo-FRET parameters" in " ".join(draw(app).strings)
    click(app, app.item_rects["tab_heterofret"])
    assert app.active_tab == 0 and "FRET parameters" in " ".join(draw(app).strings)


def test_a_dropped_file_says_the_calculator_has_no_file_input(app):
    assert app.files_dropped([]) is False and app.model.hetero.status == ""
    assert app.on_files_dropped(["/tmp/run.ptu"]) is True
    assert app.model.hetero.status == "The FRET Calculator takes no dropped files."
    assert "takes no dropped files" in " ".join(draw(app).strings)
    app.select_tab(1)
    assert app.on_paths_dropped(["/tmp/x"]) and "takes no dropped files" in app.model.homo.status
    edit(app, "t_RM", 2.0)
    assert app.model.homo.status == ""
    # the Qt host reaches the drop through the same hooks
    assert callable(getattr(app, "files_dropped")) and callable(getattr(app, "on_paths_dropped"))


def test_the_qt_tool_still_says_so_for_a_drop(qt_tool, tmp_path):
    """The behaviour the hook above replaces (kept in the baseline)."""
    qt_tool.on_paths_dropped([tmp_path / "run.ptu"])
    assert qt_tool.Information.no_file_input.is_shown


# ── 3. spec, tooltips, drawing ------------------------------------------------------------------ #


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


@pytest.mark.parametrize(("spec_file", "model"), [("fret.view.json", HeteroFretModel), ("homofret.view.json", HomoFretModel)])
def test_every_spec_key_exists_on_the_model(spec_file, model):
    spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
    m = model()
    found = set()
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source"):
            if section.get(key):
                assert hasattr(m, section[key]), (key, section[key])
                found.add(section[key])
        if section.get("call"):
            assert callable(getattr(m, section["call"]))
    assert {"tau0", "R0", "R", "sigma", "use_chi"} <= found or {"tau0", "R0", "t_RM", "rho"} <= found


def test_every_field_has_the_qt_limits_and_decimals():
    """Spec ranges equal the Qt AutoForm spec (HEAD) and the model's result rounding."""
    for spec_file, model in (("fret.view.json", HeteroFretModel), ("homofret.view.json", HomoFretModel)):
        spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
        fields = {s["attr"]: s for s in _walk(spec["sections"]) if s.get("type") == "value"}
        for attr, (decimals, lo, hi) in {**model.input_fields, **model.result_fields}.items():
            assert (fields[attr]["decimals"], fields[attr]["minimum"], fields[attr]["maximum"]) == (decimals, lo, hi), attr


@pytest.mark.parametrize("size", [SIZE, SMALL])
@pytest.mark.parametrize("tab", [0, 1])
def test_draws_the_form_and_both_plots_at_both_sizes(size, tab):
    app = make_app()
    app.select_tab(tab)
    strings = " ".join(draw(app, size).strings)
    labels = ("Lifetime D0", "Förster R0", "Distance DA", "Lifetime DA", "Efficiency", "kFRET", "σ", "χ distribution",
              "Distance distribution", "Rate-constant distribution", "HeteroFRET", "HomoFRET") if tab == 0 else (
              "τ0", "R0", "t_RM", "ρ", "k_homo", "R_DA", "σ", "χ distribution", "Distance distribution",
              "Anisotropy decay time", "HeteroFRET", "HomoFRET")
    for label in labels:
        assert label in strings, (tab, size, label)
    assert "Gaussian" in strings and "chi" in strings  # legends: the plots drew curves
    assert math.isfinite(app.model.hetero.E)


def test_draws_after_every_edit_even_at_the_ends_of_the_ranges(app):
    for attr, value in (("R", 0.1), ("R", 9999.0), ("sigma", 999.0), ("sigma", 0.1), ("R0", 999.0), ("tau0", 0.001)):
        edit(app, attr, value)
        assert draw(app).strings
        for series in app.model.hetero.distance_plot_series() + app.model.hetero.rate_plot_series():
            assert np.isfinite(series["x"]).all() and np.isfinite(series["y"]).all()


def test_no_emoji_in_the_native_labels(app):
    for tab in (0, 1):
        app.select_tab(tab)
        strings = draw(app).strings
        assert all(ord(ch) < 0x2190 or ch in "τΔρσΣχ" for text in strings for ch in text), strings
        assert {"Guide", "Help"} <= set(strings)


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("fret_calculator"))
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {"Guide", "Help", "R", "E", "tau0", "R0", "tau", "kFRET", "sigma", "χ distribution"} <= labels
    app.select_tab(1)
    assert emtk_inventory(app)["controls_without_tooltip"] == []
    for spec_file in ("fret.view.json", "homofret.view.json"):
        spec = json.loads((GUI / spec_file).read_text(encoding="utf-8"))
        for section in _walk(spec["sections"]):
            if section.get("type") in ("value", "choice", "toggle", "plot", "panel"):
                assert section.get("description"), section.get("attr") or section.get("title")


# ── 4. guide and help ---------------------------------------------------------------------------- #


def test_guide_steps_point_at_controls_the_app_draws(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert [s["title"] for s in steps if s.get("await")] == [
        "Donor lifetime", "Förster radius", "Distance", "Inverse calculation", "Distance distribution",
        "HomoFRET", "Migration time", "Back-map"]
    app.tour.start()
    for index, step in enumerate(steps):
        app.tour.step_idx = index
        app.tour._notify_change()  # selects the tab the step lives on
        draw(app)
        name = EmTkGuidedTour._target_key(step["target"])
        assert app.target_rect(name), f"{step['title']}: nothing drawn for {name!r}"
    assert not any(re.search(r"[\U0001F300-\U0001FAFF]", s["text"]) for s in steps)


def test_the_tour_waits_for_the_user_and_walks_through_both_tabs(app):
    app.tour.start()
    draw(app)
    assert app.tour.awaiting and app.tour.step_idx == 0
    edit(app, "tau0", 3.0)
    assert not app.tour.awaiting
    app.tour.next()
    edit(app, "R0", 50.0)
    app.tour.next()
    edit(app, "R", 45.0)
    app.tour.next()
    edit(app, "E", 0.6)
    app.tour.next()
    edit(app, "use_chi", True)
    app.tour.next()
    draw(app)
    assert app.tour.awaiting and app.active_tab == 0  # waits for the HomoFRET tab, never presses it
    click(app, app.item_rects["tab_homofret"])
    assert not app.tour.awaiting and app.active_tab == 1
    app.tour.next()
    draw(app)
    assert app.active_tab == 1 and app.tour.awaiting
    edit(app, "t_RM", 2.0)
    app.tour.next()
    edit(app, "R_DA", 50.0)
    app.tour.next()
    draw(app)
    assert app.tour.step_idx == len(app.tour.steps) - 1 and not app.tour.awaiting


def test_the_tour_hides_nothing_when_it_starts_on_the_other_tab(app):
    app.select_tab(1)
    app.tour.start()
    draw(app)
    assert app.active_tab == 0  # step 1 lives on HeteroFRET and brings the window there


def test_guide_and_help_buttons_open_the_tour_and_the_help(app):
    press(app, "guide")
    assert app.tour.active
    app.tour.stop()
    press(app, "help")
    assert app.help_window.open and draw(app).strings


def test_help_text_is_plain_and_its_links_are_live(app):
    text = (GUI / "help.md").read_text(encoding="utf-8")
    assert "**" not in text and "`" not in text  # the native help window shows Markdown marks raw
    assert "slider" not in text.lower()  # the Qt-era text described sliders this window does not have
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert links and all((REPO / link).is_file() for link in links)
    app.help_window.show()
    assert "FRET calculator" in " ".join(draw(app).strings) or draw(app).strings


# ── 5. persistence, manifest, no Qt, host ---------------------------------------------------------- #


def test_settings_round_trip_and_invalid_values_are_ignored(app):
    edit(app, "tau0", 3.5)
    edit(app, "R", 55.0)
    edit(app, "use_chi", True)
    app.select_tab(1)
    edit(app, "t_RM", 2.5)
    edit(app, "rho", 12.0)
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["tab"] == 1 and saved["hetero"]["tau0"] == 3.5 and saved["hetero"]["use_chi"] is True
    assert set(saved["homo"]) == {"tau0", "R0", "t_RM", "rho", "sigma", "use_chi"}
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved
    assert other.active_tab == 1
    assert other.model.hetero.E == app.model.hetero.E and other.model.homo.k_homo == app.model.homo.k_homo
    other.restore_settings({"hetero": {"tau0": "x", "R0": float("nan"), "R": 1e9, "use_chi": "yes"},
                            "homo": ["no"], "tab": 7})
    assert other.model.hetero.tau0 == 3.5 and other.model.hetero.R0 == 52.0  # unusable values change nothing
    assert other.model.hetero.R == 55.0 and other.model.hetero.use_chi is True and other.active_tab == 1
    other.restore_settings("garbage")
    assert draw(other).strings


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fret_calculator")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app_and_the_hub_kwargs_are_accepted():
    manifest = json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.calculator.fret_calculator.gui.app:make_app"
    assert isinstance(make_app(restore=False), FretCalcApp)


def test_the_qt_host_runs_the_same_app_on_the_same_models(qt_tool):
    from chisurf.plugins.calculator.fret_calculator.gui.tool import FretCalculatorTool

    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    tool = FretCalculatorTool()
    try:
        assert isinstance(tool.app, FretCalcApp)
        assert tool.app.hetero.model is tool._hetero_model is tool.model.hetero
        assert tool.tabs.count() == 2
        tool.app.hetero.model.R = 55.0
        tool.app.hetero._compute_forward()
        assert tool.app.hetero.model.E == pytest.approx(
            services.fret_compute_handler(R=55.0, R0=52.0, tau0=4.0, kappa2=0.667, sigma=6.0)["result"]["E"], abs=5e-7)
    finally:
        tool.close()
        assert QtWidgets is not None
