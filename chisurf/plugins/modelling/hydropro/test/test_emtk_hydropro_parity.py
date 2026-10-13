"""The native HydroPro against the Qt tool it replaced: the same recorded program output gives the same numbers.

The Qt side is ``qt_reference.json``: the retired ``HydroProTool``'s answers, recorded once per case from the live tool
(offscreen, hermetic, with the fake HYDRO program) and frozen; ``_recorded`` names the commit. Paths under the test
HOME are written ``<home>`` there. So this file imports no Qt.

Hermetic (``conftest.py``): HOME, settings and MMFDB are temporary; the HYDRO program is ``data/fake_hydro.sh``, which
replies with the recorded reports in ``data/recorded/`` and computes nothing. What is compared is everything around
``core.run_hydro``: the table cells, the status, the output log, the CSV, the input file written for each parameter
set, the spin-box limits and steps, the persisted values. A module guard fails the run when the owner's real HydroPRO
plist or ``~/.chisurf`` changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.modelling.hydropro.app import HydroProApp, build_spec, make_app
from chisurf.plugins.modelling.hydropro.core import HydroProSettings
from chisurf.plugins.modelling.hydropro.gui.model import HydroProModel, format_diffusion

from . import hermetic
from .support import BIG, EXPECTED, REPO, SMALL, drain, make_world

PLUGIN = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "okf/plugins/emtk-ports/hydropro"
#: The retired Qt ``HydroProTool``'s answers per case, recorded from the live tool and frozen.
QT = json.loads(Path(__file__).with_name("qt_reference.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def real_state_untouched():
    state = hermetic.RealState()
    yield
    assert state.changes() == []


@pytest.fixture
def world():
    return make_world(Path.home())


def native(world, **fields):
    model = HydroProModel()
    model.exe_path = str(fields.pop("exe", world["exe"]))
    for key, value in fields.items():
        setattr(model, key, value)
    return model


def files(world, *stems):
    return ", ".join(str(world["files"][s]) for s in stems)


def norm(world, value):
    """The record's spelling of a value: paths under the test HOME become ``<home>``."""
    home = str(world["home"])
    if isinstance(value, str):
        return value.replace(home, "<home>")
    if isinstance(value, (list, tuple)):
        return [norm(world, v) for v in value]
    if isinstance(value, dict):
        return {k: norm(world, v) for k, v in value.items()}
    return value


def cells(world, model):
    return norm(world, [[r["file"], r["d"]] for r in model.result_rows()])


def job_input(home, name="hydropro.dat"):
    return (home / ".hydropp_gui/job_001" / name).read_text()


# -- the numbers of a run -------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "stems", [("148l",), ("148l", "small", "plain", "garbled", "silent"), ("small", "148l")]
)
def test_the_table_status_and_csv_equal_the_qt_tool_for_the_same_recorded_output(
    world, stems, tmp_path
):
    qt = QT["table"][",".join(stems)]
    model = native(world, struct_files=files(world, *stems))
    model.run()
    drain(model)
    assert model.status == qt["status"] == f"Finished: {len(stems)} file(s)."
    assert cells(world, model) == qt["cells"]
    assert norm(world, model.log_text) == qt["log"]
    # The recorded values arrive as the parser reads them, formatted as the Qt table formats them.
    for stem, (_path, cell) in zip(stems, qt["cells"]):
        want = EXPECTED[stem]
        assert cell == (f"{want:.3e}" if want is not None else "N/A")
    # CSV: byte for byte what the Qt tool wrote.
    mine = tmp_path / "mine.csv"
    assert model.write_csv(mine)
    assert norm(world, mine.read_text(encoding="utf-8")) == qt["csv"]
    assert qt["saved_box"][1:] == ["Saved", "Results saved to <csv>"]
    assert model.notices[-1] == ("Saved", f"Results saved to {mine}")


