"""Named scenes — PyMOL's ``scene``.

A scene bookmarks more than a camera: which objects are enabled, how each is drawn
and what colour it is. That is the difference from ``get_view``/``set_view``, and
it is what lets a scene reproduce a figure rather than just a viewpoint.

Two behaviours here are chimol-specific and are the ones worth pinning, because
both come from the camera being stored *relative to the scene centre* — which
moves when what is drawn changes:

* a view restored **before** the representations is undone by the rebuild that
  follows it, so it goes back last;
* ``view=0`` has to actively hold the camera across the rebuild, or "leave the
  view alone" still moves the picture.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.scenes import SceneStore

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
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _state(view):
    return view._objects[view.get_active_object_id()].state


def _spheres(view) -> int:
    mask = _state(view).ball_mask
    return 0 if mask is None else int(np.count_nonzero(mask))


# --------------------------------------------------------------------------- #
# The store, on its own
# --------------------------------------------------------------------------- #
def test_a_new_store_is_empty():
    store = SceneStore()
    assert store.names() == []
    assert len(store) == 0
    assert "anything" not in store


def test_scenes_keep_the_order_they_were_stored_in(session):
    _, view, _, _ = session
    store = SceneStore()
    for name in ("c", "a", "b"):
        store.store(view, name)
    assert store.names() == ["c", "a", "b"]


def test_storing_over_a_name_keeps_its_position(session):
    _, view, _, _ = session
    store = SceneStore()
    for name in ("a", "b", "c"):
        store.store(view, name)
    store.store(view, "a")
    assert store.names() == ["a", "b", "c"]


def test_stepping_wraps_around(session):
    _, view, _, _ = session
    store = SceneStore()
    for name in ("a", "b"):
        store.store(view, name)
    assert store.step(None, 1) == "a"
    assert store.step("a", 1) == "b"
    assert store.step("b", 1) == "a"
    assert store.step("a", -1) == "b"


def test_stepping_an_empty_store_gives_nothing():
    assert SceneStore().step(None, 1) is None


def test_renaming_keeps_the_position(session):
    _, view, _, _ = session
    store = SceneStore()
    for name in ("a", "b", "c"):
        store.store(view, name)
    assert store.rename("b", "middle")
    assert store.names() == ["a", "middle", "c"]


def test_a_star_deletes_every_scene(session):
    _, view, _, _ = session
    store = SceneStore()
    for name in ("a", "b"):
        store.store(view, name)
    assert store.delete("*")
    assert store.names() == []


# --------------------------------------------------------------------------- #
# Round trip through the command
# --------------------------------------------------------------------------- #
def test_a_scene_restores_the_representation(session):
    cmd, view, _, errors = session
    cmd.do("hide everything")
    cmd.do("show cartoon")
    cmd.do("scene ribbon, store")

    cmd.do("hide everything")
    cmd.do("show spheres, all")
    assert _spheres(view) > 0

    cmd.do("scene ribbon")
    assert errors == []
    assert _state(view).show_cartoon
    assert _spheres(view) == 0


def test_a_scene_restores_the_camera(session):
    cmd, view, _, _ = session
    cmd.do("orient")
    stored = list(view.get_view_state())
    cmd.do("scene here, store")

    cmd.do("turn y, 60")
    cmd.do("zoom")
    assert not np.allclose(view.get_view_state(), stored, atol=1e-5)

    cmd.do("scene here")
    assert np.allclose(view.get_view_state(), stored, atol=1e-5)


def test_the_camera_survives_a_change_of_representation(session):
    """The ordering bug: a view restored first is undone by the rebuild after it.

    chimol stores the camera relative to the scene centre, and that centre moves
    when what is drawn changes -- so the view has to go back *last*.
    """
    cmd, view, _, _ = session
    cmd.do("hide everything")
    cmd.do("show cartoon")
    cmd.do("orient")
    stored = list(view.get_view_state())
    cmd.do("scene ribbon, store")

    cmd.do("hide everything")
    cmd.do("show spheres, all")
    cmd.do("turn x, 90")
    cmd.do("zoom")

    cmd.do("scene ribbon")
    assert _state(view).show_cartoon                       # representation back
    assert np.allclose(view.get_view_state(), stored, atol=1e-5)   # *and* camera


def test_a_scene_restores_colours(session):
    cmd, view, _, _ = session
    cmd.do("spectrum b, blue_red")
    coloured = np.asarray(_state(view).colors_per_atom_override).copy()
    cmd.do("scene painted, store")

    cmd.do("spectrum count, rainbow")
    assert not np.allclose(_state(view).colors_per_atom_override, coloured)

    cmd.do("scene painted")
    assert np.allclose(_state(view).colors_per_atom_override, coloured)


# --------------------------------------------------------------------------- #
# Per-aspect flags -- what makes scenes composable
# --------------------------------------------------------------------------- #
def test_view_zero_leaves_the_camera_alone(session):
    """Even though the rebuild it triggers would otherwise move it."""
    cmd, view, _, _ = session
    cmd.do("hide everything")
    cmd.do("show cartoon")
    cmd.do("scene ribbon, store")

    cmd.do("hide everything")
    cmd.do("show spheres, all")
    cmd.do("turn y, 60")
    cmd.do("zoom")
    current = list(view.get_view_state())

    cmd.do("scene ribbon, recall, view=0")
    assert _state(view).show_cartoon                        # representation did change
    assert np.allclose(view.get_view_state(), current, atol=1e-5)   # camera did not


def test_rep_zero_leaves_the_representation_alone(session):
    cmd, view, _, _ = session
    cmd.do("hide everything")
    cmd.do("show cartoon")
    cmd.do("orient")
    stored = list(view.get_view_state())
    cmd.do("scene ribbon, store")

    cmd.do("hide everything")
    cmd.do("show spheres, all")
    cmd.do("turn y, 45")

    cmd.do("scene ribbon, recall, rep=0")
    assert _spheres(view) > 0                               # still spheres
    assert np.allclose(view.get_view_state(), stored, atol=1e-5)


def test_a_scene_can_carry_only_a_colour_scheme(session):
    """Which is the point of the flags: one scene for the view, another for colour."""
    cmd, view, _, _ = session
    cmd.do("spectrum b, blue_red")
    cmd.do("scene colours, store, view=0, rep=0, active=0")

    scene = cmd._scene_store.get("colours")
    assert scene.view is None
    assert set(next(iter(scene.objects.values()))) == {"color"}


def test_storing_reports_which_aspects_it_captured(session):
    cmd, _, messages, _ = session
    cmd.do("scene partial, store, rep=0, color=0")
    assert "view" in messages[-1] and "rep" not in messages[-1]


# --------------------------------------------------------------------------- #
# Managing them
# --------------------------------------------------------------------------- #
def test_listing_scenes(session):
    cmd, _, messages, _ = session
    cmd.do("scene")
    assert "no scenes stored" in messages[-1]
    cmd.do("scene one, store")
    cmd.do("scene two, store")
    cmd.do("scene")
    assert "one" in messages[-1] and "two" in messages[-1]


def test_auto_steps_to_the_next_scene(session):
    cmd, _, messages, _ = session
    cmd.do("scene one, store")
    cmd.do("scene two, store")
    cmd.do("scene one")
    cmd.do("scene auto")
    assert "'two'" in messages[-1]


def test_deleting_a_scene(session):
    cmd, _, messages, errors = session
    cmd.do("scene gone, store")
    cmd.do("scene gone, delete")
    assert errors == []
    cmd.do("scene gone")
    assert errors and "no scene named" in errors[-1]


def test_recalling_an_unknown_scene_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("scene nope")
    assert errors and "no scene named" in errors[-1]


def test_a_message_is_carried_with_the_scene(session):
    cmd, _, messages, _ = session
    cmd.do("scene noted, store, the ligand pocket")
    cmd.do("scene noted")
    assert "the ligand pocket" in messages[-1]


def test_an_object_that_has_gone_is_reported(session):
    """A scene recalled against a changed session is a common surprise.

    Silence makes it look as though the scene itself was wrong.
    """
    cmd, _, messages, _ = session
    cmd.do("create copy, polymer")
    cmd.do("scene both, store")
    cmd.do("delete copy")
    cmd.do("scene both")
    assert "gone" in messages[-1] and "copy" in messages[-1]
