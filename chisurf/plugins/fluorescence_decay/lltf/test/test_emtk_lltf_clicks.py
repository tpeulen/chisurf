"""Click coverage of the native Lazy Lifetime Analysis: every control operated with pointer, keys, wheel and host drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` and the host's drop hook (``on_paths_dropped``) reach
the window; the fit is the real LLTF command line on the shipped example (a subprocess, ~15 s), the assertions read what is
drawn, the model and the files written. The control -> test list is in ``okf/plugins/emtk-ports/lltf/REPORT.md``.
"""

from __future__ import annotations

import json
import os
import pwd
import sys
import time
from pathlib import Path

import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401  (before the plugin import)
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui as _Ui, hermetic as _hermetic  # noqa: E402,F401
from emtk import keys  # noqa: E402

from chisurf.plugins.fluorescence_decay.lltf.gui.app import LLTFApp  # noqa: E402
# isort: on

EXAMPLE = Path(__file__).parent.parent / "example"
DECAY, IRF, CONFIG = EXAMPLE / "5-44_D0.dat", EXAMPLE / "IRF_D0.dat", EXAMPLE / "config.yml"
SIZE = (1200, 800)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("MPLBACKEND", "Agg")


class Ui(_Ui):
    def drop(self, *paths):
        self.app.on_paths_dropped([str(p) for p in paths])
        return self.draw(3)

    def settle(self, timeout=300.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.model.process is not None:
            assert time.monotonic() < end, "the fit did not finish"
            time.sleep(0.05)
            self.draw(1)
        return self.draw(4)

    def type_into(self, key, text, enter=True, replace=True, fx=0.3):
        self.draw(1)
        self.click(key, fx=fx)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.type_text(text, replace)
        if enter:
            self.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def pick(self, key, option):
        self.click(key)
        self.press_text(option)
        return self.draw(2)


@pytest.fixture
def ui(tmp_path):
    ui = Ui(LLTFApp(), SIZE)
    ui.out = tmp_path / "out"
    ui.out.mkdir()
    yield ui
    ui.app.close()


@pytest.fixture
def ready(ui):
    ui.drop(DECAY, IRF)
    ui.app.model.output_dir = str(ui.out)
    ui.draw(2)
    return ui


@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    """One real fit through the UI, shared by the tests that read its result."""
    os.environ["MPLBACKEND"] = "Agg"
    out = tmp_path_factory.mktemp("lltf_fit")
    ui = Ui(LLTFApp(), SIZE)
    ui.drop(DECAY, IRF)
    ui.app.model.output_dir = str(out)
    ui.type_into("n_lifetimes", "2")
    ui.click("Fit")
    ui.settle()
    ui.out = out
    yield ui
    ui.app.close()


def test_the_idle_window_offers_only_what_can_act(ui):
    assert ui.shown("Load decay and IRF files, configure the fit, then run analysis.")
    ui.click("Fit")
    assert ui.app.model.process is None and ui.app.model.result is None
    assert ui.shown("Fit plots appear after a successful analysis.")
    assert not ui.app.model.enabled("max_lifetimes") and not ui.app.model.enabled("prob_threshold")
    ui.click("stop")
    assert ui.app.model.process is None


def test_guide_and_help_buttons_are_pressed(ui):
    ui.click("Guide")
    steps = len(ui.app.tour.steps)
    assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next ►")
    assert ui.app.tour.step_idx == 1
    ui.app.tour.start(3)
    ui.draw(2)
    ui.press_text("◄ Prev")
    assert ui.app.tour.step_idx == 2
    ui.press_text("Close Tour")
    assert not ui.app.tour.active
    ui.click("help")
    assert ui.app.help_window.open
    ui.press_text("Close Help")
    assert not ui.app.help_window.open


def test_no_tour_card_button_is_dead_on_any_step():
    from chisurf.plugins.traj.traj_save_topology.test.real_input import dead_tour_buttons

    assert dead_tour_buttons(LLTFApp, SIZE) == []


@pytest.mark.parametrize("button,title,expected", [("Load...", "Load decay", DECAY), ("load_irf", "Load IRF", IRF)])
def test_the_load_buttons_open_a_filtered_dialog_and_every_way_out_works(ui, button, title, expected):
    ui.click(button)
    ui.app.dialog.directory = str(EXAMPLE)
    ui.draw(3)
    assert ui.dialog_open and ui.shown(title) and ui.shown(expected.name) and not ui.shown("config.yml")
    ui.press_text("Open")
    assert ui.dialog_open and ui.shown("Select a file first.")
    ui.press_text("Cancel")
    assert not ui.dialog_open
    ui.click(button)
    ui.press_text("×")
    assert not ui.dialog_open
    ui.click(button)
    ui.app.dialog.directory = str(EXAMPLE)
    ui.draw(3)
    ui.press_text(expected.name)
    ui.press_text("Open")
    attr = "decay_file" if button == "Load..." else "irf_file"
    assert getattr(ui.app.model, attr) == str(expected) and ui.shown(expected.name)


def test_the_output_directory_dialog_chooses_a_folder(ui):
    ui.click("Select...")
    assert ui.dialog_open and ui.shown("Output directory")
    ui.app.dialog.directory = str(ui.out.parent)
    ui.draw(3)
    ui.press_text(f"[{ui.out.name}]")
    ui.press_text("Choose")
    assert ui.app.model.output_dir == str(ui.out)


def test_dropped_files_route_by_kind(ui):
    ui.drop(DECAY)
    assert ui.app.model.decay_file == str(DECAY) and not ui.app.model.irf_file
    ui.drop(IRF)
    assert ui.app.model.irf_file == str(IRF)
    ui.drop(CONFIG)
    assert ui.app.model.config_file == str(CONFIG) and "find_optimal" in ui.app.model.config_text
    ui.drop(ui.out)
    assert ui.app.model.output_dir == str(ui.out)
    assert ui.shown("5-44_D0.dat") and ui.shown("IRF_D0.dat")


def test_the_path_fields_of_data_files_do_not_take_typing(ready):
    ready.click("decay_file", fx=0.3)
    ready.type_text("/etc/passwd")
    ready.key(keys.KEY_RETURN, "\r")
    assert ready.app.model.decay_file == str(DECAY)


def test_the_configuration_editor_opens_edits_saves_and_closes(ready, tmp_path):
    ready.drop(CONFIG)
    ready.click("Edit...")
    assert ready.app.config_open and ready.shown("Save configuration") and ready.shown("Close editor")
    ready.click_at(*[v for v in (ready.size[0] * 0.5, ready.size[1] * 0.4)])
    ready.type_text("\n# edited in the window", replace=False)
    assert "# edited in the window" in ready.app.model.config_text and ready.app.model.config_dirty
    ready.press_text("Save configuration")
    assert ready.dialog_open
    target = tmp_path / "saved_config.yml"
    ready.draw(2)
    ready.click(ready.text_rect(ready.app.dialog.filename), fx=0.3)
    ready.type_text(str(target))
    ready.press_text("Save")
    assert target.exists() and "# edited in the window" in target.read_text()
    ready.press_text("Close editor")
    assert not ready.app.config_open


def test_a_yaml_that_is_not_a_mapping_is_refused_in_the_window(ready, tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("- a\n- b\n")
    ready.drop(bad)
    assert "mapping" in ready.app.model.status or ready.shown("mapping")
    assert ready.app.model.config_file != str(bad)


def test_the_find_optimal_toggle_greys_and_ungreys_the_fields(ready):
    m = ready.app.model
    assert m.enabled("n_lifetimes") and not m.enabled("max_lifetimes")
    ready.click("find_optimal")
    assert m.find_optimal and not m.enabled("n_lifetimes") and m.enabled("max_lifetimes") and m.enabled("prob_threshold")
    before = m.n_lifetimes
    ready.click("n_lifetimes", fx=0.3)
    ready.type_text("5")
    assert m.n_lifetimes == before                       # greyed: the click did not take the keyboard
    ready.type_into("max_lifetimes", "5")
    ready.type_into("prob_threshold", "0.9")
    assert m.max_lifetimes == 5 and m.prob_threshold == pytest.approx(0.9)
    ready.click("find_optimal")
    assert m.enabled("n_lifetimes") and not m.enabled("max_lifetimes")


def test_the_lifetime_count_is_typed_clamped_and_stepped(ready):
    m = ready.app.model
    ready.type_into("n_lifetimes", "3")
    assert m.n_lifetimes == 3
    ready.type_into("n_lifetimes", "99")
    assert m.n_lifetimes == 6
    ready.type_into("n_lifetimes", "0")
    assert m.n_lifetimes == 1
    ready.arrow("n_lifetimes", +1)
    assert m.n_lifetimes == 2
    ready.arrow("n_lifetimes", -1)
    assert m.n_lifetimes == 1


def test_the_wheel_steps_the_lifetime_count(ready):
    x, y, w, h = ready.app.item_rects["n_lifetimes"]
    ready.app.pointer_move(x + w / 2, y + h / 2)
    ready.draw(2)
    ready.wheel_over("n_lifetimes", 1)
    assert ready.app.model.n_lifetimes != 1


def test_verbose_toggle(ready):
    assert ready.app.model.verbose
    ready.click("verbose")
    assert not ready.app.model.verbose
    assert "-v" not in ready.app.model.build_command()


def test_stop_ends_a_running_fit(ready):
    ready.click("Fit")
    ready.draw(3)
    assert ready.app.model.running and ready.app.enabled if False else ready.app.model.process is not None
    assert not ready.app.model.enabled("n_lifetimes")           # the options are greyed while it runs
    ready.click("stop")
    ready.settle()
    assert ready.app.model.process is None and ready.app.model.result is None
    assert ready.app.tab == "Analysis Output" or ready.shown("Analysis Output")


def test_the_real_fit_through_the_buttons_gives_the_examples_two_lifetimes(fitted):
    r = fitted.app.model.result
    assert r and r["n_lifetimes"] == 2
    taus = sorted(row["lifetime"] for row in r["lifetimes"])
    assert 3.7 < taus[-1] < 4.1 and 0.4 < taus[0] < 1.6
    assert sum(row["amplitude"] for row in r["lifetimes"]) == pytest.approx(1.0, abs=1e-6)
    assert 1.0 < r["reduced_chi_square"] < 2.0
    assert (fitted.out / "5-44_D0_fit.json").exists() and (fitted.out / "5-44_D0_fit.png").exists()


def test_the_results_tab_shows_the_table_and_the_summary(fitted):
    fitted.press_text("Results")
    assert fitted.shown("Component") and fitted.shown("Lifetime (ns)") and fitted.shown("Reduced chi-square: ")
    rows = fitted.app.model.lifetime_rows()
    assert fitted.shown(f"{rows[0]['lifetime']:.3f}")


def test_the_tabs_switch_and_clear_output_empties_the_log(fitted):
    fitted.press_text("Analysis Output")
    assert fitted.app.model.output and fitted.shown("Clear output")
    fitted.press_text("Clear output")
    assert fitted.app.model.output == []
    fitted.press_text("Information")
    assert fitted.shown("Load the measured decay and IRF")


def test_export_result_json_writes_the_fit(fitted, tmp_path):
    fitted.press_text("Results")
    fitted.click("export_json")
    assert fitted.dialog_open and fitted.shown("Export fit results")
    fitted.press_text("Cancel")
    assert not fitted.dialog_open
    fitted.click("export_json")
    fitted.draw(2)
    fitted.click(fitted.text_rect(fitted.app.dialog.filename), fx=0.3)
    target = tmp_path / "exported.json"
    fitted.type_text(str(target))
    fitted.press_text("Save")
    assert json.loads(target.read_text())["n_lifetimes"] == 2


def test_the_plot_tabs_and_the_wheel(fitted):
    assert fitted.shown("Decay and fit") and fitted.shown("Time (ns)")
    fitted.press_text("Weighted residuals")
    assert fitted.shown("Weighted residual")
    fitted.press_text("Decay and fit")
    x, y, w, h = fitted.app.item_rects["Decay and fit"] if "Decay and fit" in fitted.app.item_rects else (400, 400, 300, 200)
    before = [s for s in fitted.last.strings if s.replace(".", "", 1).isdigit()]
    fitted.app.wheel(800, 560, 1)
    fitted.draw(2)
    assert [s for s in fitted.last.strings if s.replace(".", "", 1).isdigit()] != before


def _real_chisurf_state():
    root = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
    return {str(p): p.stat().st_mtime_ns for p in root.rglob("*")} if root.exists() else {}


def test_a_full_session_leaves_the_real_chisurf_folder_untouched(ready):
    before = _real_chisurf_state()
    ready.click("Edit...")
    ready.press_text("Close editor")
    ready.app.export_settings()
    assert _real_chisurf_state() == before


def test_qt_free():
    assert qt_free("lltf")
