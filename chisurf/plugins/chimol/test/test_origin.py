"""The rotation origin -- PyMOL ``origin``.

Rotating about a chosen atom is how you look at a binding site: the thing you care
about stays put on screen while everything else swings around it. That needs the
pivot to be separable from the centre of the view, which means carrying **both**
points PyMOL's view tuple defines -- slots 12-14 for the pivot and slots 9-11 for
the camera-space offset. A camera that keeps only one can frame and orbit, and
nothing else.

``ExecutiveOrigin`` always passes ``preserve=1``, so moving the origin must not
move the picture. That is the property most worth pinning: it is invisible, and a
wrong implementation looks like a working one until someone rotates.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.core.camera.view_state import pack_view_state, unpack_view_state

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import Viewer

    view = Viewer()
    view.resize(600, 400)
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def refresh_objects(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    if view.renderer is None or not hasattr(view.renderer, "_build_matrices"):
        pytest.skip("no matrix-capable renderer in this environment")
    return cmd, view, messages, errors


def _mvp(view) -> np.ndarray:
    """Return the current model-view-projection matrix as plain numbers."""
    matrix, _ = view.renderer._build_matrices()
    return np.array(matrix.data(), dtype=float).reshape(4, 4)


def _project(view, world: np.ndarray) -> np.ndarray:
    """Project a scene-space point to normalised device coordinates."""
    mvp = _mvp(view).T
    clip = mvp @ np.array([world[0], world[1], world[2], 1.0])
    return clip[:2] / clip[3]


def _ligand_centre(view) -> np.ndarray:
    names = np.char.strip(view._atoms["res_name"].astype(str))
    return np.asarray(view._atoms["xyz"], dtype=float)[names == "NAG"].mean(axis=0)


# --------------------------------------------------------------------------- #
# The invisible property
# --------------------------------------------------------------------------- #
def test_moving_the_origin_does_not_move_the_picture(session):
    """`preserve=1`: the pivot changes, the view compensates, nothing appears to happen."""
    cmd, view, _, errors = session
    before = _mvp(view)
    cmd.do("origin resn NAG")
    assert errors == []
    assert np.allclose(before, _mvp(view), atol=1e-4)


def test_the_compensation_lands_in_slots_nine_to_eleven(session):
    """Which is where PyMOL puts it, and why the tuple carries two points."""
    cmd, view, _, _ = session
    assert np.allclose(view.get_view_state()[9:11], 0.0)
    cmd.do("origin resn NAG")
    assert not np.allclose(view.get_view_state()[9:11], 0.0)


def test_the_pivot_lands_in_slots_twelve_to_fourteen(session):
    cmd, view, _, _ = session
    cmd.do("origin resn NAG")
    pivot = view.get_rotation_origin()
    scene = view._transform_world_coords_to_scene(
        np.asarray(pivot, dtype=float).reshape(1, 3)
    ).reshape(3)
    assert np.allclose(view.get_view_state()[12:15], scene, atol=1e-4)


# --------------------------------------------------------------------------- #
# What it is for
# --------------------------------------------------------------------------- #
def test_rotation_then_pivots_about_the_chosen_point(session):
    """The point of the command: the chosen atom holds its place on screen."""
    cmd, view, _, _ = session
    centre = _ligand_centre(view)
    cmd.do("origin resn NAG")
    scene = view._transform_world_coords_to_scene(centre.reshape(1, 3)).reshape(3)

    before = _project(view, scene)
    cmd.do("turn y, 40")
    assert np.allclose(before, _project(view, scene), atol=5e-3)


def test_without_an_origin_the_chosen_point_swings_away(session):
    """The control: rotation about the default centre moves the ligand."""
    cmd, view, _, _ = session
    centre = _ligand_centre(view)
    scene = view._transform_world_coords_to_scene(centre.reshape(1, 3)).reshape(3)

    before = _project(view, scene)
    cmd.do("turn y, 40")
    assert not np.allclose(before, _project(view, scene), atol=5e-3)


def test_the_pivot_is_the_selection_centroid(session):
    """`ExecutiveOrigin` averages a *weighted* extent, which is the centroid."""
    cmd, view, _, _ = session
    cmd.do("origin resn NAG")
    assert np.allclose(view.get_rotation_origin(), _ligand_centre(view), atol=1e-3)


# --------------------------------------------------------------------------- #
# Arguments
# --------------------------------------------------------------------------- #
def test_an_explicit_position(session):
    cmd, view, _, errors = session
    cmd.do("origin position=[1, 2, 3]")
    assert errors == []
    assert np.allclose(view.get_rotation_origin(), [1.0, 2.0, 3.0], atol=1e-3)


@pytest.mark.parametrize("spelling", ["[1,2,3]", "1 2 3", "[1, 2, 3]"])
def test_position_spellings(session, spelling):
    cmd, view, _, errors = session
    cmd.do(f"origin position={spelling}")
    assert errors == []
    assert np.allclose(view.get_rotation_origin(), [1.0, 2.0, 3.0], atol=1e-3)


def test_a_position_is_in_angstrom_not_scene_units(session):
    """The viewer scales by ten; a coordinate argument must not be scaled twice."""
    cmd, view, _, _ = session
    scale = float(getattr(view, "_scale_factor", 1.0) or 1.0)
    assert scale != 1.0, "this test is only meaningful when the viewer scales"
    cmd.do("origin position=[10, 0, 0]")
    assert np.allclose(view.get_rotation_origin(), [10.0, 0.0, 0.0], atol=1e-3)


def test_a_position_overrides_a_selection(session):
    """PyMOL blanks the selection when a position is given."""
    cmd, view, _, _ = session
    cmd.do("origin resn NAG, position=[1, 2, 3]")
    assert np.allclose(view.get_rotation_origin(), [1.0, 2.0, 3.0], atol=1e-3)


def test_no_arguments_pivots_about_everything(session):
    """PyMOL's default selection is `all`."""
    cmd, view, _, errors = session
    cmd.do("origin resn NAG")
    cmd.do("origin")
    assert errors == []
    everything = np.asarray(view._atoms["xyz"], dtype=float).mean(axis=0)
    assert np.allclose(view.get_rotation_origin(), everything, atol=1e-3)


