"""The native FPS JSON editor driven by real input: pointer presses at the drawn controls, typed text, the file dialog.

Covers the user paths the Qt ``FpsJsonEditorTool`` has and ``structure_tools/test/test_cards.py`` does not: typed
values in the position and distance forms (with Qt's ranges, negatives where Qt allows them), every form field
reachable at 800x600, Save through the dialog, Update from the JSON tab, removing a row behind its question,
scoring groups, the FlexFit set / residue / bond buttons, Help and Guide. Hermetic: temp settings and HOME, the
example HIV-RT fps.json and its two structures, no network, no AV computation unless a test asks for it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui, check_guide_and_help_buttons

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
SIZES = [(1200, 800), (800, 600)]
HEADER = 18.0  # height of the table header row
ROW = 19.0  # height of a table row


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture()
def fps(tmp_path):
    """The HIV-RT example with its structures beside it, one scoring group and one FlexFit set."""
    for name in ("protein_1R0A.pdb", "dna.pdb"):
        shutil.copy(EXAMPLE / name, tmp_path / name)
    payload = json.loads((EXAMPLE / "hiv_rt.fps.json").read_text())
    for pos in payload["Positions"].values():
        pos["pdb_path"] = str(tmp_path / ("dna.pdb" if pos["chain_identifier"] == "P" else "protein_1R0A.pdb"))
    names = list(payload["Distances"])
    payload["χ²"] = {"all": {"distances": names}}
    payload["FlexFit"] = {"set_1": {"Flexible residues": [{"chain_identifier": "A", "residue_seq_number": 6}],
                                    "Bonds": []}}
    path = tmp_path / "hiv_rt.fps.json"
    path.write_text(json.dumps(payload))
    return path


def _open(fps, size=(1200, 800)):
    app = make_app()
    app.editor.auto_av = False
    ui = Ui(app, size)
    assert ui.drop(fps) and len(app.editor.doc.positions) == 11
    return ui


def _click_row(ui, table, index, column_x=100.0):
    """Press on row *index* of the data table drawn as *table*."""
    ui.draw(1)
    x, y, _, _ = ui.app.item_rects[table]
    return ui.click_at(x + column_x, y + HEADER + ROW * (index + 0.5))


def _select(ui, name):
    """Press on the table row whose cell shows *name* (the first drawn text equal to it)."""
    ui.draw(1)
    return ui.click(ui.text_rect(name, 0))


def _reveal(ui, key):
    """Wheel the window until the control *key* is fully inside it; its rectangle."""
    for _ in range(20):
        ui.draw(1)
        rect = ui.app.item_rects.get(key)
        assert rect is not None, f"{key} is not drawn"
        x, y, w, h = rect
        if y >= 0 and y + h <= ui.size[1] - 2:
            return rect
        ui.app.pointer_move(20, ui.size[1] / 2)
        ui.draw(1)
        ui.app.wheel(20, ui.size[1] / 2, -3 if y + h > ui.size[1] else 3)
        ui.draw(1)
    raise AssertionError(f"{key} cannot be scrolled into the window: {ui.app.item_rects.get(key)}")


def _type_field(ui, key, text):
    _reveal(ui, key)
    return ui.type_into(key, text)


def _expand(ui, panel):
    """Open a folded panel of the form (Simulation, Advanced) by pressing its header."""
    ui.click(_reveal(ui, f"{panel}.fold"))


def _field(ui, key):
    ed = ui.app.editor
    return ed.position_field(ed.selected_pos, key, None)


# ---- the position form ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_every_position_field_is_reachable_and_typed(fps, size):
    ui = _open(fps, size)
    _select(ui, "p51_K173C")
    assert ui.app.editor.selected_pos == "p51_K173C"
    _expand(ui, "Simulation")
    _expand(ui, "Advanced")
    typed = {
        "linker_length": ("35.5", 35.5),
        "linker_width": ("3.25", 3.25),
        "radius1": ("4", 4.0),
        "radius2": ("2.5", 2.5),
        "radius3": ("1.5", 1.5),
        "body_id": ("12", 12),
        "allowed_sphere_radius": ("2", 2.0),
        "simulation_grid_resolution": ("0.5", 0.5),
        "contact_volume_thickness": ("1.5", 1.5),
        "contact_volume_trapped_fraction": ("-1", -1.0),  # Qt allows -1: "not used"
        "min_sphere_volume_fraction": ("0.25", 0.25),
    }
    for key, (text, value) in typed.items():
        _type_field(ui, key, text)
        assert _field(ui, key) == pytest.approx(value), key
    _type_field(ui, "anchor_atoms", "CA,CB")
    _type_field(ui, "strip_mask", "resname HOH")
    assert _field(ui, "anchor_atoms") in ("CA,CB", ["CA", "CB"])
    assert _field(ui, "strip_mask") == "resname HOH"
    ui.app.close()


def test_typed_values_are_clamped_to_the_qt_ranges(fps):
    ui = _open(fps, (800, 600))
    _select(ui, "p51_E194C")
    _expand(ui, "Advanced")
    for key, text, value in (
        ("linker_length", "-5", 0.0),
        ("linker_length", "500", 200.0),
        ("radius1", "-1", 0.0),
        ("contact_volume_trapped_fraction", "-3", -1.0),
        ("contact_volume_trapped_fraction", "-0.5", -0.5),
        ("min_sphere_volume_fraction", "2", 1.0),
    ):
        _type_field(ui, key, text)
        assert _field(ui, key) == pytest.approx(value), (key, text)
    before = _field(ui, "linker_length")
    _type_field(ui, "linker_length", "abc")  # a typo leaves the value as it was
    assert _field(ui, "linker_length") == before
    ui.app.close()


def test_rows_are_added_and_removed_behind_the_question(fps):
    ui = _open(fps)
    ed = ui.app.editor
    _select(ui, "p51_E194C")
    assert ed.selected_pos == "p51_E194C"
    n_dist = len(ed.doc.distances)
    ui.click("delete_row")
    assert ui.app.modal is not None and ui.shown("Remove p51_E194C and every distance that uses it?")
    ui.press_text("Keep")
    assert "p51_E194C" in ed.doc.positions
    ui.click("delete_row")
    ui.press_text("Remove")
    assert "p51_E194C" not in ed.doc.positions and len(ed.doc.positions) == 10
    assert len(ed.doc.distances) < n_dist
    assert not any("p51_E194C" in name for name in ed.doc.distances)
    ui.app.close()


# ---- files ------------------------------------------------------------------------------------------------------


def test_save_through_the_dialog_round_trips(fps, tmp_path):
    ui = _open(fps)
    _select(ui, "p51_K173C")
    _type_field(ui, "linker_length", "33")
    ui.click("save")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.save_dialog_type_name("edited")
    ui.press_text("Save")
    out = tmp_path / "edited.fps.json"
    assert out.exists(), list(tmp_path.iterdir())
    saved = json.loads(out.read_text())
    assert len(saved["Positions"]) == 11 and len(saved["Distances"]) == 20
    assert saved["Positions"]["p51_K173C"]["linker_length"] == pytest.approx(33.0)
    ui.app.close()
    again = _open(out)
    assert again.app.editor.position_field("p51_K173C", "linker_length", None) == pytest.approx(33.0)
    again.app.close()


def test_update_reads_the_json_tab(fps):
    ui = _open(fps)
    ui.click("tab_JSON")
    assert ui.app.tab == "JSON" and ui.shown('"Distances"')
    ui.click("json_text", fx=0.5, fy=0.2)
    ui.type_text('{"Positions": {"typed_site": {"chain_identifier": "A", "residue_seq_number": 6, '
                 '"atom_name": "CB"}}, "Distances": {}}')
    ui.click("update")
    assert list(ui.app.editor.doc.positions) == ["typed_site"] and not ui.app.editor.doc.distances
    ui.click("tab_Positions")
    assert ui.shown("typed_site")
    ui.app.close()


# ---- distances and scoring groups -------------------------------------------------------------------------------


def test_distance_form_and_scoring_groups(fps):
    ui = _open(fps, (800, 600))
    ed = ui.app.editor
    ui.click("tab_Distances")
    _click_row(ui, "dist_rows", 0)
    assert ed.selected_dist
    for key, text, value in (("distance", "51.5", 51.5), ("error_neg", "2.5", 2.5), ("error_pos", "3", 3.0),
                             ("Forster_radius", "54", 54.0), ("distance", "-4", 0.0)):
        _type_field(ui, key, text)
        assert ed._dist(ed.selected_dist)[key] == pytest.approx(value), key
    ui.click("add_set")
    assert ui.app.modal is not None
    ui.type_text("first_two")
    ui.key(keys.KEY_RETURN, "\r")
    ui.draw(2)
    assert "first_two" in ed.score_set_names
    n = len(ed.doc.distances)
    ui.click("add_dist")
    assert len(ed.rows_dist) == n + 1
    ui.app.close()


# ---- FlexFit ----------------------------------------------------------------------------------------------------


def test_flexfit_sets_residues_and_bonds(fps):
    ui = _open(fps)
    ed = ui.app.editor
    ui.click("tab_FlexFit")
    assert ed.flexfit_names == ["set_1"]
    ui.click("flex_add_set")
    ui.type_text("set_2")
    ui.key(keys.KEY_RETURN, "\r")
    ui.draw(2)
    assert "set_2" in ed.flexfit_names and ed.flexfit_set == "set_2"
    ui.click("flex_add_res")
    ui.click("flex_add_bond")
    assert len(ed.rows_res) == 1 and len(ed.rows_bond) == 1
    _click_row(ui, "res_rows", 0, column_x=20.0)
    assert ed.selected_residue == 0
    ui.click("flex_remove_res")
    assert len(ed.rows_res) == 0
    ui.click("flex_remove_set")
    assert ed.flexfit_names == ["set_1"]
    ui.app.close()


# ---- help and guide ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_guide_and_help_buttons(size):
    check_guide_and_help_buttons(make_app, size=size)


# ---- structures, accessible volumes, MRC ----------------------------------------------------------------------------


def _settle(ui, timeout=300.0):
    """Draw until the AV worker has finished and its result is shown."""
    import time

    end = time.monotonic() + timeout
    ui.draw(2)
    while ui.app.editor.busy:
        assert time.monotonic() < end, "the AV computation did not finish"
        time.sleep(0.05)
        ui.draw(1)
    return ui.draw(3)


def test_browse_pdb_compute_avs_and_save_mrc(fps, tmp_path):
    ui = _open(fps)
    ed = ui.app.editor
    _select(ui, "p51_E194C")
    ui.click("browse_pdb")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("dna.pdb")
    assert ed.position_field("p51_E194C", "pdb_path", "").endswith("dna.pdb")
    _select(ui, "p51_K173C")
    ui.click("compute_avs")
    _settle(ui)
    assert ed.computed_names("p51_K173C") == ["p51_K173C"]
    assert ui.shown("Calculated"), ui.strings[:20]
    ui.click("save_mrc")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.press_text("Save")
    mrc = tmp_path / "p51_K173C.mrc"
    assert mrc.exists() and mrc.stat().st_size > 1024
    assert ui.shown("Saved 1 AV MRC map(s).")
    ui.click("tab_3D View")
    assert not ui.shown("Nothing to show")
    ui.app.close()


# ---- choices --------------------------------------------------------------------------------------------------------


def _choose(ui, key, option):
    """Open the combo *key* and press its entry *option*."""
    ui.click(_reveal(ui, key))
    ui.press_text(option)


def test_choice_fields_dye_model_preset_and_distance_type(fps, tmp_path):
    ui = _open(fps)
    ed = ui.app.editor
    _select(ui, "p51_K173C")
    _choose(ui, "p_model", "AV3")
    assert _field(ui, "simulation_type") == "AV3"
    _choose(ui, "p_preset", "D1-Alexa488")
    assert _field(ui, "dye_preset") == "D1-Alexa488"
    ui.click("tab_Distances")
    _click_row(ui, "dist_rows", 0)
    rid = ed.selected_dist
    _choose(ui, "d_type", "pRDA")
    assert ed._dist(rid)["distance_type"] == "pRDA"
    table = tmp_path / "prda.txt"
    table.write_text("R_DA\tp\n40\t0.2\n50\t0.6\n60\t0.2\n")
    ui.draw(2)
    ui.press_text("Load DA Distribution...")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("prda.txt")
    assert ed._dist(rid)["rda"] == [40.0, 50.0, 60.0] and ed._dist(rid)["prda"] == [0.2, 0.6, 0.2]
    assert ui.shown("Loaded: 3 points")
    ui.app.close()


# ---- 3D View: the molecular viewer (chimol, as the Qt editor embeds it) --------------------------------------------


@pytest.fixture()
def view3d(fps):
    """The editor with every AV computed, on the 3D View tab; skipped where chimol cannot render (no WebGPU)."""
    ui = _open(fps)
    ui.app.editor.compute_all()
    _settle(ui)
    _select(ui, "p51_E194C")
    ui.click("tab_3D View")
    ui.draw(3)
    if ui.app.chimol.error:
        ui.app.close()
        pytest.skip(f"chimol cannot render here: {ui.app.chimol.error}")
    yield ui
    ui.app.close()


def test_3d_view_shows_cartoon_av_surfaces_means_and_distance_lines(view3d):
    viewer = view3d.app.chimol.viewer
    assert sorted(o["name"] for o in viewer.list_objects()) == ["dna", "protein_1R0A"]
    overlays = set(viewer._point_overlays or {})
    assert sum(k.startswith("av_") for k in overlays) == 11
    assert sum(k.startswith("mean_") for k in overlays) == 11
    assert sum(k.startswith("dist_line_") for k in viewer.measurements) == 20
    frame = view3d.app.chimol.frame
    assert frame is not None and frame.ndim == 3 and frame[..., :3].std() > 5  # a picture, not a blank canvas
    # hiding a position takes its volume out of the view, as in Qt
    view3d.app.editor.set_position("p66_Q6C", "visible", False)
    view3d.draw(2)
    assert "av_p66_Q6C" not in set(viewer._point_overlays or {})


def test_3d_view_drag_rotates_and_wheel_zooms(view3d):
    x, y, w, h = view3d.app.item_rects["plot3d"]
    cx, cy = x + w * 0.4, y + h * 0.5
    before = view3d.app.chimol.frame.copy()
    view3d.app.pointer_move(cx, cy)
    view3d.draw(1)
    view3d.app.press(cx, cy)
    view3d.draw(1)
    for i in range(1, 6):
        view3d.app.pointer_move(cx + 15 * i, cy + 4 * i, 1)
        view3d.draw(1)
    view3d.app.release()
    view3d.draw(2)
    rotated = view3d.app.chimol.frame.copy()
    assert np.abs(rotated.astype(int) - before.astype(int)).mean() > 1.0, "a drag did not rotate"
    view3d.app.wheel(cx, cy, -3)
    view3d.draw(2)
    assert np.abs(view3d.app.chimol.frame.astype(int) - rotated.astype(int)).mean() > 1.0, "the wheel did not zoom"


def test_clicking_an_atom_attaches_the_selected_position(view3d):
    """Qt: an atom picked in the viewer becomes the current row's chain / residue / atom."""
    app = view3d.app
    ed = app.editor
    viewer = app.chimol.viewer
    renderer = app.chimol.app.renderer
    struct = ed.structure(ed.position_field("p51_E194C", "pdb_path", ""))
    picks: list = []
    viewer.atomSelectionChanged.connect(lambda idx: picks.append(list(idx)))
    rx, ry, rw, rh = app.chimol.rect
    fw, fh = app.chimol._render_size
    ca = np.flatnonzero(struct.atoms["atom_name"] == "CA")
    scene = viewer._transform_world_coords_to_scene(np.asarray(struct.atoms["xyz"])[ca])
    sx, sy, visible = renderer.project_to_screen(scene)
    centre = np.hypot(sx - fw / 2, sy - fh / 2)
    order = [i for i in np.argsort(centre) if visible[i]][:40]
    picked = None
    for i in order:
        picks.clear()
        view3d.click_at(rx + sx[i] * rw / fw, ry + sy[i] * rh / fh)
        if picks and picks[-1] and app._chimol_objects.get(viewer.get_active_object_id(), "").endswith("protein_1R0A.pdb"):
            picked = struct.atoms[picks[-1][0]]
            break
    assert picked is not None, "no protein atom answered a click"
    assert ed.position_field("p51_E194C", "chain_identifier", "") == str(picked["chain"]).strip()
    assert int(ed.position_field("p51_E194C", "residue_seq_number", 0)) == int(picked["res_id"])
    assert ed.position_field("p51_E194C", "atom_name", "") == str(picked["atom_name"]).strip()
    assert view3d.shown("(picked)")
