"""FPS JSON card: ctrl/shift-click selects several rows; Delete Row(s), Delete AV(s) and Save AV MRC act on them."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from chisurf.plugins.modelling.structure_tools.cards.fps_json import make_app as make_fps
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
CTRL, SHIFT = 0x04000000, 0x02000000


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
        pos["pdb_path"] = str(
            tmp_path / ("dna.pdb" if pos["chain_identifier"] == "P" else "protein_1R0A.pdb")
        )
    fps = tmp_path / "x.fps.json"
    fps.write_text(json.dumps(payload))
    return fps


def click_row(ui, name, modifiers=0):
    """Press and release the pointer on the table row that drew *name*, holding *modifiers*."""
    x, y, w, h = ui.text_rect(name)
    x, y = x + w / 2, y + h / 2
    ui.app.pointer_move(x, y)
    ui.draw(1)
    ui.app.pointer_press(x, y, 1, modifiers, 1)
    ui.draw(1)
    ui.app.pointer_release(x, y, 1, modifiers)
    ui.draw(2)


@pytest.fixture()
def ui(inputs):
    app = make_fps()
    app.editor.auto_av = False
    ui = Ui(app, (1200, 800))
    assert ui.drop(inputs)
    ui.draw(3)
    yield ui
    app.close()


def names(app):
    return list(app.editor.doc.positions)


def test_ctrl_and_shift_click_select_rows_and_delete_removes_them_after_one_question(ui):
    app = ui.app
    first, second, third, fourth = names(app)[:4]
    view = app.views["positions"]
    click_row(ui, first)
    click_row(ui, third, CTRL)
    assert view.picked_ids() == [first, third]
    click_row(ui, second, SHIFT)  # range from the anchor (the ctrl-clicked row) to this one
    assert set(view.picked_ids()) == {second, third}
    click_row(ui, first)
    click_row(ui, fourth, SHIFT)
    assert view.picked_ids() == names(app)[:4]
    click_row(ui, third, CTRL)
    picked = view.picked_ids()
    assert third not in picked and len(picked) == 3
    before = len(names(app))
    ui.click("delete_row")
    assert app.modal is not None and "3 rows" in app.modal["text"]
    ui.press_text("Keep")
    assert len(names(app)) == before
    ui.click("delete_row")
    ui.press_text("Remove")
    assert len(names(app)) == before - 3 and third in names(app)


def test_delete_avs_and_save_selected_avs_as_mrc(ui, tmp_path):
    app = ui.app
    ed = app.editor
    a, b, c = names(app)[:3]
    for rid in (a, b, c):
        assert ed.schedule_av(rid)
    assert ed.wait(240)
    ui.draw(3)
    assert all(rid in ed.av_cache for rid in (a, b, c))
    click_row(ui, a)
    click_row(ui, b, CTRL)
    # Save AV MRC writes the two selected volumes, not the third
    ui.click("save_mrc")
    assert app.dialog is not None
    out = tmp_path / "mrc"
    out.mkdir()
    app.dialog.directory = str(out)
    ui.press_text("Choose")
    ui.draw(3)
    written = sorted(p.name for p in out.glob("*.mrc"))
    assert len(written) == 2 and all(p.stat().st_size > 0 for p in out.glob("*.mrc")), written
    # Delete AV(s) drops the volumes of the selection and keeps the positions
    ui.click("delete_avs")
    ui.draw(2)
    assert a not in ed.av_cache and b not in ed.av_cache and c in ed.av_cache
    assert a in names(app) and b in names(app)


def test_distances_ctrl_and_shift_click_select_restraints_and_delete_removes_them_after_one_question(
    ui,
):
    app = ui.app
    view = app.views["distances"]
    ui.click("tab_Distances")
    ui.draw(3)
    ids = list(app.editor.doc.distances)
    first, second, third, fourth = (
        "p66_T27C_p_1bp",
        "p66_T27C_p_19bp",
        "p66_E194C_p_1bp",
        "p66_E194C_p_19bp",
    )
    assert {first, second, third, fourth} <= set(ids)
    click_row(ui, first)
    click_row(ui, third, CTRL)
    assert view.picked_ids() == [first, third]
    click_row(ui, fourth, SHIFT)  # from the ctrl-clicked row to this one
    assert view.picked_ids() == ids[ids.index(third) : ids.index(fourth) + 1]
    click_row(ui, second)
    click_row(ui, fourth, SHIFT)
    assert view.picked_ids() == ids[ids.index(second) : ids.index(fourth) + 1]
    click_row(ui, third, CTRL)
    picked = view.picked_ids()
    assert third not in picked and second in picked and fourth in picked
    before = len(ids)
    ui.click("delete_dist")
    assert app.modal is not None and f"{len(picked)} restraints" in app.modal["text"]
    ui.press_text("Keep")
    assert len(app.editor.doc.distances) == before
    ui.click("delete_dist")
    ui.press_text("Remove")
    left = list(app.editor.doc.distances)
    assert len(left) == before - len(picked) and third in left and not set(picked) & set(left)
    # one selected restraint still asks the single question and removes only that one
    click_row(ui, third)
    ui.click("delete_dist")
    assert app.modal is not None and "this restraint" in app.modal["text"]
    ui.press_text("Remove")
    assert third not in app.editor.doc.distances and len(app.editor.doc.distances) == len(left) - 1
