"""The native pair selection window (fret_docking): parity with the Qt window and real-input tests of every control.

Hermetic: temporary settings and HOME, a real 8-frame trajectory of the hgbp1 test data, no network. Nothing here
calls a model method to "click": a pointer is pressed and released at the rectangle a control drew, text is typed,
the wheel is turned over a field, files are dropped through ``on_files_dropped``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.modelling.fret.core.pair_run import PairParams, run_pair_selection
from chisurf.plugins.modelling.fret.gui.pair_selection_app import PATH_ROWS, make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import CTRL_A, Ui

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
DATA = REPO / "test/data/atomic_coordinates/trajectory/hgbp1"
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    from chisurf.core.structure import trajectory_data as md

    folder = tmp_path_factory.mktemp("pair_inputs")
    full = md.load(str(DATA / "hgbp1_transition.dcd"), top=str(DATA / "topol.pdb"))
    full[:8].save_dcd(str(folder / "small.dcd"))
    shutil.copy(DATA / "topol.pdb", folder / "topol.pdb")
    shutil.copy(EXAMPLE / "hiv_rt.fps.json", folder / "hiv_rt.fps.json")
    (folder / "notes.txt").write_text("not a trajectory")
    (folder / "sub").mkdir()
    return folder


def ready(inputs, size=(1200, 800), **fields):
    app = make_app()
    s = app.session
    s.trajectory, s.topology = str(inputs / "small.dcd"), str(inputs / "topol.pdb")
    s.max_pairs = 5
    for k, v in fields.items():
        setattr(s, k, v)
    return Ui(app, size)


def run_and_wait(ui):
    ui.click("run")
    assert ui.app.session.running or ui.app.session.rows
    assert ui.app.session.wait(120)
    return ui.draw(3)


EXPECTED_ROWS = [
    (1, "A:THR92-A:GLY94", 1.53),
    (2, "A:TYR47-A:ASN50", 1.29),
    (3, "A:LEU40-A:LEU95", 1.22),
    (4, "A:VAL38-A:THR92", 1.17),
    (5, "A:LEU90-A:LEU116", 1.22),
]


# ---- numeric parity with the Qt window -------------------------------------------------------------------------


QT = json.loads((Path(__file__).parent / "qt_reference.json").read_text())


def test_the_run_equals_the_qt_windows(inputs):
    """The retired Qt window chose these five pairs, and its Export button wrote this text (recorded)."""
    ui = ready(inputs)
    run_and_wait(ui)
    rows = [(r["number"], r["pair"], round(r["rmsd"], 2)) for r in ui.app.session.rows]
    assert rows == [(n, p, v) for n, p, v in EXPECTED_ROWS]
    assert ui.app.session.result.export_text() == QT["export_text"]
    ui.app.close()


def test_the_default_fields_equal_the_qt_windows():
    """The Qt window started at ``PairParams()`` and its spin boxes had these ranges (recorded)."""
    for attr, (lo, hi) in QT["ranges"].items():
        spec = _field(make_app().spec, attr)
        assert spec["minimum"] == pytest.approx(lo), attr
        assert spec["maximum"] == pytest.approx(hi), attr


def _field(spec, attr):
    for s in spec["sections"]:
        if s.get("attr") == attr:
            return s
        found = _field(s, attr) if s.get("sections") else None
        if found:
            return found
    return None


# ---- the controls, by real input -------------------------------------------------------------------------------


def test_run_lists_the_pairs_draws_the_plot_and_export_writes_the_file(inputs, tmp_path):
    ui = ready(inputs)
    assert not ui.app.session.rows and ui.shown("No result yet")
    run_and_wait(ui)
    assert (
        ui.shown("5 pairs chosen.")
        and ui.shown("A:THR92-A:GLY94")
        and "decay_plot" in ui.app.item_rects
    )
    ui.click("export")
    assert ui.dialog_open and ui.shown("Export pair selection")
    target = tmp_path / "pairs.txt"
    ui.save_dialog_type_name(str(target))
    ui.press_text("Save")
    assert target.read_text().splitlines()[0] == "#\tPair_added\t<<RMSD>>/A"
    assert target.read_text().splitlines()[1] == "1\tA:THR92-A:GLY94\t1.53"
    assert len(target.read_text().splitlines()) == 6
    ui.app.close()


def test_export_is_unavailable_before_a_run_and_while_running(inputs):
    ui = ready(inputs)
    ui.click("export")
    assert not ui.dialog_open
    ui.click("run")
    assert ui.app.session.running
    ui.click("export")
    assert not ui.dialog_open
    ui.click("run")  # a second press while running starts nothing
    assert ui.app.session.wait(120) and len(ui.app.session.rows) == 5
    ui.app.close()


@pytest.mark.parametrize(
    "key,start,typed,lo,hi,step,kind",
    [
        ("stride", 1, "2", 1, 1000000, 1, int),
        ("max_pairs", 5, "3", 1, 999, 1, int),
        ("r0", 52.0, "40.5", 1.0, 200.0, 1.0, float),
        ("err", 0.06, "0.1", 0.0001, 1.0, 0.01, float),
        ("av_samples", 5000, "6000", 100, 1000000, 1, int),
        ("av_max_points", 20000, "30000", 1000, 500000, 1, int),
    ],
)
def test_number_field(inputs, key, start, typed, lo, hi, step, kind):
    """Typed value + Enter, text that is no number, both limits and both arrows (the Qt spin boxes' ranges)."""
    ui = ready(inputs, fps_json=str(inputs / "hiv_rt.fps.json"))
    s = ui.app.session
    assert getattr(s, key) == start
    ui.type_into(key, typed)
    assert getattr(s, key) == kind(typed)
    ui.type_into(key, "abc")
    assert getattr(s, key) == kind(typed)
    ui.type_into(key, str(hi * 10 + 1))
    assert getattr(s, key) == hi
    ui.type_into(key, str(lo - 5))
    assert getattr(s, key) == lo
    ui.arrow(key, -1)
    assert getattr(s, key) == lo
    ui.arrow(key, +1)
    assert getattr(s, key) == pytest.approx(lo + step)
    ui.arrow(key, -1)
    assert getattr(s, key) == pytest.approx(lo)
    ui.app.close()


@pytest.mark.parametrize(
    "key,typed",
    [
        ("stride", "7"),
        ("max_pairs", "7"),
        ("r0", "70"),
        ("err", "0.5"),
        ("av_samples", "7000"),
        ("av_max_points", "7000"),
    ],
)
def test_number_field_wheel_and_click_away(inputs, key, typed):
    """The wheel over a spin field steps it (up raises, down lowers, as the Qt boxes do); typing without Enter is
    committed when the pointer goes down elsewhere."""
    ui = ready(inputs, fps_json=str(inputs / "hiv_rt.fps.json"))
    s = ui.app.session
    ui.type_into(key, typed)
    mid = getattr(s, key)
    x, y, w, h = ui.app.item_rects[key]
    ui.app.pointer_move(x + w / 2, y + h / 2)
    ui.draw(2)
    ui.app.wheel(x + w / 2, y + h / 2, 1)
    ui.draw(1)
    up = getattr(s, key)
    assert up > mid
    ui.app.wheel(x + w / 2, y + h / 2, -1)
    ui.draw(1)
    ui.app.wheel(x + w / 2, y + h / 2, -1)
    ui.draw(1)
    assert getattr(s, key) < up
    ui.app.pointer_move(1, 1)
    ui.draw(1)
    fresh = ready(inputs, fps_json=str(inputs / "hiv_rt.fps.json"))
    f = fresh.app.session
    fresh.draw(1)
    fresh.click(key, fx=0.3)
    fresh.type_text(typed)
    assert getattr(f, key) != type(getattr(f, key))(typed)  # typed, not yet committed
    fresh.click("trajectory", fx=0.9)
    assert getattr(f, key) == type(getattr(f, key))(typed)
    ui.app.close()
    fresh.app.close()


@pytest.mark.parametrize(
    "key,start,typed",
    [
        ("chain", "A", "B"),
        ("residues", "35-50,85-95,115-120", "10-20"),
        ("rmsd_selection", "name CA", "name CB"),
    ],
)
def test_text_field(inputs, key, start, typed):
    ui = ready(inputs)
    s = ui.app.session
    assert getattr(s, key) == start
    ui.type_into(key, typed)
    assert getattr(s, key) == typed and ui.shown(typed)
    ui.draw(1)
    ui.click(key, fx=0.3)
    ui.app.key(0x41, "a", CTRL_A)
    ui.draw(1)
    ui.key(keys.KEY_BACKSPACE, "")
    ui.click("trajectory", fx=0.9)  # the commit is the pointer going down elsewhere
    assert getattr(s, key) == ""  # an empty value is allowed, as in the Qt box
    ui.app.close()


def test_the_attachment_atom_choice_opens_a_list_and_takes_the_pick(inputs):
    ui = ready(inputs)
    assert ui.app.session.atom == "CB"
    ui.click("atom")
    assert ui.shown("CA")
    ui.press_text("CA")
    assert ui.app.session.atom == "CA"
    run_and_wait(ui)
    assert len(ui.app.session.rows) == 5  # CA sites: a different run, the same shape
    ui.app.close()


def test_the_toggles_flip_on_a_click(inputs):
    ui = ready(inputs, fps_json=str(inputs / "hiv_rt.fps.json"))
    s = ui.app.session
    assert s.unique_only is True and s.use_av is True
    ui.click("unique_only", fx=0.05)
    assert s.unique_only is False
    ui.click("unique_only", fx=0.05)
    assert s.unique_only is True
    ui.click("use_av", fx=0.05)
    assert s.use_av is False
    ui.click("use_av", fx=0.05)
    assert s.use_av is True
    ui.app.close()


def test_controls_that_do_nothing_are_greyed(inputs):
    """No FPS JSON: the AV controls are idle. An FPS JSON: the residue fields are. While running: all of them."""
    ui = ready(inputs)
    s = ui.app.session
    assert (
        not s.enabled("use_av")
        and not s.enabled("av_samples")
        and s.enabled("chain")
        and s.enabled("residues")
    )
    before = s.use_av
    ui.click("use_av", fx=0.05)
    assert s.use_av == before  # a press on a greyed toggle changes nothing
    ui.click("av_samples", fx=0.3)
    assert not ui.app.io.want_capture_keyboard  # a greyed field takes no keyboard
    assert s.av_samples == 5000
    s.fps_json = str(inputs / "hiv_rt.fps.json")
    assert (
        s.enabled("use_av")
        and s.enabled("av_samples")
        and not s.enabled("chain")
        and not s.enabled("atom")
    )
    s.use_av = False
    assert not s.enabled("av_samples")
    s.running = True
    assert not any(
        s.enabled(k) for k in ("stride", "max_pairs", "r0", "chain", "residues", "use_av")
    )
    s.running = False
    ui.app.close()


@pytest.mark.parametrize("row", [r[0] for r in PATH_ROWS])
def test_browse_rows_open_the_dialog_and_take_the_pick(inputs, row):
    ui = Ui(make_app(), (1200, 800))
    app = ui.app
    spec = next(r for r in PATH_ROWS if r[0] == row)
    pick = {"trajectory": "small.dcd", "topology": "topol.pdb", "fps_json": "hiv_rt.fps.json"}[row]
    ui.click(f"{row}_browse")
    assert ui.dialog_open and ui.shown(spec[3]) and ui.shown("Cancel")
    app.dialog.enter(str(inputs))
    ui.draw(2)
    assert ui.shown(pick)
    ui.press_text("Cancel")
    assert not ui.dialog_open and not getattr(app.session, row)
    ui.click(f"{row}_browse")
    ui.press_text("×")
    assert not ui.dialog_open and not getattr(app.session, row)
    ui.click(f"{row}_browse")
    app.dialog.enter(str(inputs))
    ui.dialog_pick(pick)
    assert getattr(app.session, row) == str(inputs / pick)
    ui.click(f"{row}_browse")
    app.dialog.enter(str(inputs))
    ui.draw(2)
    ui.press_text(pick, clicks=2)  # a double click takes it at once
    assert not ui.dialog_open and getattr(app.session, row) == str(inputs / pick)
    app.close()


def test_a_path_row_is_read_only(inputs):
    ui = ready(inputs)
    before = ui.app.session.trajectory
    ui.click("trajectory", fx=0.3)
    ui.type_text("/etc/passwd")
    ui.key(keys.KEY_RETURN, "\r")
    assert ui.app.session.trajectory == before
    ui.app.close()


def test_a_drop_goes_to_the_row_it_fits(inputs):
    ui = Ui(make_app(), (1200, 800))
    s = ui.app.session
    assert ui.drop(inputs / "small.dcd", inputs / "topol.pdb", inputs / "hiv_rt.fps.json")
    assert (s.trajectory, s.topology, s.fps_json) == tuple(
        str(inputs / n) for n in ("small.dcd", "topol.pdb", "hiv_rt.fps.json")
    )
    s.trajectory = ""
    assert (
        ui.drop(inputs / "nothing.dcd")
        and ui.shown("No file among the dropped paths")
        and s.trajectory == ""
    )
    ui.app.close()


def test_failures_are_reported_in_a_message_and_the_status_line(inputs):
    ui = Ui(make_app(), (1200, 800))
    ui.click("run")  # no trajectory
    assert ui.app.session.wait(60)
    ui.draw(3)
    assert ui.app.modal is not None and ui.shown("Trajectory file does not exist")
    ui.press_text("OK")
    assert ui.app.modal is None and ui.shown("FRET pair selection failed")
    ui2 = ready(inputs, residues="1")  # one residue is no pair
    run_and_wait(ui2)
    assert ui2.shown("Need at least 2 valid residues")
    ui2.press_text("OK")
    empty = inputs / "empty.fps.json"  # an FPS JSON that names no position
    empty.write_text('{"Positions": {}, "Distances": {}}')
    ui3 = ready(inputs, fps_json=str(empty))
    run_and_wait(ui3)
    assert ui3.shown("fps.json did not yield at least 2 valid labeling positions")
    for u in (ui, ui2, ui3):
        u.app.close()


def test_the_core_runs_without_a_window(inputs):
    result = run_pair_selection(
        PairParams(
            trajectory=str(inputs / "small.dcd"), topology=str(inputs / "topol.pdb"), max_pairs=3
        )
    )
    assert [(n, p, round(v, 2)) for n, p, v in result.rows()] == EXPECTED_ROWS[:3]


def test_stride_changes_the_frames_read(inputs):
    ui = ready(inputs, stride=2)
    run_and_wait(ui)
    assert len(ui.app.session.rows) == 5
    from chisurf.plugins.modelling.fret.core.pair_run import load_trajectory

    assert load_trajectory(ui.app.session.params()).n_frames == 4
    ui.app.close()


def test_settings_round_trip(inputs):
    ui = ready(inputs, chain="B", r0=44.0)
    state = json.loads(json.dumps(ui.app.export_settings()))
    other = make_app()
    other.restore_settings(state)
    assert other.session.params() == ui.app.session.params()
    other.restore_settings({"max_pairs": "not an int", "r0": True})
    assert other.session.max_pairs == 5
    other.close()
    ui.app.close()


# ---- guide, help, layout ----------------------------------------------------------------------------------------


def test_the_tour_is_walked_by_the_user(inputs):
    """Each await step moves on only when the control it points at is used; Next / Prev / Close are pressed."""
    ui = Ui(make_app(), (1200, 800))
    app = ui.app
    ui.click("guide")
    steps = len(app.tour.steps)
    assert steps == 6 and app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next ►")
    assert app.tour.step_idx == 1  # the trajectory step awaits the "..." row
    for step in app.tour.steps:
        key = step.get("target", {}).get("key")
        assert not key or key in app.item_rects or key in ("run", "export"), key
    ui.click("trajectory_browse")  # use the awaited control: dialog opens, pick a file
    app.dialog.enter(str(inputs))
    ui.dialog_pick("small.dcd")
    ui.draw(3)
    assert app.tour._step_used, "the await step did not complete when the awaited control was used"
    ui.press_text("Next ►")
    assert app.tour.step_idx == 2
    app.tour.start(4)
    ui.draw(3)
    s = app.session
    s.topology, s.max_pairs = str(inputs / "topol.pdb"), 3
    ui.click("run")
    assert s.wait(120)
    ui.draw(3)
    assert app.tour.step_idx == 5
    ui.press_text("◄ Prev")
    assert app.tour.step_idx == 4
    ui.press_text("Close Tour")
    assert not app.tour.active
    app.close()


def test_help_opens_and_closes(inputs):
    ui = Ui(make_app(), (1200, 800))
    ui.click("help")
    assert ui.app.help_window.open and ui.shown("Optimal FRET pair selection")
    ui.press_text("Close Help")
    assert not ui.app.help_window.open
    ui.app.close()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_draws_empty_and_populated_with_a_tooltip_everywhere(inputs, size):
    ui = ready(inputs, size)
    assert ui.shown("Candidate sites from residues") and ui.shown("Trajectory")
    run_and_wait(ui)
    from emtk.testing import RecordingPainter  # noqa: F401

    for key in (
        "trajectory",
        "topology",
        "fps_json",
        "stride",
        "chain",
        "residues",
        "atom",
        "r0",
        "use_av",
        "av_samples",
        "av_max_points",
        "max_pairs",
        "err",
        "unique_only",
        "rmsd_selection",
        "run",
        "export",
        "guide",
        "help",
    ):
        assert key in ui.app.item_rects, key
        x, y, w, h = ui.app.item_rects[key]
        assert 0 <= x and x + w <= size[0] and 0 <= y and y + h <= size[1] + 600, (
            key,
            ui.app.item_rects[key],
            size,
        )
    ui.app.close()


def test_every_field_declares_a_description():
    spec = make_app().spec

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle"):
                assert s.get("description"), s.get("attr")
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_nothing_is_written_under_the_home_folder(inputs, tmp_path):
    ui = ready(inputs)
    run_and_wait(ui)
    ui.app.export_settings()
    ui.app.close()
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