def test_an_empty_selection_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("origin resn ZZZ")
    assert errors and "matched no atoms" in errors[-1]


def test_a_malformed_position_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("origin position=[1, 2]")
    assert errors and "three numbers" in errors[-1]


# --------------------------------------------------------------------------- #
# Framing resets the pivot
# --------------------------------------------------------------------------- #
def test_zoom_recentres_the_view(session):
    """PyMOL's framing resets slots 9-11, so an old offset must not survive it."""
    cmd, view, _, _ = session
    cmd.do("origin resn NAG")
    assert not np.allclose(view.get_view_state()[9:11], 0.0)
    cmd.do("zoom")
    assert np.allclose(view.get_view_state()[9:11], 0.0)


def test_reset_recentres_the_view(session):
    cmd, view, _, _ = session
    cmd.do("origin resn NAG")
    cmd.do("reset")
    assert np.allclose(view.get_view_state()[9:11], 0.0)


# --------------------------------------------------------------------------- #
# The tuple
# --------------------------------------------------------------------------- #
def test_the_view_tuple_round_trips_with_an_offset(session):
    """A saved view has to restore the pivot as well as the picture."""
    cmd, view, _, _ = session
    cmd.do("origin resn NAG")
    saved = list(view.get_view_state())
    picture = _mvp(view)

    cmd.do("reset")
    view.set_view_state(saved)

    assert np.allclose(view.get_view_state(), saved, atol=1e-5)
    assert np.allclose(picture, _mvp(view), atol=1e-4)


# --------------------------------------------------------------------------- #
# Layout discrimination -- the trap the offset introduces
# --------------------------------------------------------------------------- #
def test_a_pymol_tuple_with_an_offset_is_not_read_as_a_legacy_one():
    """Discriminating on "slot 9 is zero" breaks the moment an offset exists.

    Both older chimol layouts put a positive distance in slot 9, so a PyMOL tuple
    with a non-zero camera-space x offset used to be misread as one of them --
    silently, and as a completely different camera.
    """
    packed = pack_view_state(
        np.eye(3), 100.0, [1.0, 2.0, 3.0], 1.0, 500.0,
        fov=20.0, shift=[-66.0, 18.0, 0.0],
    )
    state = unpack_view_state(packed)
    assert np.isclose(state.distance, 100.0)
    assert np.allclose(state.target, [1.0, 2.0, 3.0])
    assert np.allclose(state.shift[:2], [-66.0, 18.0])


def test_a_zero_offset_still_packs_as_pymol_does():
    packed = pack_view_state(np.eye(3), 100.0, [0.0, 0.0, 0.0], 1.0, 500.0)
    assert packed[9:12] == [0.0, 0.0, -100.0]


def test_the_offset_round_trips_through_the_tuple():
    for shift in ([0.0, 0.0, 0.0], [5.0, -3.0, 0.0], [-66.075, 17.942, 0.0]):
        packed = pack_view_state(
            np.eye(3), 42.0, [1.0, 2.0, 3.0], 1.0, 500.0, shift=shift
        )
        state = unpack_view_state(packed)
        again = pack_view_state(
            state.rotation, state.distance, state.target, state.near, state.far,
            state.fov, state.orthoscopic, shift=state.shift,
        )
        assert np.allclose(packed, again, atol=1e-9)


def test_the_older_chimol_layouts_still_load():
    """Projects and scripts carry them, so the offset must not break them."""
    matrix_form = [*np.eye(3).reshape(-1), 50.0, 0.0, 0.0, 1.0, 2.0, 3.0, 1.0, 500.0, 20.0]
    state = unpack_view_state(matrix_form)
    assert np.isclose(state.distance, 50.0)
    assert np.allclose(state.shift, 0.0)

    angle_form = [*np.eye(3).reshape(-1), 50.0, 20.0, 45.0, 0.0, 0.0, 0.0, 1.0, 500.0, 20.0]
    state = unpack_view_state(angle_form)
    assert np.isclose(state.distance, 50.0)
    assert not np.allclose(state.rotation, np.eye(3))


def test_the_one_ambiguous_corner_is_documented_and_resolved_toward_pymol():
    """An identity rotation with a negative slot 11 could be either format.

    Nothing in the eighteen floats distinguishes a PyMOL view that happens not to
    be rotated from a legacy angle tuple with a negative azimuth. PyMOL
    compatibility decides it; a legacy azimuth is periodic, so writing 315 instead
    of -45 recovers such a view.
    """
    ambiguous = [*np.eye(3).reshape(-1), 50.0, 20.0, -45.0, 0.0, 0.0, 0.0, 1.0, 500.0, 20.0]
    state = unpack_view_state(ambiguous)
    assert np.isclose(state.distance, 45.0)          # read as PyMOL
    assert np.allclose(state.rotation, np.eye(3))

    # The same view written with a positive azimuth still loads as legacy.
    unambiguous = [*np.eye(3).reshape(-1), 50.0, 20.0, 315.0, 0.0, 0.0, 0.0, 1.0, 500.0, 20.0]
    assert np.isclose(unpack_view_state(unambiguous).distance, 50.0)
