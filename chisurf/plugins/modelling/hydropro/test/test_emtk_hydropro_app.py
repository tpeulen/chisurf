"""The native HydroPro on a fake HYDRO program whose answers are planted.

Hermetic (``conftest.py``): HOME, settings and MMFDB are temporary; the HYDRO program is ``data/fake_hydro.sh``,
which replies with the reports in ``data/recorded/`` and computes nothing, so the diffusion coefficient of every
structure is known in advance (``support.EXPECTED``). What is checked is everything around ``core.run_hydro``: the
table cells, the status, the output log, the CSV, the ``hydropro.dat`` written for each parameter set (read back by
its ``!KEY`` tags, against the HYDROPRO 10 manual's rules), the spin fields, the persisted values. A module guard
fails the run when the owner's real HydroPRO plist or ``~/.chisurf`` changed.
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
from .support import BIG, EXPECTED, SMALL, drain, make_world

PLUGIN = Path(__file__).resolve().parent.parent


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


def cells(model):
    return [[r["file"], r["d"]] for r in model.result_rows()]


def planted_cells(world, *stems):
    """The table the fake program's planted answers give: one row per structure, ``N/A`` where it reports none."""
    return [[str(world["files"][s]), format_diffusion(EXPECTED[s])] for s in stems]


def job_input(home, name="hydropro.dat"):
    return (home / ".hydropp_gui/job_001" / name).read_text()


def dat_values(text):
    """The ``hydropro.dat`` lines keyed by the tag after ``!`` (``NSIG=-1 ...`` and ``NQ: ...`` give ``NSIG``, ``NQ``)."""
    out = {}
    for line in text.splitlines():
        if "!" not in line:
            continue
        value, comment = line.split("!", 1)
        tag = comment.strip().split()[0].split("=")[0].split(":")[0]
        out[tag] = value.strip().rstrip(",")
    return out


# -- the numbers of a run -------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "stems", [("148l",), ("148l", "small", "plain", "garbled", "silent"), ("small", "148l")]
)
def test_the_table_status_log_and_csv_carry_the_planted_answers(world, stems, tmp_path):
    model = native(world, struct_files=files(world, *stems))
    model.run()
    drain(model)
    assert model.status == f"Finished: {len(stems)} file(s)."
    assert cells(model) == planted_cells(world, *stems)
    log = model.log_text
    assert log.startswith(f"Executable: {world['exe']}")
    for index, stem in enumerate(stems, start=1):
        assert f"=== Job {index}/{len(stems)}: {world['files'][stem]} ===" in log
    for stem in stems:
        if EXPECTED[stem] is not None:
            assert f"Result: diffusion coefficient = {EXPECTED[stem]:.3e} cm^2/s" in log
    mine = tmp_path / "mine.csv"
    assert model.write_csv(mine)
    rows = [
        f"{world['files'][s]},{format_diffusion(EXPECTED[s]) if EXPECTED[s] is not None else ''}"
        for s in stems
    ]
    assert mine.read_text(encoding="utf-8") == "\n".join(
        ["File,DiffusionCoefficient(cm^2/s)", *rows, ""]
    )
    assert model.notices[-1] == ("Saved", f"Results saved to {mine}")


