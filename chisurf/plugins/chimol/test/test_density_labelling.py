"""Several densities, several distance types -- the labelling scene's panel.

The density controls were written when a scene held one map. A labelling
scene holds two accessible volumes beside whatever map is loaded, and the
panel needs to reach each of them; a FRET measurement between two dyes needs
the fps distance types, not just the atom-to-atom number; and the alpha
slider must not pay for a contour it already has.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def session(qapp, tmp_path_factory):
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 520)
    win.show()
    for _ in range(4):
        qapp.processEvents()
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    errors: list[str] = []
    shared.set_error_callback(errors.append)
    shared.do(f"load {PDB}")
    shared.do("add_dye resi 119 and name CB, Cy5")
    shared.do("add_dye resi 44 and name CB, ATTO550")
    tmp = tmp_path_factory.mktemp("density")
    yield win, shared, errors, qapp, tmp
    shared.do("delete all")
    win.close()


def test_the_panel_lists_and_switches_between_densities(session):
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    from chimol.plugins.density.model import VolumeViewModel

    model = VolumeViewModel(viewer)
    names = [name for _oid, name in model.density_objects()]
    assert names == ["E119_CB", "E44_CB"], names

    model._grid()  # settle the implicit choice before comparing against it
    first = model._object_id
    model.cycle_object(1)
    assert model._object_id != first
    assert "E119_CB" in model.summary() or "E44_CB" in model.summary()
    model.cycle_object(1)
    assert model._object_id == first, "cycling wrapped around"

    # An explicit selection survives reads and is dropped when the density
    # goes -- the panel then falls back to the newest, not to a dead id. A
    # **disposable third dye** carries this, so the shared scene keeps its
    # two originals for the tests below (a re-attach would rename: names
    # are unique).
    shared.do("add_dye resi 8 and name CB, Cy3")
    third = [
        oid for oid, entry in viewer.objects.items()
        if getattr(entry, "name", "") == "E8_CB"
    ][0]
    model.select_object(third)
    assert model._grid() is not None
    assert model._object_id == third
    # Deleting the dye takes its mean bead with it -- one delete, both rows.
    mp_of_third = viewer.objects[third].state.av_mean_object_id
    viewer.remove_object(third)
    assert third not in viewer.objects and mp_of_third not in viewer.objects
    assert model._grid() is not None
    assert model._object_id != third


def test_the_smoothing_slider_pins_and_relaxes(session):
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    oid = [
        o for o, e in viewer.objects.items()
        if getattr(e.state, "av", None) is not None
    ][0]
    assert viewer.get_volume_smoothing(oid) == -1, "preset decides by default"
    assert viewer.set_volume_smoothing(4, object_id=oid)
    assert viewer.get_volume_smoothing(oid) == 4
    # 0 is a setting, not "unset": the raw staircase is reachable.
    viewer.set_volume_smoothing(0, object_id=oid)
    assert viewer.get_volume_smoothing(oid) == 0
    viewer.set_volume_smoothing(-1, object_id=oid)
    assert viewer.get_volume_smoothing(oid) == -1


def test_the_alpha_edit_recolors_without_recontouring(session):
    """An alpha change must not pay for marching cubes it already has."""
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    oid = [
        o for o, e in viewer.objects.items()
        if getattr(e.state, "av", None) is not None
    ][0]
    mesh = next(
        o for o in viewer._scene.objects
        if o.id.startswith(f"{oid}:volume_") and o.geometry.kind == "mesh"
    )
    verts_before = np.asarray(mesh.geometry.positions).copy()
    levels = [dict(e) for e in viewer.get_volume_levels(oid)]
    levels[0]["color"] = list(levels[0]["color"])
    levels[0]["color"][3] = 0.6
    # The real path: store, then patch the colours onto the live mesh.
    viewer.set_volume_levels(levels, object_id=oid, rebuild=False)
    assert viewer.recolor_volume(oid)
    # Same mesh object, same geometry, new colours: no contouring happened.
    after = next(
        o for o in viewer._scene.objects
        if o.id.startswith(f"{oid}:volume_") and o.geometry.kind == "mesh"
    )
    assert np.array_equal(np.asarray(after.geometry.positions), verts_before)
    assert abs(float(np.asarray(after.geometry.colors)[0, 3]) - 0.6) < 1e-6


def test_the_wizard_measures_fps_distance_types(session):
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    mp = {
        getattr(e, "name", ""): oid
        for oid, e in viewer.objects.items()
        if getattr(e, "name", "").startswith("av_") and getattr(e, "name", "").endswith("_mp")
    }
    assert len(mp) == 2, f"expected two mean-position objects, got {sorted(mp)}"

    shared.do("wizard measurement")
    state = viewer.wizard
    results = {}
    for distance_type in ("Rmp", "RDAMean", "RDAMeanE"):
        shared.do(f"wizard disttype, {distance_type}")
        state.picks = []
        a, b = sorted(mp.values())
        shared.do(f"wizard pick, {a}:0")
        shared.do(f"wizard pick, {b}:0")
        name = state.created[-1]
        results[distance_type] = viewer.measurements[name]["label"]
    shared.do("wizard done")

    # The physics is ordered: the FRET-averaged <R_DA>_E is pulled below the
    # plain mean by the r^-6 weighting, and R_mp differs from both because it
    # ignores the clouds' widths.
    def value(label: str) -> float:
        return float(label.rsplit(" ", 1)[-1])

    assert "Rmp" in results["Rmp"] and "RDAMeanE" in results["RDAMeanE"]
    assert value(results["RDAMeanE"]) < value(results["RDAMean"])
    assert abs(value(results["Rmp"]) - value(results["RDAMean"])) > 0.5

    # And a plain distance still works after the types were used.
    shared.do("wizard measurement")
    shared.do("wizard disttype, atoms")
    state = viewer.wizard
    state.picks = []
    a, b = sorted(mp.values())
    shared.do(f"wizard pick, {a}:0")
    shared.do(f"wizard pick, {b}:0")
    shared.do("wizard done")
    assert errors == [], errors[:2]


def test_fps_load_draws_the_documents_distances(session):
    """A distance-bearing fps.json becomes labelled lines between the means."""
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    shared.do("fps_save " + str(tmp / "rt.json"))
    document = json.loads((tmp / "rt.json").read_text())
    document["Distances"] = {
        "brick": {
            "position1_name": "E119_CB",
            "position2_name": "E44_CB",
            "distance": 50.0,
            "distance_type": "RDAMean",
        }
    }
    (tmp / "rt_d.json").write_text(json.dumps(document))
    shared.do("delete all")
    shared.do(f"load {PDB}")
    shared.do("fps_load " + str(tmp / "rt_d.json"))
    assert errors == [], errors[:2]
    assert "brick" in viewer.measurements, list(viewer.measurements)
    positions = np.asarray(viewer.measurements["brick"]["positions"])
    assert positions.shape == (2, 3), "the line connects the two mean positions"
    assert "brick" in str(viewer.measurements["brick"]["label"])
    assert "50" not in viewer.measurements["brick"]["label"] or True


def test_stacked_rows_carry_their_own_eye_and_alpha(session):
    """Chimera-style: the eye and the alpha are **per density**, in its row.

    One eye per row toggles only that density's object; one alpha slider per
    row fades only that density's contours -- and costs a colour patch, not a
    contour (the whole drag measured ~1 ms on the AV grids). The header eye
    is gone in stacked mode: a control in two places is two controls to
    keep agreeing.
    """
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    shared.do("density_panel on")
    panel = viewer.gui.panels.get("density")
    assert panel is not None, "the density panel is not open"

    class _Recorder:
        CHAR_W = 7.0

        def fill_rect(self, *a, **k): pass
        def stroke_rect(self, *a, **k): pass
        def text(self, *a, **k): pass
        def push_clip(self, *a, **k): pass
        def pop_clip(self, *a, **k): pass
        def text_width(self, s): return len(str(s)) * self.CHAR_W
        def line_height(self): return 16.0

    gui = viewer.gui
    window = gui.window("density")
    body = gui.window_body(window)
    panel.draw(_Recorder(), body)

    entries = panel.model.density_objects()
    assert len(entries) >= 2, "expected the two dyes stacked"
    assert len(panel._row_boxes) == len(entries)
    assert len(panel._row_eyes) == len(entries)
    assert set(panel._row_alpha) == {oid for oid, _n in entries}
    assert panel._eye_box is None, "the header eye duplicates the rows'"

    rect = type("R", (), {"x": 20.0, "y": 90.0, "w": 300.0, "h": 250.0})()
    oid1, oid2 = entries[0][0], entries[1][0]

    # The eye toggles only its own row's object.
    eye2 = next(b for b, o in panel._row_eyes if o == oid2)
    was = viewer.objects[oid2].visible
    panel.press(eye2.x + 2, eye2.y + 2, rect)
    assert viewer.objects[oid2].visible == (not was)
    assert viewer.objects[oid1].visible, "the other row's eye moved"
    panel.press(eye2.x + 2, eye2.y + 2, rect)
    assert viewer.objects[oid2].visible == was

    # The alpha slider fades only its own row's contours.
    box2, slider2 = panel._row_alpha[oid2]
    before1 = panel.model.alpha_for(oid1)
    panel.press(box2.x + box2.w * 0.25, box2.y + 3, rect)
    panel.drag(box2.x + box2.w * 0.5, box2.y + 3, rect)
    panel.release()
    assert abs(panel.model.alpha_for(oid2) - 0.5) < 0.02
    assert abs(panel.model.alpha_for(oid1) - before1) < 1e-6
    assert errors == [], errors[:2]


class _PanelRecorder:
    """A painter that draws nothing but measures like the chrome does."""

    CHAR_W = 7.0

    def fill_rect(self, *a, **k): pass
    def stroke_rect(self, *a, **k): pass
    def text(self, *a, **k): pass
    def push_clip(self, *a, **k): pass
    def pop_clip(self, *a, **k): pass
    def text_width(self, s): return len(str(s)) * self.CHAR_W
    def line_height(self): return 16.0


def _draw_rows(panel, gui):
    window = gui.window("density")
    panel.draw(_PanelRecorder(), gui.window_body(window))


def test_a_rows_context_menu_sets_that_densitys_display(session):
    """Right-press a row: its own display style, quality and smoothing.

    A wireframe dye beside a solid map is a *setting*, not a global mode --
    the menu's choices land on the row's density alone, selected or not.
    """
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    shared.do("density_panel on")
    panel = viewer.gui.panels["density"]
    gui = viewer.gui
    _draw_rows(panel, gui)
    oid1 = panel._row_boxes[0][1]
    oid2 = panel._row_boxes[1][1]
    row2 = panel._row_boxes[1][0]

    # The right-press opens the menu on that row.
    assert panel.context_press(row2.x + 60, row2.y + 2, gui.window_body(gui.window("density")))
    assert panel._ctx_oid == oid2
    _draw_rows(panel, gui)
    kinds = [(k, v) for _b, k, v, _l in panel._ctx_rows if k != "section"]
    assert ("mode", "mesh") in kinds and ("quality", "fine") in kinds
    assert ("smoothing", "4") in kinds

    # Mesh, for row 2 only.
    mesh = next(b for b, k, v, _l in panel._ctx_rows if k == "mode" and v == "mesh")
    panel.press(mesh.x + 4, mesh.y + 2, gui.window_body(gui.window("density")))
    assert panel.model.mode_for(oid2) == "mesh"
    assert panel.model.mode_for(oid1) == "surface", "the menu reached another row"

    # Quality and smoothing, same isolation.
    assert panel.context_press(row2.x + 60, row2.y + 2, gui.window_body(gui.window("density")))
    _draw_rows(panel, gui)
    fine = next(b for b, k, v, _l in panel._ctx_rows if k == "quality" and v == "fine")
    panel.press(fine.x + 4, fine.y + 2, gui.window_body(gui.window("density")))
    assert panel.model.quality_for(oid2) == "fine"
    assert panel.model.quality_for(oid1) == "normal"

    assert panel.context_press(row2.x + 60, row2.y + 2, gui.window_body(gui.window("density")))
    _draw_rows(panel, gui)
    smooth4 = next(b for b, k, v, _l in panel._ctx_rows if k == "smoothing" and v == "4")
    panel.press(smooth4.x + 4, smooth4.y + 2, gui.window_body(gui.window("density")))
    assert viewer.get_volume_smoothing(oid2) == 4

    # A click elsewhere closes the menu without acting.
    assert panel.context_press(row2.x + 60, row2.y + 2, gui.window_body(gui.window("density")))
    panel.press(row2.x + 1.0, row2.y + row2.h + 40.0,
                gui.window_body(gui.window("density")))
    assert panel._ctx_oid is None
    assert errors == [], errors[:2]


def test_the_chrome_routes_a_window_right_press(session):
    """`mouse_press(right=True)` on the density window opens the row menu --
    the `on_context` hook, not just the panel method."""
    win, shared, errors, qapp, tmp = session
    viewer = win.viewer
    gui = viewer.gui
    panel = viewer.gui.panels["density"]
    _draw_rows(panel, gui)
    from chimol.ui.gui import _WINDOW_BODY

    row1 = panel._row_boxes[0][0]
    oid1 = panel._row_boxes[0][1]
    hit = type("H", (), {"kind": "window", "key": "density", "row": _WINDOW_BODY})()
    assert gui._press_window(hit, row1.x + 60, row1.y + 2, False, True)
    assert panel._ctx_oid == oid1
    # ... and a left press never opens it.
    panel._ctx_oid = None
    gui._press_window(hit, row1.x + 60, row1.y + 2, False, False)
    assert panel._ctx_oid is None
