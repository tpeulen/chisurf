"""The native HydroPro against the Qt tool it replaces: the same recorded program output gives the same numbers.

Hermetic (``conftest.py``): HOME, settings, MMFDB and ``QSettings`` are temporary; the HYDRO program is
``data/fake_hydro.sh``, which replies with the recorded reports in ``data/recorded/`` and computes nothing. Both tools
run the same ``core.run_hydro``; what is compared here is everything around it: the table cells, the status, the
output log, the CSV, the input file written for each parameter set, the spin-box limits and steps, the persisted
values. A module guard fails the run when the owner's real HydroPRO plist or ``~/.chisurf`` changed.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.project_browser.test.driving import clipped_texts, draw_clip, layout_problems
from chisurf.plugins.modelling.hydropro.app import HydroProApp, build_spec, make_app
from chisurf.plugins.modelling.hydropro.core import HydroProSettings
from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel, format_diffusion

from . import hermetic
from .support import BIG, EXPECTED, REPO, SMALL, drain, make_world

PLUGIN = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "okf/plugins/emtk-ports/hydropro"


@pytest.fixture(scope="module", autouse=True)
def real_state_untouched():
    state = hermetic.RealState()
    yield
    assert state.changes() == []


@pytest.fixture
def world():
    return make_world(Path.home())


@pytest.fixture
def qt(monkeypatch, world):
    """A Qt HydroProTool offscreen whose message boxes and file dialogs are recorded, not shown."""
    pytest.importorskip("qtpy.QtWidgets")
    from qtpy import QtWidgets

    from chisurf.plugins.modelling.hydropro.gui import tool as tool_module

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    boxes = []
    for name in ("warning", "information", "error"):
        monkeypatch.setattr(tool_module.dialogs, name, lambda parent, title, text, _n=name: boxes.append((_n, title, text)))
    hermetic.assert_no_leaks()  # a module holding the real QSettings would write the owner's plist on Run
    tool = tool_module.HydroProTool()
    assert tool._qsettings.fileName().endswith(".ini") and "Library/Preferences" not in tool._qsettings.fileName()

    class Qt:
        pass

    q = Qt()
    q.tool, q.boxes, q.app = tool, boxes, qapp
    q.save_to = None

    def run(timeout=60.0):
        tool._on_run()
        end = time.monotonic() + timeout
        while tool._thread is not None and time.monotonic() < end:
            qapp.processEvents()
            time.sleep(0.01)
        qapp.processEvents()
        assert tool._thread is None

    q.run = run
    yield q
    tool.close()


def native(world, **fields):
    model = HydroProModel()
    model.exe_path = str(fields.pop("exe", world["exe"]))
    for key, value in fields.items():
        setattr(model, key, value)
    return model


def files(world, *stems):
    return ", ".join(str(world["files"][s]) for s in stems)


def qt_set(q, world, stems, exe=None, **fields):
    m = q.tool._model
    m.exe_path = str(exe or world["exe"])
    m.struct_files = files(world, *stems)
    for key, value in fields.items():
        setattr(m, key, value)
    q.tool._form.rebuild()
    q.tool._refresh_table_files()


def qt_cells(q):
    return [(q.tool.table.item(r, 0).text(), q.tool.table.item(r, 1).text()) for r in range(q.tool.table.rowCount())]


def job_input(home, name="hydropro.dat"):
    return (home / ".hydropp_gui/job_001" / name).read_text()


# -- the numbers of a run -------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("stems", [("148l",), ("148l", "small", "plain", "garbled", "silent"), ("small", "148l")])
def test_the_table_status_and_csv_equal_the_qt_tool_for_the_same_recorded_output(qt, world, stems, tmp_path):
    qt_set(qt, world, stems)
    qt.run()
    qt_status, qt_table, qt_log = qt.tool._model.status, qt_cells(qt), qt.tool._out_dlg.log.toPlainText()

    model = native(world, struct_files=files(world, *stems))
    model.run()
    drain(model)
    rows = [(r["file"], r["d"]) for r in model.result_rows()]
    assert model.status == qt_status == f"Finished: {len(stems)} file(s)."
    assert rows == qt_table
    assert model.log_text == qt_log
    # The recorded values arrive as the parser reads them, formatted as the Qt table formats them.
    for stem, (_path, cell) in zip(stems, rows):
        want = EXPECTED[stem]
        assert cell == (f"{want:.3e}" if want is not None else "N/A")
    # CSV: byte for byte what the Qt tool wrote.
    from qtpy import QtWidgets

    qt_csv = tmp_path / "qt.csv"
    QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(qt_csv), ""))
    qt.tool._save_csv()
    mine = tmp_path / "mine.csv"
    assert model.write_csv(mine)
    assert mine.read_bytes() == qt_csv.read_bytes()
    assert qt.boxes[-1][1] == "Saved" and model.notices[-1] == ("Saved", f"Results saved to {mine}")


def test_the_hydropp_flavour_equal_the_qt_tool(qt, world):
    qt_set(qt, world, ("148l", "small"), exe=world["hpp"])
    qt.run()
    qt_table, qt_dat = qt_cells(qt), job_input(world["home"], "hydro_input.dat")
    model = native(world, exe=world["hpp"], struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert [(r["file"], r["d"]) for r in model.result_rows()] == qt_table
    assert job_input(world["home"], "hydro_input.dat") == qt_dat
    assert [c for _f, c in qt_table] == ["1.047e-06", "2.500e-07"]


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"indmode": "2", "aer": 4.8, "nsig": -1},
        {"indmode": "4", "aer": 6.1, "t": 25.0, "eta": 0.0089, "rm": 14300.0, "vbar": 0.72, "rho": 1.002},
        {"nq": 20, "qmax": 3.5e7, "ns": 30, "rmax": 1.2e-6, "ntrials": 1000, "idif": False},
        {"nsig": 8, "sigmin": 0.5, "sigmax": 3.0},
    ],
)
def test_every_parameter_set_writes_the_input_file_the_qt_tool_wrote(qt, world, fields):
    qt_set(qt, world, ("148l",), **fields)
    qt.run()
    qt_dat = job_input(world["home"])
    qt_table = qt_cells(qt)
    model = native(world, struct_files=files(world, "148l"), **fields)
    model.run()
    drain(model)
    assert job_input(world["home"]) == qt_dat
    assert [(r["file"], r["d"]) for r in model.result_rows()] == qt_table
    assert model.to_settings() == qt.tool._model.to_settings()


def test_a_failing_run_reports_the_same_error_as_the_qt_tool(qt, world):
    qt_set(qt, world, ("148l",), exe=world["noexec"])
    qt.run()
    qt_status, qt_log = qt.tool._model.status, qt.tool._out_dlg.log.toPlainText()
    assert qt_status.startswith("Error: ") and "Permission denied" in qt_status
    model = native(world, exe=world["noexec"], struct_files=files(world, "148l"))
    model.run()
    drain(model)
    assert model.status == qt_status and model.log_text == qt_log
    assert model.output_status == qt.tool._out_dlg.status_label.text() == "Failed."
    assert model.results == [] and not model.enabled("save_csv") and not qt.tool._save_btn.isEnabled()


def test_the_output_pane_texts_equal_the_qt_dialog(qt, world):
    qt_set(qt, world, ("148l", "small"))
    qt.run()
    dlg = qt.tool._out_dlg
    model = native(world, struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert model.output_status == dlg.status_label.text() == "Finished."
    assert model.done == dlg.progress.value() == dlg.progress.maximum() == model.total == 2
    assert model.progress_text() == "100%"
    assert model.log_lines[0] == f"Executable: {world['exe']}"


def test_the_warnings_equal_the_qt_tool(qt, world):
    # No files.
    qt.tool._model.exe_path = str(world["exe"])
    qt.tool._on_run()
    model = native(world)
    model.run()
    assert qt.boxes[-1][1:] == model.notices[-1] == ("No files", "Please select one or more files first.")
    # Invalid settings (NSIG 2 in a shell mode).
    qt_set(qt, world, ("148l",), nsig=2)
    qt.tool._on_run()
    model = native(world, struct_files=files(world, "148l"), nsig=2)
    model.run()
    assert qt.boxes[-1][1:] == model.notices[-1]
    assert model.notices[-1][0] == "Invalid settings" and "NSIG must be > 2" in model.notices[-1][1]
    assert not model.running
    # QMAX / RMAX rules.
    for fields in ({"nq": 5, "qmax": 0.0}, {"ns": 5, "rmax": 0.0}):
        qt_set(qt, world, ("148l",), **{"nsig": 6, "nq": -1, "ns": -1, "qmax": 0.0, "rmax": 0.0, **fields})
        qt.tool._on_run()
        model = native(world, struct_files=files(world, "148l"), **fields)
        model.run()
        assert qt.boxes[-1][1:] == model.notices[-1]


def test_a_missing_executable_gives_the_qt_prompt_and_the_same_outcomes(qt, world, monkeypatch):
    """Qt: a modal DownloadInfoDialog; Close without a choice -> 'Executable required'; with one -> the run goes on."""
    from chisurf.plugins.modelling.hydropro.gui import tool as tool_module

    # Qt, no executable and the dialog closed with nothing chosen.
    class Closed:
        selected_path = None

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            return 1

    monkeypatch.setattr(tool_module, "DownloadInfoDialog", Closed)
    qt_set(qt, world, ("148l",), exe="/nonexistent/hydropro10.exe")
    qt.tool._model.exe_path = ""
    qt.tool._on_run()
    qt_box = qt.boxes[-1]
    model = native(world, exe="", struct_files=files(world, "148l"))
    model.exe_path = ""
    model.run()
    assert model.exe_prompt and not model.running
    model.close_exe_prompt()
    assert model.notices[-1] == ("Executable required", "Configure the HYDRO executable before running.")
    assert qt_box[1:] == model.notices[-1]

    # Qt dialog that picked an executable: the run continues with it and the field now holds it.
    class Picked:
        selected_path = world["exe"]

        def __init__(self, *a, **k):
            pass

        def exec_(self):
            from qtpy import QtWidgets

            return QtWidgets.QDialog.Accepted

    monkeypatch.setattr(tool_module, "DownloadInfoDialog", Picked)
    qt.tool._model.exe_path = ""
    qt.run()
    assert qt.tool._model.exe_path == str(world["exe"])
    qt_cell = qt_cells(qt)[0][1]
    model.run()
    model.prompt_exe_chosen(world["exe"])
    model.close_exe_prompt()
    drain(model)
    assert model.exe_path == str(world["exe"])
    assert model.result_rows()[0]["d"] == qt_cell == "1.047e-06"


def test_clear_empties_what_the_qt_clear_empties(qt, world):
    qt_set(qt, world, ("148l",))
    qt.run()
    qt.tool._clear()
    model = native(world, struct_files=files(world, "148l"))
    model.run()
    drain(model)
    model.clear()
    assert (model.struct_files, model.status, model.results, model.result_rows()) == (
        qt.tool._model.struct_files, qt.tool._model.status, qt.tool._results, []) == ("", "", [], [])
    assert qt.tool.table.rowCount() == 0 and not qt.tool._save_btn.isEnabled() and not model.enabled("save_csv")


# -- the form -------------------------------------------------------------------------------------------------------- #


def test_defaults_equal_the_qt_models_defaults(qt):
    qm = qt.tool._model
    model = HydroProModel()
    for name in ("exe_path", "struct_files", "indmode", "aer", "nsig", "sigmin", "sigmax", "t", "eta", "rm", "vbar", "rho",
                 "nq", "qmax", "ns", "rmax", "ntrials", "idif", "status"):
        assert getattr(model, name) == getattr(qm, name), name


def _qt_spin_boxes(tool):
    from qtpy import QtWidgets

    boxes = tool._form.findChildren((QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox))
    out = []
    for box in boxes:
        step = box.singleStep()
        out.append((type(box).__name__, box.minimum(), box.maximum(), getattr(box, "decimals", lambda: 0)(), step, box.suffix()))
    return out


def test_every_numeric_field_has_the_qt_limits_decimals_step_and_suffix(qt):
    qt_boxes = _qt_spin_boxes(qt.tool)
    spec = build_spec()
    fields = [s for panel in spec["params"] for s in panel["sections"] if s.get("type") == "value" and s.get("kind") in ("int", "float")]
    assert len(fields) == len(qt_boxes) == 14
    # Qt lists them in the order of the spec; every one is a spin box in the native spec too.
    qt_sorted = {}
    for (kind, lo, hi, dec, step, suffix), f in zip(qt_boxes, fields):
        assert (kind == "QSpinBox") == (f["kind"] == "int"), f["attr"]
        assert f["minimum"] == lo and f["maximum"] == hi, f["attr"]
        assert f.get("suffix", "") == suffix, f["attr"]
        assert f.get("step", 1.0) == pytest.approx(step), (f["attr"], f.get("step"), step)
        if f["kind"] == "float":
            assert f["decimals"] == dec, f["attr"]
        assert f["style"] == "spin"
        qt_sorted[f["attr"]] = (lo, hi, step)
    assert set(qt_sorted) == {"aer", "nsig", "sigmin", "sigmax", "t", "eta", "rm", "vbar", "rho", "nq", "qmax", "ns", "rmax", "ntrials"}


def test_the_native_spec_is_the_qt_spec_plus_the_actions(qt):
    """Labels, descriptions and options come from ``hydropro.view.json`` itself: nothing is retyped."""
    import json

    qt_spec = json.loads((PLUGIN / "gui/hydropro.view.json").read_text())
    native_titles = [p["title"] for p in build_spec()["params"]]
    assert native_titles == [p["title"] for p in qt_spec["sections"] if p["title"] != "Results"]
    qt_fields = {s["attr"]: s for p in qt_spec["sections"] for s in p["sections"] if s.get("attr")}
    for panel in build_spec()["params"]:
        for s in panel["sections"]:
            if s.get("attr"):
                for key in ("label", "description", "options", "kind", "minimum", "maximum"):
                    assert s.get(key) == qt_fields[s["attr"]].get(key), (s["attr"], key)
    assert [o for p in build_spec()["params"] for s in p["sections"] if s.get("attr") == "indmode" for o in s["options"]] == ["1", "2", "4"]


def test_the_persisted_values_round_trip_through_the_qt_tool(qt, world):
    """What the native app remembers is what the Qt tool's QSettings holds, key for key and value for value."""
    model = native(world, struct_files=files(world, "148l"), indmode="2", aer=4.8, nsig=-1, t=25.0, nq=10, qmax=2.0, idif=False)
    saved = model.export_settings()
    # Qt writes what its model holds on Run; feed it the native state through the same file.
    qs = qt.tool._qsettings
    qs.setValue("hydro_exe", saved["exe_path"])
    for name, value in HydroProSettings(**{k: v for k, v in saved.items() if k not in ("exe_path",)}).to_dict().items():
        qs.setValue(f"hp.{name}", value)
    qs.sync()
    qt.tool._load_persisted()
    qm = qt.tool._model
    assert qm.exe_path == saved["exe_path"] and qm.to_settings() == model.to_settings()
    # And the other way: Qt's saved file restores the native model.
    qt.tool._save_persisted()
    fresh = HydroProModel()
    fresh.restore_settings({"exe_path": qs.value("hydro_exe"), **{n: qs.value(f"hp.{n}") for n in HydroProSettings().to_dict()}})
    assert fresh.to_settings() == model.to_settings() and fresh.exe_path == model.exe_path
    assert "Library/Preferences" not in qs.fileName()


