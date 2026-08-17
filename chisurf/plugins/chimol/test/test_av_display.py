"""An accessible volume is a density object.

The AV's dye cloud is handed to the same volume machinery a map gets: the
Density panel contours it, its level/alpha/quality controls apply, the
object menu's colour entries recolour its contour levels, and the default
representation is the surface at the binary grid's 0.5 envelope. What the
volume path cannot draw -- the density-weighted mean, the point a FRET
distance attaches to -- is the marker.

Every assertion here is a defect that existed:

* the grid arrived from the imp-bff backend **x/z-swapped** (correlation
  +1.0000 under transpose (2,1,0) against the AV's own voxelized points,
  +0.35 as delivered) and the mesh landed 13.6 A off its cloud;
* the composition filter dropped AV objects entirely (no coords, no volume)
  -- the "no AV displayed" report;
* `color` resolved selections to atom masks only, so a density object could
  not be recoloured from the object menu at all.
"""

from __future__ import annotations

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
def session(qapp):
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
    yield win, shared, errors, qapp
    shared.do("delete all")
    win.close()


def _euler(verts: np.ndarray, faces: np.ndarray) -> int:
    edges = set()
    for a, b, c in faces:
        for one, two in ((a, b), (b, c), (c, a)):
            edges.add((min(one, two), max(one, two)))
    return int(verts.shape[0] - len(edges) + faces.shape[0])


def _av_entry(viewer):
    av_ids = [
        oid for oid, entry in viewer._objects.items()
        if getattr(entry.state, "av", None) is not None
    ]
    assert av_ids, "no AV object in the viewer"
    return av_ids[0], viewer._objects[av_ids[0]]



def _fresh_av(session):
    """Reset the scene to one structure plus one dye -- tests are order-free.

    Every test then measures the same object: a Cy5 on 148L's E119 CB, as a
    density object.
    """
    win, shared, errors, qapp = session
    shared.do("delete all")
    shared.do(f"load {PDB}")
    errors.clear()
    shared.do("add_dye resi 119 and name CB, Cy5")
    errors.clear()


def test_the_av_is_a_density_object_with_a_surface_level(session):
    _fresh_av(session)
    win, shared, errors, qapp = session
    assert errors == [], errors[:2]
    viewer = win.viewer
    oid, entry = _av_entry(viewer)
    state = entry.state
    assert state.volume is not None, "the AV's grid is not on the volume path"
    assert state.volume.shape == tuple(
        int(n) for n in np.asarray(state.av.density).shape
    )
    levels = state.volume_levels
    assert levels and levels[0]["style"] == "surface"
    assert abs(float(levels[0]["level"]) - 0.5) < 1e-9, (
        "a binary grid contours at its 0.5 envelope"
    )


def test_the_density_panel_edits_the_av(session):
    _fresh_av(session)
    """The panel a map gets is the panel a dye gets."""
    win, shared, errors, qapp = session
    viewer = win.viewer
    from chimol.plugins.density.model import VolumeViewModel

    model = VolumeViewModel(viewer)
    grid = model._grid()
    assert grid is not None, "the panel does not see the AV"
    assert "E119_CB" in model.summary()
    changed = viewer.set_volume_levels(
        [{"level": 0.5, "color": (0.1, 0.9, 0.1, 0.4), "style": "surface"}],
        object_id=model._object_id,
    )
    assert changed, "the panel's level setter refused the AV"


def test_the_contour_is_closed_and_centered_on_the_cloud(session):
    _fresh_av(session)
    from chimol.plugins.labelling import av as avmod

    if "imp-bff" not in avmod.available_backends():
        pytest.skip("imp-bff not importable here")
    win, shared, errors, qapp = session
    viewer = win.viewer
    oid, entry = _av_entry(viewer)
    meshes = [
        o for o in viewer._scene.objects
        if o.id.startswith(f"{oid}:volume_") and o.geometry.kind == "mesh"
    ]
    assert meshes, "no contour in the composed scene"
    shell = meshes[0]
    verts = np.asarray(shell.geometry.positions)
    faces = np.asarray(shell.geometry.indices)
    assert faces.shape[0] > 100
    assert _euler(verts, faces) == 2, "the shell is not closed"
    assert shell.render_mode == "transparent"

    # Centered on its own cloud: the axis-swapped grid landed 11.5 A off.
    av = entry.state.av
    with viewer._activate_object(oid):
        mean_scene = viewer._transform_world_coords_to_scene(
            np.asarray(av.mean_position, dtype=float)
        )
    delta = float(np.linalg.norm(verts.mean(axis=0) - mean_scene)) / 10.0
    assert delta < 3.0, f"the shell sits {delta:.1f} A off its cloud's mean"

    # ... and reaches the attachment atom: the residue is stripped, so the
    # dye can hug its own site.
    records = avmod._cached_pdb_records(str(PDB))
    cb_world = np.array([
        r[3:6] for r in records
        if r[0] == "E" and r[1] == 119 and r[2] == "CB"
    ][0])
    with viewer._activate_object(oid):
        cb_scene = viewer._transform_world_coords_to_scene(cb_world)
    nearest = float(np.linalg.norm(verts - cb_scene, axis=1).min()) / 10.0
    assert nearest < 10.0, f"shell stops {nearest:.1f} A from the attachment atom"


