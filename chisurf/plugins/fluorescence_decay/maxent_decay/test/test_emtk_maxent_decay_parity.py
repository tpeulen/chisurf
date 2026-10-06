"""The native MaxEnt MEM tool against the Qt tool, every control operated with real input events.

Hermetic through ``conftest.py`` (HOME, chisurf/MMFDB folders and QSettings in a temp folder); the last test proves
the user's real ``~/.chisurf`` is untouched. Both tools are fed the same stub live fit (a two-lifetime decay of
1.1 / 3.6 ns with its IRF), so the numbers must agree.
"""

from __future__ import annotations

import json
import os
import pwd
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import MaxentApp, make_app
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.model import MEMModel, execute_job
from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem

PLUGIN = Path(__file__).parent.parent
REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {
        str(p): p.stat().st_mtime_ns
        for p in REAL_CHISURF.rglob("*")
        if p.is_file() and not {"cache", "logs"} & set(p.parts)
    }


REAL_BEFORE = snapshot_real()


def stub_fit():
    y, lamp, dt, t = _problem(n=256)
    data = SimpleNamespace(x=t, y=y, name="two_lifetimes.dat", dx=np.array([dt]))
    irf = SimpleNamespace(x=t, y=lamp, name="IRF.dat")
    return SimpleNamespace(
        name="Fit 1",
        data=data,
        xmin=20,
        xmax=255,
        model=SimpleNamespace(
            convolve=SimpleNamespace(
                irf=irf, unnormalized_irf=irf, timeshift=0.0, lamp_background=0.0
            ),
            generic=SimpleNamespace(background=5.0, scatter=0.0),
        ),
    )


