"""Data Selection's assignment table: what the workflow works on, by role, made from the setup.

Real paths: workspace datasets (a group and single files) dragged onto rows, the setup changing
under the rows, the dye selector, Simple and Advanced, the warning without calibration files,
and the hand-over of IRF and buffer files to Burst MLE.
"""

from __future__ import annotations

import copy
import shutil
import time
from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_analysis import demo, samples
from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import (
    BurstDataSelectionApp,
    BurstDataSelectionModel,
)

SIZE = (900, 600)


@pytest.fixture(autouse=True)
def _packaged_dye_database(monkeypatch):
    """The dye database as ChiSurf ships it: a test before this one may have configured an empty
    MMFDB, which the database module would read instead (and cache)."""
    from chisurf.core.fluorescence import dyes

    monkeypatch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    yield
    monkeypatch.undo()
    try:
        dyes.reference_dyes(refresh=True)
    except Exception:  # noqa: BLE001 - the next user reloads it
        dyes._CACHE = None


@pytest.fixture(scope="module")
def demo_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("selection_demo")
    paths = demo.make_demo(folder)
    for n in (2, 3):
        shutil.copy(paths["measurement"], folder / f"sample_dsDNA_{n}.ptu")
    paths["red"] = demo.make_red_reference(folder)
    return paths


