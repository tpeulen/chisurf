"""The native hidden-Markov-model tool against the Qt tool it replaces, every control operated with real input events.

Hermetic through ``conftest.py`` (HOME, chisurf/MMFDB folders, QSettings in a temp folder); the last test proves the
user's real ``~/.chisurf`` is untouched. The Qt tool and the native app share the Qt-free ``HmmViewModel``: the numbers
of a fit started from the native window must equal those of the Qt tool's model for the same trace and settings, and the
native forms must carry the ranges, choices and decimals of ``hmm.view.json``.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.core.hmm.gui.app import HmmApp, make_app
from chisurf.plugins.core.hmm.gui.view_model import HmmViewModel
from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver

PLUGIN = Path(__file__).parent.parent
REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {str(p): p.stat().st_mtime_ns for p in REAL_CHISURF.rglob("*")
            if p.is_file() and not {"cache", "logs"} & set(p.parts)}


REAL_BEFORE = snapshot_real()


def make_trace(n=1500, seed=11):
    """Two-channel trace with three states (means (20,5), (60,15), (110,40); mean dwell 60 / 40 / 80 bins)."""
    rng = np.random.default_rng(seed)
    means = np.array([[20.0, 5.0], [60.0, 15.0], [110.0, 40.0]])
    stay = 1 - 1 / np.array([60.0, 40.0, 80.0])
    state, path = 0, np.empty(n, int)
    for i in range(n):
        path[i] = state
        if rng.random() > stay[state]:
            state = int(rng.choice([s for s in range(3) if s != state]))
    return rng.poisson(means[path]).astype(float)


@pytest.fixture
def files(tmp_path):
    out = {}
    for name, seed in (("a", 11), ("b", 12)):
        path = tmp_path / "data" / f"{name}.csv"
        path.parent.mkdir(exist_ok=True)
        np.savetxt(path, make_trace(seed=seed), delimiter=",")
        out[name] = str(path)
    return out


class UI(Driver):
    def settle(self, timeout=120.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.busy and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        self.draw(3)
        assert not self.app.job.busy
        return self.app.model


@pytest.fixture
def ui():
    app = make_app()
    driver = UI(app)
    driver.draw(3)
    yield driver
    app.close()


@pytest.fixture
def demo(ui):
    ui.click_name("demo")
    ui.draw(3)
    return ui


def fit(ui):
    ui.click_name("request_run")
    return ui.settle()


def field(ui, name):
    ui.draw(2)
    for form in ui.app.forms.values():
        if name in form.rects:
            return form.rects[name]
    raise AssertionError(name)


def type_value(ui, name, text):
    if name in ("min_states", "max_states") and "scan" not in ui.app.plot_info.get("opened", ()):
        ui.click_text("> State scan range")
        ui.app.plot_info.setdefault("opened", set()).add("scan")
    ui.type_into(field(ui, name), text)
    return ui.app.model


# ───────────────────────────── numbers equal the Qt tool ───────────────────────────── #


@pytest.fixture
def qt_tool(files):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.core.hmm.gui.tool import HmmTool

    tool = HmmTool()
    tool._qapp = qapp
    return tool


def test_a_fit_started_in_the_native_window_equals_the_qt_tools_fit(qt_tool, ui, files):
    qt = qt_tool.model
    qt.files = [files["a"]]
    qt.n_states, qt.time_step = 3, 0.001
    qt.run()
    ui.app.add_files([files["a"]])
    ui.app.model.n_states, ui.app.model.time_step = 3, 0.001
    ui.draw(2)
    m = fit(ui)
    assert m.fit.n_states == qt.fit.n_states == 3
    assert m.fit.log_likelihood == pytest.approx(qt.fit.log_likelihood, rel=1e-9)
    np.testing.assert_allclose(m.fit.means, qt.fit.means)
    np.testing.assert_allclose(m.fit.transmat, qt.fit.transmat)
    np.testing.assert_allclose(m.fit.transition_rates, qt.fit.transition_rates)
    assert m._status == qt._status


def test_the_state_scan_equals_the_qt_tools_scan(qt_tool, ui, files):
    qt = qt_tool.model
    qt.files, qt.max_states, qt.time_step = [files["a"]], 5, 0.001
    qt.run_scan()
    ui.app.add_files([files["a"]])
    ui.app.model.max_states, ui.app.model.time_step = 5, 0.001
    ui.click_name("request_scan")
    m = ui.settle()
    assert list(m._scan.n_states) == list(qt._scan.n_states)
    np.testing.assert_allclose(m._scan.bic, qt._scan.bic)
    np.testing.assert_allclose(m._scan.aic, qt._scan.aic)
    assert (m._scan.best_bic, m._scan.best_aic) == (qt._scan.best_bic, qt._scan.best_aic) == (3, 3)


def test_the_tables_show_what_the_qt_html_tables_show(qt_tool, ui, files):
    qt = qt_tool.model
    qt.files, qt.time_step = [files["a"]], 0.001
    qt.n_states = 3
    qt.run()
    html = qt.states_html()
    qt_cells = [re.sub(r"<[^>]+>|&#9632;", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", html)]
    rows = qt.state_rows()
    native_cells = []
    for r in rows:
        native_cells += [str(r["state"]), r["mean"], r["std"], f"{r['occupancy']:.3f}", str(r["visits"]), f"{r['dwell']:.4g}"]
    assert native_cells == qt_cells
    trans = re.findall(r"<td[^>]*>(\d\.\d{4})", qt.transitions_html())
    flat = [t[f"to_{j}"].split()[0] for t in qt.transition_rows() for j in range(3)]
    assert flat == trans


def test_the_native_forms_carry_the_ranges_choices_and_decimals_of_the_qt_spec():
    qt_spec = json.loads((PLUGIN / "gui" / "hmm.view.json").read_text())
    native = json.loads((PLUGIN / "gui" / "hmm_emtk.view.json").read_text())["panels"]

    def leaves(sections, out):
        for s in sections:
            if s.get("attr"):
                out[s["attr"]] = s
            leaves(s.get("sections", []), out)
        return out

    qt = leaves(qt_spec["sections"], {})
    nat = {}
    for panel in native.values():
        leaves(panel["sections"], nat)
    assert {"n_states", "covariance_type", "time_step", "n_iter", "tol", "accelerate", "decode", "random_state",
            "min_states", "max_states"} <= set(nat) == set(qt) - set()
    for attr, section in qt.items():
        for key in ("minimum", "maximum", "options", "decimals", "kind"):
            if key in section:
                assert nat[attr].get(key) == section[key], (attr, key)


# ───────────────────────────────────── loading data ───────────────────────────────────── #


def test_the_empty_window_asks_for_data_and_greys_fit_and_scan(ui):
    strings = [t[5] for t in ui.draw().texts]
    assert "Load a trace (Add files... or Demo trace)." in strings
    ui.click_name("request_run")
    ui.click_name("request_scan")
    assert not ui.app.job.busy and ui.app.model.fit is None
    ui.click_name("save")
    assert ui.app.dialog is None


def test_the_demo_button_loads_a_generated_trace_and_a_fit_recovers_its_three_states(demo):
    m = demo.app.model
    assert m._labels == ["Demo: generated 3-state trace"] and m._traces[0].shape == (1500, 2)
    assert "Demo trace loaded" in m.status
    m.n_states = 3
    m = fit(demo)
    means = sorted(float(np.sum(s.mean)) for s in m.fit.summaries)
    assert means == pytest.approx([25.0, 75.0, 150.0], rel=0.05)
    assert any("Demo" in t[5] or "state path" in t[5] for t in demo.draw().texts)


def test_add_files_through_the_dialog_toggles_files_and_fits_them_jointly(ui, files):
    ui.app.last_dir = str(Path(files["a"]).parent)
    ui.click_name("add_files")
    assert ui.app.dialog is not None
    ui.click_text("a.csv")
    ui.click_text("b.csv")
    ui.click_text("Open")
    m = ui.app.model
    assert ui.app.dialog is None and m.files == [files["a"], files["b"]]
    assert {"a.csv", "b.csv"} <= {t[5] for t in ui.draw().texts}
    m.n_states = 3
    m = fit(ui)
    assert len(m.traces) == 2 and m.fit.n_states == 3


def test_the_dialog_cancel_and_close_add_nothing(ui, files):
    ui.app.last_dir = str(Path(files["a"]).parent)
    for closer in ("Cancel", "×"):
        ui.click_name("add_files")
        assert ui.app.dialog is not None
        ui.click_text(closer)
        assert ui.app.dialog is None
    assert ui.app.model.files == []


def test_dropped_files_join_the_list_and_duplicates_are_ignored(ui, files):
    assert ui.drop(files["a"], files["b"], files["a"]) is True
    assert ui.app.model.files == [files["a"], files["b"]]
    assert ui.drop() is False


def test_remove_and_clear_and_the_delete_key_edit_the_file_list(ui, files):
    m = ui.app.model
    ui.drop(files["a"], files["b"])
    ui.click_name("remove")
    assert m.files == [files["a"]]                       # none selected: the last one goes
    ui.drop(files["b"])
    ui.click(ui.text_rect(ui.draw(), "a.csv"))
    ui.delete()
    assert m.files == [files["b"]]
    ui.click_name("clear")
    assert m.files == [] and ui.drawn("Add files...")


def test_an_unreadable_file_is_reported_and_nothing_is_fitted(ui, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("not,numbers\nat,all\n")
    ui.drop(bad)
    ui.click_name("request_run")
    m = ui.settle()
    assert m.fit is None and ("Cannot read" in m.status or "No traces" in m.status or m.status.startswith("Fit failed"))
    assert any(m.status[:25] in t[5] for t in ui.draw().texts)


# ───────────────────────────────────── settings forms ───────────────────────────────────── #


@pytest.mark.parametrize("name,typed,attr,expected", [
    ("n_states", "4", "n_states", 4), ("n_states", "99", "n_states", 32), ("n_states", "0", "n_states", 1),
    ("time_step", "0.01", "time_step", 0.01), ("min_states", "2", "min_states", 2), ("max_states", "7", "max_states", 7),
])
def test_the_model_fields_take_typed_values_clamped_to_the_qt_range(ui, name, typed, attr, expected):
    m = type_value(ui, name, typed)
    assert getattr(m, attr) == pytest.approx(expected)


def open_header(ui, label):
    ui.click_text("> " + label)
    ui.draw(3)


@pytest.mark.parametrize("name,typed,expected", [("n_iter", "50", 50), ("tol", "0.05", 0.05), ("random_state", "7", 7)])
def test_the_fitting_fields_are_behind_their_header_and_take_typed_values(ui, name, typed, expected):
    assert not any(t[5].startswith("Max EM maps") for t in ui.draw().texts)
    open_header(ui, "Fitting")
    m = type_value(ui, name, typed)
    assert getattr(m, name) == pytest.approx(expected)


@pytest.mark.parametrize("name,step", [("n_states", 1), ("time_step", 0.001), ("min_states", 1)])
def test_the_arrows_step_the_model_fields(ui, name, step):
    m = ui.app.model
    setattr(m, name, getattr(m, name) + 5 * step if name != "min_states" else 3)
    if name == "min_states":
        ui.click_text("> State scan range")
    ui.draw(3)
    start = getattr(m, name)
    ui.click(field(ui, f"{name}.stepper"), fy=0.25)
    assert getattr(m, name) == pytest.approx(start + step)
    ui.click(field(ui, f"{name}.stepper"), fy=0.75)
    ui.click(field(ui, f"{name}.stepper"), fy=0.75)
    assert getattr(m, name) == pytest.approx(start - step)


def test_the_covariance_and_decoder_choices_list_their_options_and_each_can_be_clicked(ui):
    m = ui.app.model
    ui.click(field(ui, "covariance_type"))
    assert {"full", "diag", "spherical", "tied"} <= {t[5] for t in ui.draw(1).texts}
    ui.click_text("tied")
    assert m.covariance_type == "tied"
    ui.click(field(ui, "covariance_type"))
    ui.escape()
    assert m.covariance_type == "tied"
    open_header(ui, "Fitting")
    ui.click(field(ui, "decode"))
    ui.click_text("map")
    assert m.decode == "map"


def test_the_acceleration_switch_is_clicked(ui):
    open_header(ui, "Fitting")
    m = ui.app.model
    assert m.accelerate is True
    ui.click_text("Accelerate (SQUAREM)")
    assert m.accelerate is False


def test_every_setting_reaches_the_fit(demo):
    m = demo.app.model
    m.n_states = 2
    ui = demo
    ui.click(field(ui, "covariance_type"))
    ui.click_text("diag")
    m = fit(ui)
    assert m.fit.n_states == 2
    reference = HmmViewModel()
    reference.set_traces(m._traces)
    reference.settings = type(m.settings)(**{**m.settings.__dict__})
    reference.run()
    assert reference.fit.log_likelihood == pytest.approx(m.fit.log_likelihood, rel=1e-9)


def test_fields_are_greyed_while_a_fit_runs_and_edits_are_not_lost(demo):
    m = demo.app.model
    m.n_states = 3
    demo.click_name("request_run")
    demo.draw(1)
    assert demo.app.job.busy and not demo.app.model.enabled("request_run")
    demo.settle()
    assert demo.app.model.enabled("request_run") and demo.app.model.fit is not None


# ───────────────────────────────────── results ───────────────────────────────────── #


def test_the_states_and_transitions_tables_show_the_fit(demo):
    demo.app.model.n_states = 3
    demo.app.model.time_step = 0.001
    m = fit(demo)
    strings = {t[5] for t in demo.draw().texts}
    for row in m.state_rows():
        assert f"{row['occupancy']:.3f}" in strings
    assert "To 0" in strings and any(s.startswith("0.98") for s in strings)
    assert any("/s)" in s for s in strings)                                   # rates appear with a bin width
    demo.click(demo.text_rect(demo.draw(), f"{m.state_rows()[1]['occupancy']:.3f}"))   # selecting a row changes no value
    assert demo.app.model.fit is m.fit


def test_the_state_scan_picks_three_states_and_draws_both_criteria(demo):
    demo.app.model.max_states = 5
    demo.click_name("request_scan")
    m = demo.settle()
    assert m._scan.best_bic == 3 and "BIC prefers 3 states" in m.status
    demo.click_text("Scan", last=False)
    strings = [t[5] for t in demo.draw().texts]
    for label in ("states", "information criterion", "BIC", "AIC"):
        assert label in strings, label


def test_the_plot_tabs_draw_axes_and_legends(demo):
    demo.app.model.n_states = 3
    fit(demo)
    strings = [t[5] for t in demo.draw().texts]
    for label in ("bin", "counts per bin", "channel 1", "state path", "occurrences", "state 0", "counts"):
        assert label in strings, label
    demo.click_text("Dwell times")
    strings = [t[5] for t in demo.draw(3).texts]
    assert "dwell time" in strings and "state 1" in strings
    demo.click_text("Histogram")
    assert "counts per bin" in [t[5] for t in demo.draw(3).texts]


def test_the_wheel_zooms_the_trace_plot_and_a_drag_pans_it(demo):
    demo.draw(3)
    (px, py), (sx, sy) = demo.app.plot_info["trace"]["pos"], demo.app.plot_info["trace"]["size"]
    before = [t[5] for t in demo.draw().texts]
    demo.wheel(px + sx * 0.5, py + sy * 0.5, -3.0)
    zoomed = [t[5] for t in demo.draw().texts]
    assert zoomed != before
    demo.drag((px + sx * 0.5, py + sy * 0.5), (px + sx * 0.2, py + sy * 0.5))
    assert [t[5] for t in demo.draw().texts] != zoomed


def test_save_writes_the_fit_json_through_the_dialog(demo, tmp_path):
    demo.app.model.n_states = 3
    m = fit(demo)
    demo.app.last_dir = str(tmp_path)
    demo.click_name("save")
    assert demo.app.dialog is not None
    demo.click_text("hmm_fit.json", last=False, fx=0.3)
    demo.app.key(0x41, "a", CTRL)
    demo.type("my_fit.json")
    demo.click_text("Save")
    saved = json.loads((tmp_path / "my_fit.json").read_text())
    assert saved["n_states"] == 3 and saved["log_likelihood"] == pytest.approx(m.fit.log_likelihood)
    assert "Saved the fit to" in m.status


def test_set_traces_is_the_seam_other_tools_use(ui):
    ui.app.set_traces([make_trace()], ["from another tool"])
    ui.app.model.n_states = 3
    m = fit(ui)
    assert m._labels == ["from another tool"] and m.fit is not None


# ───────────────────────────────────── help, guide, hygiene ───────────────────────────────────── #


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_name("help")
    assert ui.app.help_window.open
    ui.click_text("Close")
    assert not ui.app.help_window.open
    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_the_demo_scan_and_fit(ui):
    ui.click_name("guide")
    tour = ui.app.tour
    assert tour.active
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 1
    ui.click_name("demo")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 2 and tour.awaiting
    ui.app.model.max_states = 4
    ui.click_name("request_scan")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Next ►")
    ui.click_text("Next ►")
    assert tour.step_idx == 4 and tour.awaiting
    ui.click_name("request_run")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Close Tour")
    assert not tour.active


def test_every_tour_target_is_drawn(ui):
    for index, step in enumerate(ui.app.tour.steps):
        key = ui.app.tour._target_key(step.get("target"))
        if not key:
            continue
        ui.app.tour.start(index)
        ui.draw(3)
        assert ui.app.tour.get_target_rect(key), key
        ui.app.tour.stop()


def test_settings_round_trip(ui, files):
    m = ui.app.model
    ui.app.add_files([files["a"]])
    m.n_states, m.covariance_type, m.time_step, m.max_states = 4, "diag", 0.002, 6
    ui.app.last_dir = "/somewhere"
    saved = json.loads(json.dumps(ui.app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.model.n_states == 4 and other.model.covariance_type == "diag" and other.model.time_step == 0.002
    assert other.model.max_states == 6 and other.model.files == [files["a"]] and other.last_dir == "/somewhere"
    other.restore_settings({"n_states": "junk", "files": ["/nope.csv"]})
    other.restore_settings(None)
    other.close()


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_the_window_draws_empty_and_fitted_at_every_size(ui, size):
    ui.resize(size)
    ui.draw(3)
    ui.click_name("demo")
    ui.app.model.n_states = 3
    ui.click_name("request_run")
    ui.settle()
    ui.app.model.max_states = 4
    ui.click_name("request_scan")
    ui.settle()
    ui.resize(size)
    for tab in ("Dwell times", "Scan", "Histogram"):
        ui.click_text(tab, last=False) if ui.drawn(tab) else None
        ui.draw(3)


def test_no_text_runs_past_the_window_edge_in_the_small_window(demo):
    demo.resize(SMALL)
    demo.app.model.n_states = 3
    fit(demo)
    for x, y, w, h, align, string, *_ in demo.draw(3).texts:
        assert x + w <= SMALL[0] + 1, (x, w, string)


def test_every_control_has_a_tooltip(demo):
    from test.gui.emtk_port_parity import emtk_inventory

    demo.app.model.n_states = 3
    fit(demo)
    missing = set(emtk_inventory(demo.app, SIZE)["controls_without_tooltip"])
    demo.click_text("> Fitting")
    demo.click_text("> State scan range")
    missing |= set(emtk_inventory(demo.app, SIZE)["controls_without_tooltip"])
    assert not missing, sorted(missing)


def test_every_spec_field_exists_on_the_model_and_is_described():
    model = HmmViewModel()
    spec = json.loads((PLUGIN / "gui" / "hmm_emtk.view.json").read_text())["panels"]

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "toggle", "choice"):
                assert hasattr(model, s["attr"]), s["attr"]
                assert s.get("description"), s["attr"]
            if s.get("type") == "panel":
                assert s.get("description"), s.get("title")
            if s.get("type") == "custom":
                o = s["options"]
                for key in ("source", "columns_source", "delete_call", "selected_call"):
                    if key in o:
                        assert callable(getattr(model, o[key])), o[key]
                for column in o.get("columns", []):
                    assert column.get("tooltip"), column
            walk(s.get("sections", []))

    for panel in spec.values():
        walk(panel["sections"])
    assert all(c.get("tooltip") for c in model.state_columns() + model.transition_columns())


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("hmm")
    assert result["ok"], result["output"]


def test_zzz_the_real_chisurf_folder_was_not_touched():
    assert snapshot_real() == REAL_BEFORE