def test_the_hydropp_flavour_equal_the_qt_tool(world):
    qt = QT["hydropp"]
    model = native(world, exe=world["hpp"], struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert cells(world, model) == qt["cells"]
    assert norm(world, job_input(world["home"], "hydro_input.dat")) == qt["dat"]
    assert [c for _f, c in qt["cells"]] == ["1.047e-06", "2.500e-07"]


@pytest.mark.parametrize("index", range(5))
def test_every_parameter_set_writes_the_input_file_the_qt_tool_wrote(world, index):
    qt = QT["parameter_sets"][index]
    model = native(world, struct_files=files(world, "148l"), **qt["fields"])
    model.run()
    drain(model)
    assert norm(world, job_input(world["home"])) == qt["dat"]
    assert cells(world, model) == qt["cells"]
    assert model.to_settings().to_dict() == qt["settings"]


def test_the_parameter_sets_cover_every_mode_and_option():
    """The record holds the five parameter sets the Qt tool was driven with (every INDMODE, Q/S curves, NSIG)."""
    fields = [case["fields"] for case in QT["parameter_sets"]]
    assert {f.get("indmode", "1") for f in fields} == {"1", "2", "4"}
    assert any(f.get("nq", -1) > 0 and f.get("ns", -1) > 0 for f in fields)
    assert any(f.get("nsig") == 8 for f in fields) and any(f.get("idif") is False for f in fields)


def test_a_failing_run_reports_the_same_error_as_the_qt_tool(world):
    qt = QT["failing"]
    assert qt["status"].startswith("Error: ") and "Permission denied" in qt["status"]
    model = native(world, exe=world["noexec"], struct_files=files(world, "148l"))
    model.run()
    drain(model)
    assert norm(world, model.status) == qt["status"]
    assert norm(world, model.log_text) == qt["log"]
    assert model.output_status == qt["output_status"] == "Failed."
    assert model.results == qt["results"] == []
    assert model.enabled("save_csv") is qt["save_enabled"] is False


def test_the_output_pane_texts_equal_the_qt_dialog(world):
    qt = QT["output_pane"]
    model = native(world, struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert model.output_status == qt["output_status"] == "Finished."
    assert model.done == qt["progress"] == qt["progress_maximum"] == model.total == 2
    assert model.progress_text() == qt["progress_text"] == "100%"
    assert norm(world, model.log_lines[0]) == qt["first_log_line"]


def test_the_warnings_equal_the_qt_tool(world):
    qt = QT["warnings"]
    model = native(world)
    model.run()
    assert list(model.notices[-1]) == qt["no_files"] == ["No files", "Please select one or more files first."]
    # Invalid settings (NSIG 2 in a shell mode).
    model = native(world, struct_files=files(world, "148l"), nsig=2)
    model.run()
    assert list(model.notices[-1]) == qt["nsig_2"]
    assert model.notices[-1][0] == "Invalid settings" and "NSIG must be > 2" in model.notices[-1][1]
    assert model.running is qt["nsig_2_running"] is False
    # QMAX / RMAX rules.
    for key, fields in (("qmax_rule", {"nq": 5, "qmax": 0.0}), ("rmax_rule", {"ns": 5, "rmax": 0.0})):
        model = native(world, struct_files=files(world, "148l"), **fields)
        model.run()
        assert list(model.notices[-1]) == qt[key]


def test_a_missing_executable_gives_the_qt_prompt_and_the_same_outcomes(world):
    """Qt: a modal DownloadInfoDialog; Close without a choice -> 'Executable required'; with one -> the run goes on."""
    qt = QT["missing_exe"]
    model = native(world, exe="", struct_files=files(world, "148l"))
    model.exe_path = ""
    model.run()
    assert model.exe_prompt and not model.running
    model.close_exe_prompt()
    assert list(model.notices[-1]) == qt["closed_box"] == [
        "Executable required",
        "Configure the HYDRO executable before running.",
    ]
    assert qt["closed_running"] is False
    # A prompt that picked an executable: the run continues with it and the field now holds it.
    model.run()
    model.prompt_exe_chosen(world["exe"])
    model.close_exe_prompt()
    drain(model)
    assert norm(world, model.exe_path) == qt["picked_exe_path"]
    assert model.result_rows()[0]["d"] == qt["picked_cell"] == "1.047e-06"


def test_clear_empties_what_the_qt_clear_empties(world):
    qt = QT["clear"]
    model = native(world, struct_files=files(world, "148l"))
    model.run()
    drain(model)
    model.clear()
    assert (model.struct_files, model.status, model.results, model.result_rows()) == (
        qt["struct_files"],
        qt["status"],
        qt["results"],
        [],
    ) == ("", "", [], [])
    assert qt["row_count"] == 0 and qt["save_enabled"] is False and not model.enabled("save_csv")


# -- the form -------------------------------------------------------------------------------------------------------- #


def test_defaults_equal_the_qt_models_defaults():
    model = HydroProModel()
    for name, value in QT["defaults"].items():
        assert getattr(model, name) == value, name


def test_every_numeric_field_has_the_qt_limits_decimals_step_and_suffix():
    qt_boxes = QT["spin_boxes"]
    spec = build_spec()
    fields = [
        s
        for panel in spec["params"]
        for s in panel["sections"]
        if s.get("type") == "value" and s.get("kind") in ("int", "float")
    ]
    assert len(fields) == len(qt_boxes) == 14
    # Qt listed them in the order of the spec; every one is a spin box in the native spec too.
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
    assert set(qt_sorted) == {
        "aer",
        "nsig",
        "sigmin",
        "sigmax",
        "t",
        "eta",
        "rm",
        "vbar",
        "rho",
        "nq",
        "qmax",
        "ns",
        "rmax",
        "ntrials",
    }


def test_the_native_spec_is_the_qt_spec_plus_the_actions():
    """Labels, descriptions and options come from ``hydropro.view.json`` itself: nothing is retyped."""
    qt_spec = json.loads((PLUGIN / "gui/hydropro.view.json").read_text())
    native_titles = [p["title"] for p in build_spec()["params"]]
    assert native_titles == [p["title"] for p in qt_spec["sections"] if p["title"] != "Results"]
    qt_fields = {s["attr"]: s for p in qt_spec["sections"] for s in p["sections"] if s.get("attr")}
    for panel in build_spec()["params"]:
        for s in panel["sections"]:
            if s.get("attr"):
                for key in ("label", "description", "options", "kind", "minimum", "maximum"):
                    assert s.get(key) == qt_fields[s["attr"]].get(key), (s["attr"], key)
    assert [
        o
        for p in build_spec()["params"]
        for s in p["sections"]
        if s.get("attr") == "indmode"
        for o in s["options"]
    ] == ["1", "2", "4"]


def test_the_persisted_values_round_trip_through_the_qt_tool(world):
    """What the native app remembers is what the Qt tool's QSettings held, key for key and value for value."""
    qt = QT["persisted"]
    model = native(
        world,
        struct_files=files(world, "148l"),
        indmode="2",
        aer=4.8,
        nsig=-1,
        t=25.0,
        nq=10,
        qmax=2.0,
        idif=False,
    )
    saved = model.export_settings()
    assert norm(world, saved) == qt["native_export"]
    # The Qt tool, fed this state through its QSettings, held the same parameters.
    assert norm(world, saved["exe_path"]) == qt["qt_loaded"]["exe_path"]
    assert model.to_settings().to_dict() == qt["qt_loaded"]["settings"]
    assert model.indmode == qt["qt_loaded"]["indmode"]
    assert set(qt["written"]) == {"hydro_exe", *(f"hp.{n}" for n in HydroProSettings().to_dict())}
    # And the other way: what the Qt tool's own save wrote restores the native model.
    stored = qt["qt_saved"]
    fresh = HydroProModel()
    fresh.restore_settings(
        {
            "exe_path": stored["hydro_exe"].replace("<home>", str(world["home"])),
            **{n: stored[f"hp.{n}"] for n in HydroProSettings().to_dict()},
        }
    )
    assert fresh.to_settings() == model.to_settings() and fresh.exe_path == model.exe_path


def test_invalid_stored_values_are_ignored_field_by_field():
    model = HydroProModel()
    model.restore_settings(
        {
            "exe_path": 5,
            "aer": "abc",
            "nsig": "9",
            "eta": None,
            "indmode": "4",
            "idif": "0",
            "bogus": 1,
        }
    )
    assert (
        model.aer == 2.9
        and model.nsig == 9
        and model.eta == 0.01
        and model.indmode == "4"
        and model.idif is False
    )
    assert model.exe_path == ""


def test_the_result_cell_format_is_the_qt_one():
    assert (
        format_diffusion(1.047e-06) == "1.047e-06"
        and format_diffusion(4.0) == "4.000e+00"
        and format_diffusion(None) == "N/A"
    )


def test_the_record_names_the_commit_it_was_taken_at():
    rec = QT["_recorded"]
    assert len(rec["source_commit"]) == 40 and "HydroProTool" in rec["from"]


# -- drawing --------------------------------------------------------------------------------------------------------- #


def populated_app(world):
    app = HydroProApp(
        native(world, struct_files=files(world, "148l", "small", "plain", "garbled", "silent"))
    )
    app.model.run()
    drain(app)
    return app


@pytest.mark.parametrize("size", [BIG, SMALL, (500, 500)])
def test_the_window_draws_empty_and_populated_without_clipping_or_overlap(world, size):
    for app in (make_app(), populated_app(world)):
        painter = draw_clip(app, size, 4)
        for text in (
            "Executable",
            "Structures",
            "INDMODE",
            "AER",
            "NSIG",
            "SIGMIN",
            "SIGMAX",
            "T",
            "ETA",
            "RM",
            "VBAR",
            "RHO",
            "NQ",
            "QMAX",
            "NS",
            "RMAX",
            "NTRIALS",
            "Full diffusion tensor",
            "Select files…",
            "Executable…",
            "Download page",
            "▶ Run",
            "Save CSV",
            "Clear",
            "Status",
            "Clear log",
            "Save Log…",
            "✕  Cancel",
            "Help",
            "Guide",
        ):
            if size[0] >= 800:
                assert text in painter.strings, text
        if size[0] >= 800:
            log = [tuple(app.form.rects["output_log"])]  # the log editor draws its text in pieces
            assert layout_problems(painter, size, ignore=log) == [], layout_problems(
                painter, size, ignore=log
            )[:5]
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
