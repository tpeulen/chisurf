"""Structure Tools cards: FPS JSON editor, docking, QuEst. Hermetic: temp settings, no network, real example files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.modelling.structure_tools.cards.docking import make_app as make_dock
from chisurf.plugins.modelling.structure_tools.cards.docking_model import DockingSession
from chisurf.plugins.modelling.structure_tools.cards.fps_json import make_app as make_fps
from chisurf.plugins.modelling.structure_tools.cards.fps_model import FpsEditor
from chisurf.plugins.modelling.structure_tools.cards.quest import make_app as make_quest
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture()
def inputs(tmp_path):
    for name in ("protein_1R0A.pdb", "dna.pdb"):
        shutil.copy(EXAMPLE / name, tmp_path / name)
    payload = json.loads((EXAMPLE / "hiv_rt.fps.json").read_text())
    for pos in payload["Positions"].values():
        pos["pdb_path"] = str(tmp_path / ("dna.pdb" if pos["chain_identifier"] == "P" else "protein_1R0A.pdb"))
    names = list(payload["Distances"])
    payload["χ²"] = {"all": {"distances": names}}
    fps = tmp_path / "x.fps.json"
    fps.write_text(json.dumps(payload))
    return fps


# ---- FPS model --------------------------------------------------------------------------------------------------


def test_fps_round_trip_equals_the_qt_model(inputs, tmp_path):
    from chisurf.plugins.modelling.fps_json_editor.core.model import FpsJsonModel

    ed = FpsEditor()
    ed.auto_av = False
    assert ed.load(str(inputs))
    qt = FpsJsonModel()
    qt.load_file(str(inputs))
    assert ed.doc.fps_json_payload == qt.fps_json_payload
    out = tmp_path / "out.fps.json"
    assert ed.save(str(out))
    written = json.loads(out.read_text())
    assert written.pop("FormatVersion") == "1.0"
    assert written == json.loads(inputs.read_text())


def test_rename_keeps_distances_and_empty_name_is_refused(inputs):
    ed = FpsEditor()
    ed.auto_av = False
    ed.load(str(inputs))
    n = len(ed.doc.distances)
    assert ed.set_position("p66_Q6C", "name", "Q6")
    assert "Q6" in ed.doc.positions and len(ed.doc.distances) == n
    assert any(d["position1_name"] == "Q6" for d in ed.doc.distances.values())
    assert not ed.set_position("Q6", "name", "")
    assert "Q6" in ed.doc.positions


def test_draft_row_is_named_from_chain_and_residue_and_av_is_computed(inputs, tmp_path):
    ed = FpsEditor()
    rid = ed.add_position_row()
    ed.set_position(rid, "pdb_path", str(tmp_path / "protein_1R0A.pdb"))
    assert list(ed.doc.positions) == ["A1"]            # named from the first chain and residue of the structure
    ed.set_position("A1", "chain_identifier", "B")
    ed.set_position("A1", "residue_seq_number", "173")
    assert ed.doc.positions["A1"]["chain_identifier"] == "B" and ed.doc.positions["A1"]["residue_seq_number"] == 173
    assert ed.wait(120)
    assert ed.av_cache


def test_distance_rows_and_score_sets(inputs):
    ed = FpsEditor()
    ed.auto_av = False
    ed.load(str(inputs))
    assert len(ed.rows_dist) == 20
    ed.add_score_set("few")
    first = ed.rows_dist[0]["row"]
    ed.set_distance(first, "score_set", "few")
    ed.set_score_filter("few")
    assert [r["row"] for r in ed.rows_dist] == [first]
    ed.set_score_filter("All distances")
    d = ed.add_distance_row()
    ed.set_distance(d, "position1_name", "p_1bp")
    assert not ed.set_distance(d, "position2_name", "p_1bp")
    assert ed.set_distance(d, "position2_name", "p_10bp") and "p_1bp_p_10bp" in ed.doc.distances


def test_flexfit_and_json_update(inputs):
    ed = FpsEditor()
    ed.auto_av = False
    ed.load(str(inputs))
    assert ed.add_flexfit_set("s")
    ed.add_flexfit_residue()
    ed.edit_flexfit_residue(0, "chain", "A")
    ed.edit_flexfit_residue(0, "residue", "7")
    assert ed.doc.extra_sections["FlexFit"]["s"]["Flexible residues"] == [
        {"chain_identifier": "A", "residue_seq_number": 7}]
    ed.json_text = "{not json"
    assert not ed.apply_json_text() and ed.status_error
    ed.json_text = json.dumps({"Positions": {}, "Distances": {}})
    assert ed.apply_json_text() and not ed.doc.positions


# ---- FPS window, real input -------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_fps_card_draws_every_tab(inputs, size):
    app = make_fps()
    app.editor.auto_av = False
    app.load_path(str(inputs))
    for tab in ("Positions", "Distances", "FlexFit", "JSON", "3D View"):
        app.tab = tab
        app.draw(RecordingPainter(), 0, 0, *size)
    app.close()


def test_fps_card_clicks_load_tabs_clear_and_drop(inputs):
    app = make_fps()
    app.editor.auto_av = False
    ui = Ui(app, (1200, 800))
    assert ui.drop(inputs) and len(app.editor.doc.positions) == 11
    ui.click("tab_Distances")
    assert app.tab == "Distances" and ui.shown("p51_E194C_p_10bp")
    ui.click("tab_Positions")
    ui.click("add_row")
    assert len(app.editor.pos_drafts) == 1
    ui.click("clear")                       # the question: Keep first
    assert ui.app.modal is not None
    ui.press_text("Keep")
    assert len(app.editor.doc.positions) == 11
    ui.click("clear")
    ui.press_text("Clear all")
    assert not app.editor.doc.positions
    ui.click("guide")
    assert app.tour.active
    app.close()


def test_fps_card_file_dialog_loads(inputs):
    app = make_fps()
    app.editor.auto_av = False
    ui = Ui(app, (1200, 800))
    ui.click("load")
    assert ui.dialog_open
    ui.app.dialog.enter(str(inputs.parent))
    ui.dialog_pick(inputs.name)
    assert len(app.editor.doc.positions) == 11
    app.close()


# ---- docking ----------------------------------------------------------------------------------------------------


def test_docking_request_equals_the_qt_models(inputs, tmp_path):
    pytest.importorskip("qtpy")
    from chisurf.plugins.modelling.fret.gui.dock_tool import _DockingModel

    s, q = DockingSession(), _DockingModel()
    pdbs = [str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")]
    for m in (s, q):
        m.fps_json, m.output_dir, m.n_frames, m.sigma_da = str(inputs), str(tmp_path / "o"), 77, 4.5
    s.add_pdbs(pdbs)
    q.pdb_paths = ", ".join(pdbs)
    for op in ("dock", "refine", "screen", "score"):
        s.operation = q.operation = op
        assert s.build_params() == q.build_params()
    s.operation = q.operation = "dock"
    s.n_repeats = q.n_repeats = 3
    assert s.build_params() == q.build_params()


def test_docking_runs_and_lists_the_result(inputs, tmp_path):
    app = make_dock()
    s = app.session
    s.add_pdbs([str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")])
    s.fps_json, s.output_dir, s.n_frames = str(inputs), str(tmp_path / "out"), 30
    ui = Ui(app, (1200, 800))
    ui.click("run")
    assert s.running
    assert s.poll_wait(120)
    ui.draw(3)
    assert len(s.rows) == 1 and s.rows[0]["score"] > 0 and (tmp_path / "out" / "docked.pdb").exists()
    app.close()


def test_docking_repeats_give_one_row_per_trial(inputs, tmp_path):
    s = DockingSession()
    s.add_pdbs([str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")])
    s.fps_json, s.output_dir, s.n_frames, s.n_repeats = str(inputs), str(tmp_path / "out"), 20, 2
    assert s.start() and s.poll_wait(120)
    assert len(s.rows) == 2 and "2 trials" in s.status
    s.close()


def test_docking_missing_input_and_drop(inputs, tmp_path):
    app = make_dock()
    ui = Ui(app, (800, 600))
    ui.click("run")
    assert ui.shown("Add at least one PDB file")
    assert ui.drop(tmp_path / "dna.pdb", inputs) and app.session.pdb_files and app.session.fps_json == str(inputs)
    app.close()


# ---- QuEst ------------------------------------------------------------------------------------------------------


def test_quest_card_draws_and_reports_when_unavailable(monkeypatch):
    from chisurf.plugins.modelling.structure_tools.cards import quest as qmod

    app = make_quest(qmod.QuestSession())
    for size in SIZES:
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
        if not app.session.ready:
            assert any("QuEst cannot start here" in t for t in painter.strings)
            assert "retry" in app.item_rects
    app.close()


def test_nothing_is_written_under_the_home_folder(inputs, tmp_path):
    """The cards write only where they are told (the fixture points HOME into the temp folder)."""
    app = make_fps()
    app.editor.auto_av = False
    app.load_path(str(inputs))
    app.save_path(str(tmp_path / "o.fps.json"))
    app.export_settings()
    app.close()
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