def test_the_mean_position_is_its_own_sphere_object(session):
    """``av_<position>_mp``: one bead at the mean, addressable like any object.

    The marker used to be a scene-only sprite -- visible, but nothing could
    select it, measure to it or colour it. As an object it is all three, and
    `distance av_X_mp, av_Y_mp` connects two of them.
    """
    _fresh_av(session)
    win, shared, errors, qapp = session
    viewer = win.viewer
    oid, entry = _av_entry(viewer)
    mp_id = entry.state.av_mean_object_id
    assert mp_id and mp_id in viewer._objects, "no mean-position object"
    mp_entry = viewer._objects[mp_id]
    assert mp_entry.name == "av_E119_CB_mp"
    # The bead sits on the density-weighted mean, in the scene's frame --
    # the same frame the structure is drawn in (a single-point object
    # centres on itself unless it adopts the structure's).
    av = entry.state.av
    with viewer._activate_object(mp_id):
        mean_scene = viewer._transform_world_coords_to_scene(
            np.asarray(av.mean_position, dtype=float)
        )
    bead = np.asarray(mp_entry.state.all_atom_coords, dtype=float).reshape(1, 3)
    assert np.linalg.norm(bead[0] - mean_scene) < 1e-6
    # Sphere representation, and nothing else.
    assert mp_entry.state.show_atoms and not mp_entry.state.show_cartoon
    # The wizard can resolve the dye cloud through the bead.
    assert mp_entry.state.mp_for_av == oid


def test_the_object_menu_colors_the_av(session):
    _fresh_av(session)
    """`color <name>, <object>` -- the C menu's entry -- recolours the dye."""
    win, shared, errors, qapp = session
    viewer = win.viewer
    oid, entry = _av_entry(viewer)
    shared.do("color red, E119_CB")
    assert errors == [], errors[:2]
    color = entry.state.volume_levels[0]["color"]
    assert tuple(round(float(c), 3) for c in color[:3]) == (1.0, 0.0, 0.0)
    # The panel's view agrees -- same levels, same object.
    from chimol.plugins.density.model import VolumeViewModel

    model = VolumeViewModel(viewer)
    assert model._grid() is not None
    assert model._object_id == oid


def test_the_numpy_backend_also_becomes_a_density(session, monkeypatch):
    """The browser backend (no physics library) draws the same way."""
    _fresh_av(session)
    from chimol.plugins.labelling import av as avmod

    if "numpy" not in avmod.available_backends():
        pytest.skip("numpy backend missing")
    real_compute = avmod.compute_av

    def _numpy_compute(pdb_path, params, **kwargs):
        kwargs["backend"] = "numpy"
        return real_compute(pdb_path, params, **kwargs)

    monkeypatch.setattr(avmod, "compute_av", _numpy_compute)
    win, shared, errors, qapp = session
    shared.do("add_dye resi 44 and name CB, Cy5")
    assert errors == [], errors[:2]
    viewer = win.viewer
    oid = [
        o for o, e in viewer._objects.items()
        if getattr(e.state, "av", None) is not None
    ][-1]
    state = viewer._objects[oid].state
    assert state.volume is not None
    assert min(state.volume.shape) >= 2
    meshes = [
        o for o in viewer._scene.objects
        if o.id.startswith(f"{oid}:volume_") and o.geometry.kind == "mesh"
    ]
    assert meshes, "the numpy-backend AV drew no contour"