def test_invalid_stored_values_are_ignored_field_by_field():
    model = HydroProModel()
    model.restore_settings({"exe_path": 5, "aer": "abc", "nsig": "9", "eta": None, "indmode": "4", "idif": "0", "bogus": 1})
    assert model.aer == 2.9 and model.nsig == 9 and model.eta == 0.01 and model.indmode == "4" and model.idif is False
    assert model.exe_path == ""


def test_the_result_cell_format_is_the_qt_one():
    assert format_diffusion(1.047e-06) == "1.047e-06" and format_diffusion(4.0) == "4.000e+00" and format_diffusion(None) == "N/A"


# -- drawing --------------------------------------------------------------------------------------------------------- #


def populated_app(world):
    app = HydroProApp(native(world, struct_files=files(world, "148l", "small", "plain", "garbled", "silent")))
    app.model.run()
    drain(app)
    return app


@pytest.mark.parametrize("size", [BIG, SMALL, (500, 500)])
def test_the_window_draws_empty_and_populated_without_clipping_or_overlap(world, size):
    for app in (make_app(), populated_app(world)):
        painter = draw_clip(app, size, 4)
        for text in ("Executable", "Structures", "INDMODE", "AER", "NSIG", "SIGMIN", "SIGMAX", "T", "ETA", "RM", "VBAR", "RHO",
                     "NQ", "QMAX", "NS", "RMAX", "NTRIALS", "Full diffusion tensor", "Select files…", "Executable…", "Download page",
                     "Run", "Save CSV", "Clear", "Status", "Clear log", "Save Log…", "Cancel", "Help", "Guide"):
            if size[0] >= 800:
                assert text in painter.strings, text
        if size[0] >= 800:
            log = [tuple(app.form.rects["output_log"])]  # the log editor draws its text in pieces
            assert layout_problems(painter, size, ignore=log) == [], layout_problems(painter, size, ignore=log)[:5]
            assert clipped_texts(painter, ignore=log) == []


def test_the_populated_table_shows_what_the_qt_table_showed(world):
    app = populated_app(world)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, *BIG)
    shown = painter.strings
    for cell in ("1.047e-06", "2.500e-07", "4.000e+00", "N/A"):
        assert cell in shown
    assert "Diffusion coefficient (cm²/s)" in shown and "File" in shown


def test_idle_controls_are_greyed_not_misleading(world):
    model = HydroProModel()
    assert model.enabled("run") and not model.enabled("save_csv") and not model.enabled("cancel")
    assert not model.enabled("clear_log") and not model.enabled("save_log")


def test_the_native_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    assert qt_free("hydropro")["ok"] is True