class UI(Driver):
    def settle(self, timeout=120.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.jobs.process is not None and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        self.draw(3)
        assert self.app.jobs.process is None
        return self.app.model


@pytest.fixture
def ui():
    app = make_app()
    driver = UI(app)
    driver.draw()
    yield driver
    app.close()


@pytest.fixture
def fitted(ui):
    m = ui.app.model
    m.load_fit(stub_fit())
    m.settings.tau_bins = 32
    m.settings.tau_max = 8.0
    ui.draw(3)
    return ui


def run(ui):
    ui.click_text("Run MEM")
    return ui.settle()


def field(ui, panel, name):
    ui.draw()
    return ui.app.forms[panel].rects[name]


def reveal(ui, label, steps=-4.0):
    """Scroll the controls window with the wheel until the text *label* is drawn."""
    for _ in range(12):
        hits = [t[:4] for t in ui.draw().texts if t[5] == label]
        if hits and 40 < hits[-1][1] < ui.size[1] - 16:
            return
        ui.wheel(120, 400, steps)
    raise AssertionError(f"{label!r} never scrolled into view")


def open_more(ui):
    """Open the collapsed L-curve / sampling section (once), scrolling it into view."""
    if "lcurve" not in ui.app.plot_info.get("opened", ()):
        reveal(ui, "> L-curve span and sampling")
        ui.click_text("> L-curve span and sampling")
        ui.app.plot_info.setdefault("opened", set()).add("lcurve")
    ui.draw(2)


def scroll_to(ui, panel, name):
    for _ in range(12):
        ui.draw(2)
        rect = ui.app.forms[panel].rects.get(name)
        if rect and 0 < rect[1] < ui.size[1] - 30:
            return
        ui.wheel(120, 400, -3.0)


def type_into_field(ui, panel, name, text):
    for _ in range(12):
        ui.draw(2)
        rect = ui.app.forms[panel].rects.get(name)
        if rect and 0 < rect[1] < ui.size[1] - 30:
            break
        ui.wheel(120, 400, -3.0)
    ui.type_into(ui.app.forms[panel].rects[name], text)


def type_value(ui, panel, name, text):
    if panel in ("lcurve", "sampling"):
        open_more(ui)
    type_into_field(ui, panel, name, text)
    return ui.app.model


def write_decay(path, t, y):
    np.savetxt(path, np.column_stack((t, y)))
    return str(path)


# ───────────────────────────── numbers equal the Qt tool ───────────────────────────── #


@pytest.fixture
def qt_tool():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import MaxentDecayWidget

    fit = stub_fit()
    w = MaxentDecayWidget()
    w._qapp = qapp
    w._current_fit = lambda: fit
    w._on_refresh_data()
    return w


def test_refreshing_from_a_live_fit_sets_the_same_values_as_the_qt_tool(qt_tool):
    m = MEMModel()
    m.load_fit(stub_fit())
    assert m.settings.tau_min == pytest.approx(qt_tool.spin_tau_min.value(), abs=1e-3)
    assert m.settings.period == pytest.approx(qt_tool.spin_period.value(), abs=1e-2)
    assert m.settings.background == pytest.approx(qt_tool.spin_background.value())
    assert m.settings.timeshift == pytest.approx(qt_tool.spin_timeshift.value())
    assert (m.settings.irf_background or 0.0) == pytest.approx(qt_tool.spin_irf_bg.value())
    assert m.fitrange == tuple(qt_tool._fit_range)
    assert (
        "two_lifetimes.dat" in qt_tool.label_data_source.text() and "two_lifetimes.dat" in m.source
    )
    assert "IRF.dat" in qt_tool.label_irf_source.text() and "IRF.dat" in m.irf_source


def test_the_mem_run_equals_the_qt_run(qt_tool):
    qt_tool.spin_tau_bins.setValue(32)
    qt_tool.spin_tau_max.setValue(8.0)
    qt_tool._run_mem()
    qt = qt_tool._last_result
    m = MEMModel()
    m.load_fit(stub_fit())
    m.settings.tau_bins, m.settings.tau_max = 32, 8.0
    result = m.run()
    assert float(result["chisq"]) == pytest.approx(float(qt["chisq"]), rel=1e-6)
    np.testing.assert_allclose(result["p"], qt["p"], rtol=1e-5, atol=1e-8)
    np.testing.assert_allclose(result["tau"], qt["tau"])
    assert float(result["S"]) == pytest.approx(float(qt["S"]), rel=1e-6)


def test_the_lcurve_sweep_equals_the_qt_sweep(qt_tool, monkeypatch):
    qt_tool.spin_tau_bins.setValue(16)
    qt_tool.spin_tau_max.setValue(8.0)
    seen = {}
    monkeypatch.setattr(
        qt_tool,
        "_update_lcurve_plot",
        lambda chi, sol, nu, corner: seen.update(
            chi=np.array(chi), sol=np.array(sol), nu=np.array(nu)
        ),
    )
    qt_tool._run_lcurve()
    m = MEMModel()
    m.load_fit(stub_fit())
    m.settings.tau_bins, m.settings.tau_max = 16, 8.0
    curve = execute_job({"kind": "lcurve", "snapshot": m.snapshot()})
    # the plateau chi2 differs by 0.05 % (open item in the report): same curve shape, same nu axis
    np.testing.assert_allclose(curve["chi2r"], seen["chi"], rtol=2e-3)
    np.testing.assert_allclose(curve["sol_norm"], seen["sol"], rtol=2e-2)
    np.testing.assert_allclose(10.0 ** curve["log10_nu"], seen["nu"])


# ───────────────────────────────────── data input ───────────────────────────────────── #


def test_an_empty_window_asks_for_data_and_greys_the_actions(ui):
    strings = [t[5] for t in ui.draw().texts]
    assert "Select a decay or use a live fit." in strings
    m = ui.app.model
    ui.click_text("Run MEM")
    assert ui.app.jobs.process is None and m.result is None
    ui.click_text("Save")
    ui.click_text("Sample")
    assert ui.app.dialog is None


def test_load_decay_and_irf_through_the_dialog_then_run(ui, tmp_path):
    y, lamp, dt, t = _problem(n=128)
    write_decay(tmp_path / "decay.dat", t, y)
    write_decay(tmp_path / "irf.dat", t, lamp)
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Load decay")
    assert ui.app.dialog is not None
    ui.click_text("decay.dat")
    ui.click_text("Open")
    m = ui.app.model
    assert m.source == "decay.dat" and len(m.decay) == 128 and m.dt == pytest.approx(dt)
    ui.click_text("IRF file")
    ui.click_text("irf.dat")
    ui.click_text("Open")
    assert m.irf_source == "irf.dat" and m.irf is not None
    m.settings.tau_bins = 16
    m.settings.tau_max = 8.0
    m = run(ui)
    assert m.result is not None and np.isfinite(m.result["p"]).all()
    ui.click_text("Clear IRF")
    assert m.irf is None and m.result is None


def test_the_dialog_cancel_and_close_load_nothing(ui, tmp_path):
    ui.app.last_dir = str(tmp_path)
    for closer in ("Cancel", "×"):
        ui.click_text("Load decay")
        assert ui.app.dialog is not None
        ui.click_text(closer)
        assert ui.app.dialog is None
    assert ui.app.model.decay is None


def test_a_file_that_is_not_a_decay_is_reported(ui, tmp_path):
    (tmp_path / "bad.dat").write_text("just text\n")
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Load decay")
    ui.click_text("bad.dat")
    ui.click_text("Open")
    assert ui.app.model.decay is None and ui.app.model.status.startswith("Error:")
    assert any(ui.app.model.status[:30] in t[5] for t in ui.draw().texts)


def test_dropped_files_load_decay_irf_and_preferences(ui, tmp_path):
    y, lamp, dt, t = _problem(n=128)
    decay, irf = write_decay(tmp_path / "d.dat", t, y), write_decay(tmp_path / "i.dat", t, lamp)
    prefs = tmp_path / "p.json"
    prefs.write_text(json.dumps({"tau_grid": {"max": 9.5}}))
    assert ui.drop(decay, irf, prefs) is True
    m = ui.app.model
    assert m.source == "d.dat" and m.irf_source == "i.dat" and m.settings.tau_max == 9.5
    assert ui.drop() is False


def test_refresh_lists_live_fits_and_datasets_and_each_use_button_works(ui, monkeypatch):
    import chisurf

    fit = stub_fit()
    other = SimpleNamespace(x=fit.data.x, y=fit.data.y * 0.5 + 1, name="half.dat")
    monkeypatch.setattr(chisurf, "fits", [fit])
    monkeypatch.setattr(chisurf, "imported_datasets", [fit.data, other])
    m = ui.app.model
    assert not ui.drawn("Fit")
    ui.click_text("Refresh")
    assert ui.drawn("Fit") and ui.drawn("Use as decay")
    ui.click_text("Fit")
    assert m.source == "two_lifetimes.dat" and m.fit is fit and m.settings.background == 5.0
    ui.app.dataset_index = 1
    ui.click_text("Use as decay")
    assert m.source == "half.dat"
    ui.click_text("Use as IRF")
    assert m.irf_source == "half.dat"


# ───────────────────────────────────── settings forms ───────────────────────────────────── #


@pytest.mark.parametrize(
    "panel,name,typed,expected",
    [
        ("mode", "nu", "0.01", 0.01),
        ("mode", "nu", "5", 1.0),
        ("mode", "max_iter", "50", 50),
        ("lifetime", "tau_min", "0.2", 0.2),
        ("lifetime", "tau_max", "7", 7.0),
        ("lifetime", "tau_bins", "24", 24),
        ("lifetime", "tau_bins", "1", 2),
        ("instrument", "timeshift", "0.5", 0.5),
        ("instrument", "timeshift", "500", 100.0),
        ("instrument", "background", "3.5", 3.5),
        ("instrument", "irf_background", "0.2", 0.2),
        ("instrument", "lamp_scatter", "0.01", 0.01),
        ("lcurve", "lcurve_left", "1.5", 1.5),
        ("lcurve", "lcurve_right", "9", 6.0),
        ("sampling", "sample_steps", "200", 200),
        ("sampling", "sample_thin", "2", 2),
        ("sampling", "sample_walkers", "8", 8),
        ("sampling", "sample_substeps", "20", 20),
        ("sampling", "sample_nprocs", "2", 2),
    ],
)
def test_each_setting_takes_typed_values_clamped_to_the_qt_range(ui, panel, name, typed, expected):
    m = type_value(ui, panel, name, typed)
    value = getattr(m.settings, name) if hasattr(m.settings, name) else getattr(m, name)
    assert value == pytest.approx(expected)


@pytest.mark.parametrize(
    "panel,name,step",
    [
        ("mode", "nu", 1e-3),
        ("lifetime", "tau_bins", 1),
        ("instrument", "background", 1.0),
        ("lcurve", "lcurve_left", 0.5),
        ("sampling", "sample_thin", 1),
    ],
)
def test_the_arrows_step_each_kind_of_field(ui, panel, name, step):
    m = ui.app.model
    holder = m.settings if hasattr(m.settings, name) else m
    if panel in ("lcurve", "sampling"):
        open_more(ui)
    setattr(holder, name, getattr(holder, name) + 10 * step)  # away from the lower limit
    ui.draw(2)
    scroll_to(ui, panel, f"{name}.stepper")
    ui.click(field(ui, panel, f"{name}.stepper"), fy=0.25)
    after_up = getattr(holder, name)
    ui.click(field(ui, panel, f"{name}.stepper"), fy=0.75)
    ui.click(field(ui, panel, f"{name}.stepper"), fy=0.75)
    assert after_up - getattr(holder, name) == pytest.approx(2 * step, rel=1e-3)


def test_the_mode_choice_switches_the_grid_panel_and_resets_results(fitted):
    ui = fitted
    run(ui)
    assert (
        ui.app.model.result is not None
        and ui.drawn("Lifetime grid")
        and not ui.drawn("Distance grid")
    )
    ui.click(field(ui, "mode", "mode"))
    ui.click_text("FRET")
    m = ui.app.model
    assert m.settings.mode == "fret" and m.result is None
    assert ui.drawn("Distance grid") and not ui.drawn("Lifetime grid")
    ui.click(field(ui, "mode", "mode"))
    ui.click_text("Lifetime")
    assert m.settings.mode == "lifetime"


def test_the_fret_fields_and_the_donor_gate(fitted, tmp_path):
    ui = fitted
    ui.click(field(ui, "mode", "mode"))
    ui.click_text("FRET")
    m = ui.app.model
    for name, typed, expected in (
        ("tau0", "3.5", 3.5),
        ("R0", "60", 60.0),
        ("r_min_frac", "0.2", 0.2),
        ("r_max_frac", "2.5", 2.5),
        ("r_bins", "12", 12),
        ("x_donly", "0.1", 0.1),
    ):
        type_value(ui, "fret", name, typed)
        assert getattr(m.settings, name) == pytest.approx(expected), name
    ui.click_text("Run MEM")
    assert ui.app.jobs.process is None  # greyed: FRET needs a donor spectrum
    assert any("required in FRET mode" in t[5] for t in ui.draw().texts)
    donor = tmp_path / "donor.csv"
    np.savetxt(donor, [[1.0, 4.1]], delimiter=",")
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Donor")
    ui.click_text("donor.csv")
    ui.click_text("Open")
    assert m.donor is not None and "1 components" in " ".join(t[5] for t in ui.draw().texts)
    ui.click_text("fix donor-only fraction")
    assert m.fix_x_donly is True
    m.settings.r_bins = 8
    m = run(ui)
    assert "R" in m.result and len(m.result["p"]) == 8


def test_the_period_field_is_greyed_until_periodic_convolution_is_ticked(ui):
    m = ui.app.model
    assert not ui.app.mform.enabled("period")
    ui.click_text("Periodic convolution")
    assert m.use_periodic is True and ui.app.mform.enabled("period")
    type_value(ui, "period", "period", "12.5")
    assert m.settings.period == 12.5
    ui.click_text("Periodic convolution")
    assert m.use_periodic is False


@pytest.mark.parametrize(
    "label,attr",
    [
        ("Fit nuisance (ts/bg/IRF BG)", "optimize_nuisance"),
        ("fix timeshift", "fix_timeshift"),
        ("fix background", "fix_background"),
        ("fix IRF background", "fix_irf_background"),
        ("Vectorized sampling", "sample_vectorized"),
    ],
)
def test_every_switch_is_clicked(ui, label, attr):
    m = ui.app.model
    holder = m.settings if hasattr(m.settings, attr) else m
    before = bool(getattr(holder, attr))
    if attr == "sample_vectorized":
        open_more(ui)
    reveal(ui, label)
    ui.click_text(label)
    assert bool(getattr(holder, attr)) is (not before)
    ui.click_text(label)
    assert bool(getattr(holder, attr)) is before


def test_fixed_nuisance_values_reach_the_solver(fitted):
    ui = fitted
    m = ui.app.model
    type_value(ui, "instrument", "timeshift", "0.37")
    type_value(ui, "instrument", "background", "7.5")
    type_value(ui, "instrument", "irf_background", "0.1")
    ui.click_text("Fit nuisance (ts/bg/IRF BG)")
    for label in ("fix timeshift", "fix background", "fix IRF background"):
        ui.click_text(label)
    m = run(ui)
    assert m.result["timeshift"] == pytest.approx(0.37) and m.result["background"] == pytest.approx(
        7.5
    )
    assert m.result["irf_background"] == pytest.approx(0.1)


# ───────────────────────────────────── run, plots, jobs ───────────────────────────────────── #


def test_run_gives_the_solver_result_and_draws_all_four_plots(fitted):
    ui = fitted
    m = run(ui)
    assert m.result is not None and m.status == "run completed."
    reference = MEMModel()
    reference.load_fit(stub_fit())
    reference.settings.tau_bins, reference.settings.tau_max = 32, 8.0
    np.testing.assert_allclose(m.result["p"], reference.run()["p"], rtol=1e-6)
    strings = [t[5] for t in ui.draw().texts]
    for label in (
        "Time (ns)",
        "Counts",
        "Observed",
        "IRF scaled",
        "MEM fit",
        "Lifetime (ns)",
        "Probability",
        "MEM",
        "Residual / sigma",
        "Residuals",
        "Chi-square",
        "Solution norm",
    ):
        assert label in strings or any(label in s for s in strings), label
    assert "Lifetime grid" in strings


def test_run_is_cancelled_by_the_cancel_button(fitted):
    ui = fitted
    ui.app.model.settings.tau_bins = 400
    ui.app.model.settings.max_iter = 100000
    ui.app.model.settings.tol = 1e-12
    ui.click_text("Run MEM")
    assert ui.app.jobs.process is not None
    ui.click_text("Cancel job")
    ui.settle()
    assert (
        ui.app.model.result is None
        and "cancelled" in ui.app.model.status
        or "failed" in ui.app.model.status
    )


def test_the_lcurve_button_sweeps_and_sets_nu_and_a_click_on_a_point_picks_its_nu(fitted):
    ui = fitted
    ui.click_name("lcurve")
    m = ui.settle()
    assert m.lcurve is not None and len(m.lcurve["log10_nu"]) == 16
    ui.draw(3)
    points = ui.app.plot_info["lcurve"]
    index = 3
    ui.click((points[index][0] - 3, points[index][1] - 3, 6, 6))
    assert m.settings.nu == pytest.approx(10.0 ** m.lcurve["log10_nu"][index], rel=1e-6)
    assert "from L-curve" in m.status


def test_dragging_the_fit_range_box_in_the_decay_plot_changes_the_range(fitted):
    ui = fitted
    ui.draw(3)
    m = ui.app.model
    info = ui.app.plot_info["decay"]
    before = tuple(m.fitrange)
    (x, y) = info["left"]
    ui.drag((x, y), (x + 60, y))
    assert m.fitrange[0] > before[0] and m.fitrange[1] == before[1]


def test_the_wheel_zooms_the_decay_plot(fitted):
    ui = fitted
    ui.draw(3)
    (px, py), (sx, sy) = ui.app.plot_info["decay"]["pos"], ui.app.plot_info["decay"]["size"]
    before = [t[5] for t in ui.draw().texts]
    ui.wheel(px + sx * 0.5, py + sy * 0.5, -3.0)
    assert [t[5] for t in ui.draw().texts] != before


def test_save_writes_the_result_folder_and_sample_writes_the_chains(fitted, tmp_path):
    ui = fitted
    run(ui)
    ui.app.last_dir = str(tmp_path)
    out = tmp_path / "result"
    out.mkdir()
    ui.click_text("Save")
    assert ui.app.dialog is not None
    ui.click_text("[result]")
    ui.click_text("Choose")
    assert {p.name for p in out.iterdir()} == {
        "distribution.txt",
        "decay_fit.txt",
        "irf.txt",
        "wres.txt",
        "meta.json",
    }
    type_value(ui, "sampling", "sample_steps", "20")
    type_value(ui, "sampling", "sample_thin", "1")
    type_value(ui, "sampling", "sample_substeps", "10")
    type_value(ui, "sampling", "sample_nprocs", "1")
    ui.app.last_dir = str(tmp_path)
    samples = tmp_path / "samples"
    samples.mkdir()
    ui.wheel(120, 400, 30.0)  # back to the top: the buttons
    ui.click_text("Sample")
    ui.click_text("[samples]")
    ui.click_text("Choose")
    m = ui.settle()
    assert m.samples is not None and (samples / "sampling_project.json").is_file()
    assert (samples / "sampling.npz").is_file()


# ───────────────────────────────────── json, help, guide ───────────────────────────────────── #


def test_the_json_editor_applies_valid_preferences_and_reports_invalid_ones(ui):
    m = ui.app.model
    ui.click_text("JSON")
    assert ui.app.edit_settings
    data = json.loads(ui.app.settings_text)
    data["settings"]["tau_max"] = 11.0
    ui.app.settings_text = json.dumps(data)
    ui.click_text("Apply settings")
    assert m.settings.tau_max == 11.0 and not ui.app.edit_settings
    ui.click_text("JSON")
    ui.app.settings_text = "{broken"
    ui.click_text("Apply settings")
    assert m.status.startswith("Error:") and m.settings.tau_max == 11.0
    ui.click_text("JSON")
    ui.click_text("Close settings")
    assert not ui.app.edit_settings


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_text("Help")
    assert ui.app.help_window.open
    ui.click_text("Close")
    assert not ui.app.help_window.open
    import re

    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_refresh_run_and_lcurve(fitted, monkeypatch):
    import chisurf

    monkeypatch.setattr(chisurf, "fits", [stub_fit()])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    ui = fitted
    ui.click_text("Guide")
    tour = ui.app.tour
    assert tour.active
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 1
    ui.click_text("Refresh")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 2 and tour.awaiting
    ui.click_text("Run MEM")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 3 and tour.awaiting
    ui.click_name("lcurve")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Next ►")
    ui.click_text("Close Tour")
    assert not tour.active


def test_every_tour_target_is_drawn(fitted):
    ui = fitted
    for index, step in enumerate(ui.app.tour.steps):
        key = ui.app.tour._target_key(step.get("target"))
        if not key:
            continue
        ui.app.tour.start(index)
        ui.draw(3)
        assert ui.app.tour.get_target_rect(key), key
        ui.app.tour.stop()


# ───────────────────────────── settings, sizes, tooltips, hygiene ─────────────────────────────  #


def test_settings_round_trip(ui):
    m = ui.app.model
    m.settings.tau_max = 9.0
    m.settings.nu = 0.02
    m.use_periodic = True
    m.sample_steps = 300
    ui.app.last_dir = "/somewhere"
    saved = json.loads(json.dumps(ui.app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.model.settings.tau_max == 9.0 and other.model.settings.nu == 0.02
    assert (
        other.model.use_periodic is True
        and other.model.sample_steps == 300
        and other.last_dir == "/somewhere"
    )
    other.close()


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_the_window_draws_empty_and_populated_at_every_size(fitted, size):
    ui = fitted
    ui.resize(size)
    run(ui)
    ui.resize(size)
    ui.app.model.lcurve = execute_job({"kind": "lcurve", "snapshot": ui.app.model.snapshot()})
    ui.draw(3)


def test_no_text_runs_past_the_window_edge_in_the_small_window(fitted):
    ui = fitted
    ui.resize(SMALL)
    for x, y, w, h, align, string, *_ in ui.draw(3).texts:
        assert x + w <= SMALL[0] + 1, (x, w, string)


def test_every_control_has_a_tooltip(fitted):
    from test.gui.emtk_port_parity import emtk_inventory

    missing = set(emtk_inventory(fitted.app, SIZE)["controls_without_tooltip"])
    fitted.app.model.settings.mode = "fret"
    missing |= set(emtk_inventory(fitted.app, SIZE)["controls_without_tooltip"])
    assert not missing, sorted(missing)


def test_every_spec_field_exists_on_the_form_object_and_is_described():
    form = __import__(
        "chisurf.plugins.fluorescence_decay.maxent_decay.gui.model", fromlist=["x"]
    ).MEMForm(MEMModel())
    spec = json.loads((PLUGIN / "gui" / "maxent_emtk.view.json").read_text())["panels"]

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "toggle", "choice"):
                assert hasattr(form, s["attr"]), s["attr"]
                assert s.get("description"), s["attr"]
            if s.get("type") == "panel":
                assert s.get("description"), s.get("title")
            walk(s.get("sections", []))

    for panel in spec.values():
        walk(panel["sections"])


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("maxent_decay")
    assert result["ok"], result["output"]


def test_zzz_the_real_chisurf_folder_was_not_touched():
    assert snapshot_real() == REAL_BEFORE
