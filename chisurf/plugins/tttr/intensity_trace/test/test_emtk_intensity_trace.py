"""The native intensity-trace tool: the Qt tool's numbers, and real input (presses at drawn rects, typed keys, dialogs).

Data: the tool's own demo (a molecule switching between two FRET states, dwell 20 / 80 ms, two detectors) and a temp
copy of BH_SPC132.spc for the numbers the Qt widget recorded (``okf/plugins/emtk-ports/intensity_trace/qt_values.json``;
Compute HMM writes beside the file, so never on the repository's copy). Hermetic: temp settings and HOME.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.intensity_trace.gui.app import make_app
from chisurf.plugins.tttr.intensity_trace.model import IntensityTraceModel

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
SPC = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"
QT = REPO / "okf/plugins/emtk-ports/intensity_trace/qt_values.json"
CTRL_A = 0x04000000
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


class Ui:
    def __init__(self, app, size=(1200, 800)):
        self.app, self.size, self.last = app, size, None
        self.draw(3)

    def draw(self, n=2):
        for _ in range(n):
            self.last = RecordingPainter()
            self.app.draw(self.last, 0, 0, *self.size)
        return self.last

    def settle(self, timeout=300):
        end = time.monotonic() + timeout
        while self.app.busy:
            assert time.monotonic() < end, "the work did not finish"
            time.sleep(0.02)
            self.draw(1)
        return self.draw(2)

    def click_at(self, x, y):
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.press(x, y)
        self.draw(1)
        self.app.release()
        return self.draw(2)

    def reveal(self, key, dock="controls"):
        """Wheel *dock* until the control is inside it (as a user scrolls to it); its rectangle."""
        for _ in range(30):
            self.draw(1)
            x, y, w, h = self.app.item_rects[key]
            bx, by, bw, bh = self.app.docks.windows[dock].content
            if by <= y and y + h <= by + bh:
                return x, y, w, h
            cx, cy = bx + 4, by + bh / 2
            self.app.pointer_move(cx, cy)
            self.draw(1)
            self.app.wheel(cx, cy, -2 if y + h > by + bh else 2)
            self.draw(1)
        raise AssertionError(f"{key} cannot be scrolled into view in {dock}")

    def click(self, key, fx=0.5, fy=0.5):
        dock = "results" if key.startswith("result.") else "controls"
        x, y, w, h = self.reveal(key, dock)
        return self.click_at(x + w * fx, y + h * fy)

    def press_text(self, label, nth=0):
        hits = [t[:4] for t in self.draw(1).texts if t[5] == label]
        assert hits, f"{label!r} not drawn"
        x, y, w, h = hits[nth]
        return self.click_at(x + w / 2, y + h / 2)

    def type_into(self, key, text):
        self.click(key, fx=0.3)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.app.key(0x41, "a", CTRL_A)
        self.draw(1)
        for ch in text:
            self.app.key(ord(ch), ch)
            self.draw(1)
        self.app.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def shown(self, text):
        return any(text in s for s in self.draw(1).strings)


@pytest.fixture
def spc(tmp_path):
    if not SPC.exists():
        pytest.skip("SPC test data not available")
    dst = tmp_path / "data" / SPC.name
    dst.parent.mkdir()
    shutil.copy(SPC, dst)
    return dst


# ---- the Qt tool's numbers ------------------------------------------------------------------------------------------


def test_the_model_reproduces_the_qt_tools_trace_hmm_and_outputs(spc):
    """Qt bound with no setup bins its first ticked routing channel (Ch0); the same selection gives the same numbers."""
    qt = json.loads(QT.read_text())
    m = IntensityTraceModel(selected=["routing_0"])
    assert m.load(spc)
    assert m.labels == qt["channels"] and m.counts.shape[0] == qt["n_bins"]
    assert m.counts.sum(axis=0).tolist() == qt["counts_sum"]
    m.n_states = 3
    m.run_hmm()
    assert np.bincount(m.states).tolist() == qt["state_counts"]
    assert np.allclose(np.asarray(m.transmat), qt["transmat"], atol=1e-4)
    base = m.export()
    assert sorted(p.name for p in base.rglob("*") if p.is_file()) == sorted(Path(p).name for p in qt["outputs"])


def test_without_a_setup_every_channel_the_file_uses_is_offered(spc):
    m = IntensityTraceModel()
    m.load(spc)
    assert m.choices() == ["routing_0", "routing_1", "routing_8", "routing_9"]  # Qt offered 0-7 only
    assert m.labels == ["Ch0", "Ch1", "Ch8", "Ch9"]


# ---- real input -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_example_hmm_and_results_by_pointer_and_keyboard(size):
    ui = Ui(make_app(), size)
    m = ui.app.model
    ui.click("request_example")
    ui.settle()
    assert m.labels == ["Ch0", "Ch1"] and m.window_ms == 2.0
    ui.type_into("window_ms", "5")
    ui.settle()
    assert m.window_ms == 5.0 and m.counts.shape[0] == 4001  # 20 s in 5 ms bins
    ui.click("det.routing_1")
    ui.settle()
    assert m.labels == ["Ch0"]
    ui.click("det.routing_1")
    ui.settle()
    assert m.labels == ["Ch0", "Ch1"]
    ui.type_into("n_bins", "60")
    assert m.n_bins == 60
    ui.click("tab_HMM")
    ui.type_into("n_states", "2")
    ui.click("request_hmm")
    ui.settle()
    assert m.states is not None and len(np.unique(m.states)) == 2
    assert ui.shown("Written to intensity_trace_demo_HMM#2_5ms/")
    fret = sorted(float(np.mean(v)) for v in m.fret_by_state().values())
    assert fret[0] == pytest.approx(0.3, abs=0.05) and fret[1] == pytest.approx(0.7, abs=0.05)
    for button, result in (("request_dwell", "Dwell Times"), ("request_matrix", "HMM Matrix"),
                           ("request_fret", "FRET Distributions")):
        ui.click(button)
        assert ui.app.result == result
    ui.click("result.Dwell Times")
    assert ui.shown("Save Histograms and Fits") and ui.shown("τ =")
    ui.app.close()


def test_bic_elbow_and_the_save_dialogs(tmp_path):
    ui = Ui(make_app())
    ui.click("request_example")
    ui.settle()
    ui.click("tab_HMM")
    ui.click("request_bic")
    ui.settle(600)
    assert len(ui.app.bics) == 15 and ui.app.result == "BIC Elbow"
    ui.app.model.n_states = 2
    ui.click("request_hmm")
    ui.settle()
    ui.click("tab_Processing")
    ui.click("request_save_traces")
    assert ui.app.dialog is not None
    ui.app.dialog.enter(str(tmp_path))
    ui.draw(2)
    ui.press_text("Save")
    rows = np.loadtxt(tmp_path / "traces.csv", delimiter=",", skiprows=1)
    assert rows.shape == (ui.app.model.counts.shape[0], 4)  # time, Ch0, Ch1, state
    ui.click("result.Dwell Times")
    ui.press_text("Save Histograms and Fits")
    ui.app.dialog.enter(str(tmp_path))
    ui.draw(2)
    ui.press_text("Save")
    text = (tmp_path / "dwell_times.csv").read_text()
    assert text.startswith("State,BinCenter,Count") and ",tau," in text
    ui.app.close()


def test_load_dialog_drop_and_setup_choice(spc, monkeypatch):
    ui = Ui(make_app())
    ui.click("request_load")
    ui.app.dialog.enter(str(spc.parent))
    ui.draw(2)
    ui.press_text(spc.name)
    ui.press_text("Open")
    ui.settle()
    assert ui.app.model.labels == ["Ch0", "Ch1", "Ch8", "Ch9"]
    other = make_app()
    assert other.on_files_dropped([str(spc)])
    other.wait()
    assert other.model.loaded
    # a detector setup: green = 0, 8; red = 1, 9
    setup = {"detectors": {"green": {"chs": [0, 8], "micro_time_ranges": []},
                           "red": {"chs": [1, 9], "micro_time_ranges": []}}}
    ui.app.setups = {"setups": {"Bench": setup}}
    ui.click("setup_name")
    ui.press_text("Bench")
    ui.settle()
    assert ui.app.model.labels == ["green", "red"] and ui.shown("green")
    totals = ui.app.model.counts.sum(axis=0)
    assert totals[0] > 0 and totals[1] > 0
    for app in (ui.app, other):
        app.close()


def test_edit_setups_opens_the_shared_detector_editor_and_a_change_rebins(spc):
    ui = Ui(make_app())
    ui.app.open_file(str(spc))
    ui.settle()
    ui.click("request_edit_setup")
    assert ui.app.docks.selected["results"] == "setup"
    assert ui.shown("PIE windows") or ui.shown("Detectors")  # the shared editor is drawn
    setup = {"detectors": {"green": {"chs": [0, 8], "micro_time_ranges": []},
                           "red": {"chs": [1, 9], "micro_time_ranges": []}}}
    ui.app.setup_edited(setup)  # what the editor calls on every change
    ui.settle()
    assert ui.app.model.labels == ["green", "red"]
    assert ui.app.setup_name == "Edited setup" and ui.shown("Edited setup")
    ui.click("tab_HMM")
    ui.app.model.states = np.zeros(ui.app.model.counts.shape[0], dtype=int)
    ui.click("request_dwell")
    assert ui.app.docks.selected["results"] == "results"  # a result brings the results tab back
    ui.app.close()


def test_help_and_the_tour_waits_for_the_user():
    ui = Ui(make_app())
    ui.click("request_help")
    assert ui.app.help.open
    ui.press_text("Close Help")
    ui.click("request_guide")
    tour = ui.app.tour
    assert tour.active and len(tour.steps) >= 5
    ui.press_text("Next ►")
    assert tour.awaiting
    ui.click("request_example")
    ui.settle()
    assert not tour.awaiting
    ui.app.close()


def test_the_native_app_loads_without_qt():
    import subprocess

    code = ("import sys; import chisurf.plugins.tttr.intensity_trace.gui.app; "
            "print(any(m.split('.')[0] in ('qtpy', 'PyQt5') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO,
                         env={**__import__("os").environ}).stdout.strip()
    assert out == "False"