def _draw(app, frames=2):
    from emtk.testing import PixelPainter

    painter = None
    for _ in range(frames):
        painter = PixelPainter(*SIZE)
        app.draw(painter, 0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
    return painter


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    _draw(app, 1)
    while time.monotonic() < end:
        while app.job.busy and time.monotonic() < end:
            time.sleep(0.1)
        _draw(app, 1)
        if not app.job.busy:
            return


def _app(setup, **kwargs):
    from chisurf.emtk.i18n import install

    install()
    model = BurstDataSelectionModel(auto_import=False)
    holder = {"setup": setup}
    app = BurstDataSelectionApp(model, setup_provider=lambda: holder["setup"], **kwargs)
    return app, model, holder


def _row_point(app, key):
    control = app.form.tables["assignment_rows"].control
    keys = [control.key_of(i) for i in control.order()]
    position = keys.index(key)
    bx, by, _bw, _bh = control._body_box
    top = by if control._rows_top is None else control._rows_top
    return bx + 40.0, top + (position - control.bar.top + 0.5) * control._row_h


def _workspace(demo_files):
    """The session as a user has it: the three sample files dropped together (one group) and the
    calibration files one by one."""
    from chisurf.core.plugin.workspace_input import _api, register_result

    folder = demo_files["measurement"].parent
    group = [demo_files["measurement"], folder / "sample_dsDNA_2.ptu", folder / "sample_dsDNA_3.ptu"]
    start = len(_api().list_datasets())
    for path in group:
        register_result(path, kind="photons", name=path.stem)
    _api().group_datasets(list(range(start, start + 3)), "dsDNA sample")
    for key in ("buffer", "irf", "reference", "red"):
        register_result(demo_files[key], kind="photons", name=demo_files[key].stem)
    return group


def _drag(app, name, row, drop=True):
    record = next(r for r in app.input.workspace_input_rows() if r["name"] == name)
    _draw(app, 1)
    x, y = _row_point(app, f"row:{row}")
    app.input.workspace_input_drag(record, x, y, False)
    assert app.drop_target == f"row:{row}"  # the row it would land on is shown
    if drop:
        app.input.workspace_input_drag(record, x, y, True)
        assert app.drop_target is None


def test_rows_are_made_from_the_setup_and_follow_it(demo_files):
    app, model, holder = _app({})
    _draw(app)
    assert [r["row"] for r in app.assignment_rows() if r["parent"] == ""] == ["measurement", "buffer"]
    holder["setup"] = copy.deepcopy(demo.SETUP_PIE)
    model.add_paths([demo_files["red"]], "reference:R")
    model.add_paths([demo_files["irf"]])  # guessed: an IRF, the first colour
    roles = [r["row"] for r in app.assignment_rows() if r["parent"] == ""]
    assert roles == ["measurement", "buffer", "irf:G", "irf:R", "reference:G", "reference:R"]
    assert model.row_of(demo_files["irf"]) == "irf:G"
    # the red colour goes away: its file is shown unassigned, not lost; it comes back with it
    holder["setup"] = copy.deepcopy(demo.SETUP)
    assert model.row_of(demo_files["red"]) == "unassigned"
    assert "unassigned" in [r["row"] for r in app.assignment_rows() if r["parent"] == ""]
    assert model.assignments[str(demo_files["red"])] == "reference:R"
    holder["setup"] = copy.deepcopy(demo.SETUP_PIE)
    assert model.row_of(demo_files["red"]) == "reference:R"


def test_workspace_data_dropped_on_rows_with_a_group_kept_as_one(demo_files):
    app, model, _holder = _app(copy.deepcopy(demo.SETUP_PIE))
    _draw(app)
    group = _workspace(demo_files)
    _drag(app, "dsDNA sample", "measurement")
    _drag(app, "buffer", "buffer")
    _drag(app, "water_irf", "irf:G")
    _drag(app, "Rh110_ref", "reference:G")
    _drag(app, "Alexa647_ref", "reference:R")
    assert [Path(p) for p in model.measurement_paths()] == [p.resolve() for p in group]
    assert model.row_of(demo_files["buffer"]) == "buffer"
    assert model.row_of(demo_files["red"]) == "reference:R"
    rows = app.assignment_rows()
    entries = [r for r in rows if r.get("group")]
    assert len(entries) == 1 and entries[0]["files"] == "3" and "dsDNA sample" in entries[0]["name"]
    assert entries[0]["key"] not in app.expanded_rows  # the group is folded
    assert "row:measurement" in app.expanded_rows
    # the workspace remembers what each dataset is here
    from chisurf.core.plugin.workspace_input import _api

    tagged = {
        m.get("name"): (m.get("tags") or {}).get("sample")
        for d in _api().list_datasets()
        for m in (d.get("members") or [d])
    }
    assert tagged["buffer"] == "buffer" and tagged["Alexa647_ref"] == "reference:R"
    # a dataset dragged onto another row moves there
    _drag(app, "water_irf", "buffer")
    assert model.row_of(demo_files["irf"]) == "buffer"
    # Remove on the group takes all of its files out
    app.remove_entry(entries[0])
    assert model.measurement_paths() == []


def test_the_assignment_round_trips_through_the_settings(demo_files):
    app, model, _ = _app(copy.deepcopy(demo.SETUP_PIE))
    model.add_paths([demo_files["measurement"], demo_files["buffer"]])
    model.add_paths([demo_files["red"]], "reference:R")
    model.set_group([demo_files["measurement"]], "g1", "dsDNA sample")
    app.set_dye("R", dye="Cy5", temperature_c=21.0)
    state = app.export_settings()
    other, model2, _ = _app(copy.deepcopy(demo.SETUP_PIE))
    other.restore_settings(state)
    assert model2.assignments == model.assignments
    assert model2.groups == {"g1": "dsDNA sample"}
    assert model2.group_of == {str(demo_files["measurement"]): "g1"}
    assert model2.dyes["R"]["dye"] == "Cy5" and model2.dyes["R"]["how"] == "user"


def test_the_dye_selector_lists_the_database_and_a_users_choice_is_kept(demo_files):
    from chisurf.core.fluorescence.dyes import dye_names

    app, model, _ = _app(copy.deepcopy(demo.SETUP))
    column = next(c for c in app.spec["sections"][0]["options"]["columns"] if c["key"] == "dye")
    assert [c["value"] for c in column["choices"]] == list(dye_names()) + [samples.CUSTOM_DYE]
    assert {c["value"]: c["label"] for c in column["choices"]}["Rhodamine 110"] == "Rh110"
    model.add_paths([demo_files["reference"]])
    row = next(r for r in app.assignment_rows() if r["key"] == "row:reference:G")
    assert row["dye"] == "Rhodamine 110" and model.dyes["G"]["how"] == "file name"
    assert app.cell_editable(row, "dye") and not app.cell_editable(row, "name")
    app.cell_edited(row, "dye", "Fluorescein")
    model.add_paths([demo_files["reference"].with_name("Rh110_ref.ptu")])  # nothing re-infers it
    assert app.reference_dyes()["G"]["dye"] == "Fluorescein"
    assert app.reference_dyes()["G"]["how"] == "user"


def test_the_role_table_shows_the_setup_quality_in_both_modes_and_g_is_applied(demo_files):
    applied = {}
    setup = copy.deepcopy(demo.SETUP)

    def apply(values):
        applied.update(values)
        for det, value in values.items():
            setup["detectors"][det]["g_factor"] = value

    app, model, _ = _app(setup, on_apply_g=apply)
    app.set_advanced(False)
    keys = [c["key"] for c in app.spec["sections"][0]["options"]["columns"]]
    assert keys == ["name", "files", "dye", "g", "veff", "taud", "w0", "s", "cpm", "bg", "fwhm", "info"]
    assert not app.docks.is_shown("calibration")
    model.add_paths([demo_files["reference"], demo_files["buffer"], demo_files["irf"], demo_files["measurement"]])
    _settle(app)
    assert applied["G|G"] == pytest.approx(demo.TRUTH["g_factor"], rel=0.02)
    rows = {r["key"]: r for r in app.assignment_rows()}
    ref = rows["row:reference:G"]
    assert ref["g"] == pytest.approx(demo.TRUTH["g_factor"], rel=0.02)
    assert ref["veff"] > 0 and ref["taud"] > 0 and ref["w0"] > 0 and ref["s"] > 0 and ref["cpm"] > 0
    assert ref["info"] == "measured"
    assert rows["row:buffer"]["bg"] == pytest.approx(sum(demo.TRUTH["background_khz"]), rel=0.03)
    fwhm = 2.3548 * demo.TRUTH["prompt_sigma_ns"] * 1e3
    assert rows["row:irf:G"]["fwhm"] == pytest.approx(fwhm, rel=0.15)
    assert rows["row:measurement"]["g"] is None  # a number only where it applies
    # a G edited by hand in the setup is kept: not written over, said so
    setup["detectors"]["G|G"]["g_factor"] = 1.05
    applied.clear()
    app.set_dye("G", temperature_c=24.0)  # recalibrates
    _settle(app)
    assert applied == {} and setup["detectors"]["G|G"]["g_factor"] == 1.05
    assert app.hand_edited_g() == ["G|G"]
    assert next(r for r in app.assignment_rows() if r["key"] == "row:reference:G")["info"] == "hand-edited"
    app.set_advanced(True)
    keys = [c["key"] for c in app.spec["sections"][0]["options"]["columns"]]
    assert "size" in keys and "status" in keys
    assert app.docks.is_shown("calibration")


def test_without_calibration_files_the_workflow_goes_on_with_a_warning(demo_files):
    proceeded = []
    app, model, _ = _app(copy.deepcopy(demo.SETUP), on_proceed=lambda: proceeded.append(1))
    model.propose = False  # a session without calibration files (the demo has them beside)
    model.add_paths([demo_files["measurement"]])
    warning = app.fallback_warning()
    assert warning == "Estimated (no buffer, IRF, reference dye)"
    assert "photons outside the bursts" in app.fallback_detail()
    from emtk.testing import Driver

    driver = Driver(app, SIZE)
    driver.frame(3)
    drawn = " ".join(entry[5] for entry in driver.painter.texts)
    assert warning in drawn
    rows = {r["row"]: r for r in app.assignment_rows() if r["parent"] == ""}
    assert rows["buffer"]["info"] == "estimated" and "photons outside" in rows["buffer"]["tip"]
    assert "non-burst" in rows["irf:G"]["tip"]
    app.proceed()
    assert proceeded == [1] and warning in app.message
    app.proceed()
    assert proceeded == [1, 1]


def test_irf_and_buffer_files_reach_burst_mle(demo_files):
    """The workflow context hands Data Selection's files to Burst MLE per detector; Auto takes
    the IRF from the reference dye first (the owner's order: measured like the sample), the IRF
    measurement stays selectable, and the buffer gives the buffer rate."""
    from chisurf.plugins.burst.burst_analysis.workflow_context import BurstWorkflowContext
    from chisurf.plugins.burst.burst_mle_analysis import engine
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    context = BurstWorkflowContext(channel_settings=copy.deepcopy(demo.SETUP))
    context.samples = {
        str(demo_files["measurement"]): "measurement",
        str(demo_files["buffer"]): "buffer",
        str(demo_files["irf"]): "irf",  # a guess without colour: the setup's first
        str(demo_files["reference"]): "reference",
    }
    references = context.references()
    assert references["irf"] == {"G|G": [str(demo_files["irf"])]}
    assert references["buffer"] == [str(demo_files["buffer"])]
    assert "background" not in context.estimated()

    model = MleViewModel(engine.MleSession())
    model.set_setup(copy.deepcopy(demo.SETUP))
    model.prepare_patterns([str(demo_files["measurement"])], references)
    session = model.session
    assert sorted(session.irf_files["G|G"]) == sorted(
        [Path(demo_files["irf"]), Path(demo_files["reference"])]
    )
    assert session.bg_files["G|G"] == [Path(demo_files["buffer"])]
    assert "Rh110_ref.ptu" in session.irf_source["G|G"]
    session.choose_irf("G|G", "measurement")
    assert session.irf_source["G|G"].startswith("scatter water_irf.ptu")
    assert model.buffer_rate("G|G") == pytest.approx(sum(demo.TRUTH["background_khz"]), rel=0.03)
    assert "B_G|G" in model.irf_source_text()

    # only measurements: the fallbacks are named in the provenance
    bare = BurstWorkflowContext(channel_settings=copy.deepcopy(demo.SETUP))
    bare.samples = {str(demo_files["measurement"]): "measurement"}
    estimated = bare.estimated()
    assert "photons outside the bursts" in estimated["background"]
    assert "blind estimate" in estimated["irf:G"]
    assert "G from the setup" in estimated["g_factor:G"]
    assert bare.to_payload()["estimated"] == estimated


def test_the_hub_hands_measurements_on_and_keeps_the_calibration(demo_files, tmp_path, monkeypatch):
    """In Burst Analysis: only the measurements go to Burst Selection; the volume goes into the
    setup and the context; Apply G writes the setup's G-Factor column."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    try:
        hub.set_advanced(True)
        hub.setup_model.data = copy.deepcopy(demo.SETUP)
        hub.context.channel_settings = hub.setup_model.get_settings()
        data = hub.ensure_child("data")
        data.source.auto_import = False
        data.source.add_paths(
            [demo_files["measurement"], demo_files["buffer"], demo_files["irf"], demo_files["reference"]]
        )
        assert hub.context.raw_files == [Path(demo_files["measurement"]).resolve()]
        assert hub.context.samples[str(Path(demo_files["irf"]).resolve())] == "irf"
        end = time.monotonic() + 120
        data.poll_calibration()
        while time.monotonic() < end and (data.job.busy or not hub.context.calibration):
            time.sleep(0.1)
            data.poll_calibration()
        volume = hub.context.confocal_volume("G")
        assert volume["veff_fl"] > 0
        assert hub.setup_model.data["confocal_volume"]["G"]["veff_fl"] == pytest.approx(volume["veff_fl"])
        g = hub.context.calibration["colours"]["G"]["g_factor"]["G|G"]["g"]
        # written into the setup as computed, in Advanced too
        assert hub.setup_model.data["detectors"]["G|G"]["g_factor"] == pytest.approx(g)
        assert hub.context.channel_settings["detectors"]["G|G"]["g_factor"] == pytest.approx(g)
        assert hub.context.references()["irf"]["G|G"] == [str(Path(demo_files["irf"]).resolve())]
        report = hub.context.calibration_report
        assert report["colours"]["G"]["g_applied"]["G|G"] == pytest.approx(g)
        assert hub.context.to_payload()["calibration_report"] == report
    finally:
        hub.close()


def test_the_calibration_report_is_complete_and_round_trips_through_the_container(demo_files, tmp_path):
    from chisurf.plugins.burst.burst_analysis.calibration_report import (
        SCHEMA,
        build_report,
        read_report,
        write_report,
    )
    from chisurf.plugins.burst.burst_analysis.workflow_context import BurstWorkflowContext

    rows = {
        str(demo_files["measurement"]): "measurement",
        str(demo_files["buffer"]): "buffer",
        str(demo_files["irf"]): "irf:G",
        str(demo_files["reference"]): "reference:G",
    }
    result = samples.calibrate(rows, demo.SETUP)
    context = BurstWorkflowContext(channel_settings=copy.deepcopy(demo.SETUP), samples=dict(rows))
    report = build_report(result, rows, demo.SETUP, estimated=context.estimated(), applied_g={"G|G": 1.15})
    assert report["schema"] == SCHEMA
    roles = {f["role"]: f for f in report["files"]}
    assert set(roles) == {"measurement", "buffer", "irf:G", "reference:G"}
    import hashlib

    assert roles["buffer"]["sha256"] == hashlib.sha256(Path(demo_files["buffer"]).read_bytes()).hexdigest()
    green = report["colours"]["G"]
    assert green["dye"]["dye"] == "Rhodamine 110" and "Kapusta" in green["D_citation"]
    fit = green["volume_fit"]
    for key in ("N", "tau_d_ms", "s", "w0_um", "veff_fl"):
        assert fit[key] > 0 and fit[f"{key}_err"] >= 0
    assert fit["chi2r"] > 0 and green["g_factor"]["G|G"]["sem"] > 0
    assert report["buffer"]["rates"]["G|G"]["B_kHz"] > 0 and report["irf"]["G"]["fwhm_ps"] > 0
    assert report["estimated"] == {}
    container = write_report(demo_files["measurement"], report, tmp_path / "containers")
    write_report(demo_files["measurement"], report, tmp_path / "containers")  # replaced, not added
    assert read_report(container) == report
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(container) as m:
        names = [o.name for o in m._f.objects()]
    assert names.count("burst_calibration") == 1