def test_the_hydropp_flavour_writes_its_input_and_reads_the_planted_answers(world):
    model = native(world, exe=world["hpp"], struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert cells(model) == planted_cells(world, "148l", "small")
    assert [c for _f, c in cells(model)] == ["1.047e-06", "2.500e-07"]
    lines = [line.strip() for line in job_input(world["home"], "hydro_input.dat").splitlines()]
    settings = model.to_settings()
    assert str(world["files"]["148l"]) in lines
    for value in (settings.t, settings.rm, settings.vbar, settings.rho):
        assert str(value) in lines
    assert lines[-1] == "*"


#: Parameter sets that cover every INDMODE, automatic NSIG, Q/S curves with NTRIALS, and a custom sigma range.
PARAMETER_SETS = [
    {},
    {"aer": 4.8, "indmode": "2", "nsig": -1},
    {"aer": 6.1, "eta": 0.0089, "indmode": "4", "rho": 1.002, "rm": 14300.0, "t": 25.0, "vbar": 0.72},
    {"idif": False, "nq": 20, "ns": 30, "ntrials": 1000, "qmax": 35000000.0, "rmax": 1.2e-06},
    {"nsig": 8, "sigmax": 3.0, "sigmin": 0.5},
]


@pytest.mark.parametrize("fields", PARAMETER_SETS)
def test_every_parameter_set_writes_its_values_into_the_input_file(world, fields):
    model = native(world, struct_files=files(world, "148l"), **fields)
    model.run()
    drain(model)
    expected = HydroProSettings.from_dict(
        {**HydroProSettings().to_dict(), **fields, "idif": int(fields.get("idif", True))}
    )
    assert model.to_settings() == expected
    dat = dat_values(job_input(world["home"]))
    assert dat["TITLE"] == dat["FILENAME"] == "148l" and dat["INPUT"] == "148l.pdb"
    assert int(dat["INDMODE"]) == expected.indmode
    for tag, name in (("AER", "aer"), ("T", "t"), ("ETA", "eta"), ("RM", "rm"), ("VBAR", "vbar"), ("RHO", "rho")):
        assert float(dat[tag]) == pytest.approx(getattr(expected, name)), tag
    # HYDROPRO 10 manual: NSIG only in the shell modes; SIGMIN/SIGMAX only with an explicit NSIG.
    shell = expected.indmode in (1, 2)
    assert ("NSIG" in dat) == shell
    assert ("SIGMIN" in dat) == ("SIGMAX" in dat) == (shell and expected.nsig != -1)
    if shell:
        assert int(dat["NSIG"]) == expected.nsig
    if "SIGMIN" in dat:
        assert (float(dat["SIGMIN"]), float(dat["SIGMAX"])) == (expected.sigmin, expected.sigmax)
    # QMAX only when NQ > 0, RMAX only when NS > 0.
    assert (int(dat["NQ"]), int(dat["NS"])) == (expected.nq, expected.ns)
    assert ("QMAX" in dat) == (expected.nq > 0) and ("RMAX" in dat) == (expected.ns > 0)
    if expected.nq > 0:
        assert float(dat["QMAX"]) == expected.qmax and float(dat["RMAX"]) == expected.rmax
    assert int(dat["NTRIALS"]) == expected.ntrials and int(dat["IDIF"]) == expected.idif
    assert cells(model) == planted_cells(world, "148l")


def test_a_failing_run_reports_the_error(world):
    model = native(world, exe=world["noexec"], struct_files=files(world, "148l"))
    model.run()
    drain(model)
    assert model.status.startswith("Error: ") and "Permission denied" in model.status
    assert str(world["noexec"]) in model.status
    assert model.log_text.endswith(f"ERROR: {model.status[len('Error: '):]}")
    assert model.output_status == "Failed."
    assert model.results == []
    assert model.enabled("save_csv") is False


def test_the_output_pane_texts(world):
    model = native(world, struct_files=files(world, "148l", "small"))
    model.run()
    drain(model)
    assert model.output_status == "Finished."
    assert model.done == model.total == 2
    assert model.progress_text() == "100%"
    assert model.log_lines[0] == f"Executable: {world['exe']}"


def test_the_warnings(world):
    model = native(world)
    model.run()
    assert list(model.notices[-1]) == ["No files", "Please select one or more files first."]
    # Invalid settings (NSIG 2 in a shell mode).
    model = native(world, struct_files=files(world, "148l"), nsig=2)
    model.run()
    assert list(model.notices[-1]) == [
        "Invalid settings",
        "NSIG must be > 2 or -1 (automatic) in shell modes",
    ]
    assert model.running is False
    # QMAX / RMAX rules.
    for fields, text in (
        ({"nq": 5, "qmax": 0.0}, "QMAX must be > 0 when NQ > 0"),
        ({"ns": 5, "rmax": 0.0}, "RMAX must be > 0 when NS > 0"),
    ):
        model = native(world, struct_files=files(world, "148l"), **fields)
        model.run()
        assert list(model.notices[-1]) == ["Invalid settings", text]


def test_a_missing_executable_prompts_and_a_picked_one_runs(world):
    """Without an executable a prompt opens; closed without a choice -> 'Executable required'; with one -> the run goes on."""
    model = native(world, exe="", struct_files=files(world, "148l"))
    model.exe_path = ""
    model.run()
    assert model.exe_prompt and not model.running
    model.close_exe_prompt()
    assert list(model.notices[-1]) == [
        "Executable required",
        "Configure the HYDRO executable before running.",
    ]
    assert model.running is False
    # A prompt that picked an executable: the run continues with it and the field now holds it.
    model.run()
    model.prompt_exe_chosen(world["exe"])
    model.close_exe_prompt()
    drain(model)
    assert model.exe_path == str(world["exe"])
    assert model.result_rows()[0]["d"] == format_diffusion(EXPECTED["148l"]) == "1.047e-06"


def test_clear_empties_the_files_status_and_results(world):
    model = native(world, struct_files=files(world, "148l"))
    model.run()
    drain(model)
    model.clear()
    assert (model.struct_files, model.status, model.results, model.result_rows()) == (
        "",
        "",
        [],
        [],
    )
    assert not model.enabled("save_csv")


# -- the form -------------------------------------------------------------------------------------------------------- #


def test_defaults_are_the_manuals_defaults():
    """The model starts at :class:`HydroProSettings` (the HYDROPRO 10 manual's defaults), no files, no executable."""
    model = HydroProModel()
    assert model.to_settings() == HydroProSettings()
    assert (model.indmode, model.idif) == ("1", True)
    assert (model.exe_path, model.struct_files, model.status) == ("", "", "")


#: The numeric fields of ``hydropro.view.json``, in spec order; the integer ones are counts.
NUMERIC = ["aer", "nsig", "sigmin", "sigmax", "t", "eta", "rm", "vbar", "rho", "nq", "qmax", "ns", "rmax", "ntrials"]


def test_every_numeric_field_is_a_spin_field_with_the_specs_limits_and_step():
    view = json.loads((PLUGIN / "gui/hydropro.view.json").read_text())
    declared = {s["attr"]: s for p in view["sections"] for s in p["sections"] if s.get("attr")}
    fields = [
        s
        for panel in build_spec()["params"]
        for s in panel["sections"]
        if s.get("type") == "value" and s.get("kind") in ("int", "float")
    ]
    assert [f["attr"] for f in fields] == NUMERIC
    for f in fields:
        source = declared[f["attr"]]
        assert f["style"] == "spin", f["attr"]
        assert (f["kind"] == "int") == (f["attr"] in {"nsig", "nq", "ns", "ntrials"}), f["attr"]
        assert (f["minimum"], f["maximum"]) == (source["minimum"], source["maximum"]), f["attr"]
        assert f.get("suffix", "") == source.get("suffix", ""), f["attr"]
        if "step" in source:
            assert f["step"] == pytest.approx(source["step"]), f["attr"]
        if f["kind"] == "float" and "decimals" in source:
            assert f["decimals"] == source["decimals"], f["attr"]


def test_the_native_spec_is_the_view_spec_plus_the_actions():
    """Labels, descriptions and options come from ``hydropro.view.json`` itself: nothing is retyped."""
    view = json.loads((PLUGIN / "gui/hydropro.view.json").read_text())
    native_titles = [p["title"] for p in build_spec()["params"]]
    assert native_titles == [p["title"] for p in view["sections"] if p["title"] != "Results"]
    declared = {s["attr"]: s for p in view["sections"] for s in p["sections"] if s.get("attr")}
    for panel in build_spec()["params"]:
        for s in panel["sections"]:
            if s.get("attr"):
                for key in ("label", "description", "options", "kind", "minimum", "maximum"):
                    assert s.get(key) == declared[s["attr"]].get(key), (s["attr"], key)
    assert [
        o
        for p in build_spec()["params"]
        for s in p["sections"]
        if s.get("attr") == "indmode"
        for o in s["options"]
    ] == ["1", "2", "4"]


def test_the_persisted_values_round_trip(world):
    """What the app remembers is the executable and every parameter, and restoring it gives the same model."""
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
    saved = json.loads(json.dumps(model.export_settings()))
    assert set(saved) == {"exe_path", *HydroProSettings().to_dict()}
    assert saved["exe_path"] == str(world["exe"]) and saved["indmode"] == "2"
    assert {k: v for k, v in saved.items() if k not in ("exe_path", "indmode")} == {
        k: v for k, v in model.to_settings().to_dict().items() if k != "indmode"
    }
    assert "struct_files" not in saved  # the file list is not remembered
    fresh = HydroProModel()
    fresh.restore_settings(saved)
    assert fresh.to_settings() == model.to_settings() and fresh.exe_path == model.exe_path
    assert fresh.indmode == "2" and fresh.to_settings().idif == 0


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


def test_the_result_cell_format():
    assert (
        format_diffusion(1.047e-06) == "1.047e-06"
        and format_diffusion(4.0) == "4.000e+00"
        and format_diffusion(None) == "N/A"
    )


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


def test_the_populated_table_shows_every_planted_answer(world):
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
