"""Every object lives in one world frame.

Scene coordinates are ``(xyz - raw_center) * scale`` and ``raw_center`` is
per-object state, so each ``set_structure`` used to compute its own — and two
structures loaded one after the other were both drawn on the origin,
interpenetrating. That is what *"fetch structure on top of another break entire
geom"* was looking at.

PyMOL keeps every object in one frame and aims the camera at all of them. The
**first** object defines the origin; later ones borrow it and land where their
own coordinates put them.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")

from chimol.core.viewer import MolView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _blob(centre, n=40, spread=5.0):
    rng = np.random.default_rng(0)
    return rng.normal(scale=spread, size=(n, 3)) + np.asarray(centre, dtype=float)


def _load(view, points, name=None):
    """Load *points* as a real object, not a placeholder.

    `set_coordinates` on a bare `MolView` leaves its entry marked
    `placeholder`, and `create_object` prunes placeholders -- so building the
    second object would silently delete the first and the test would measure a
    single-object scene while claiming to measure two.
    """
    if name is not None:
        view.create_object(name=name)
    view.set_coordinates(points)
    entry = view.objects[view.get_active_object_id()]
    entry.placeholder = False
    return view.get_active_object_id()


def test_the_first_object_still_defines_the_origin(qapp):
    view = MolView()
    points = _blob((100.0, 0.0, 0.0))
    _load(view, points)

    centre = np.asarray(view._get_active_state().raw_center)
    assert np.allclose(centre, points.mean(0), atol=3.0), centre
    assert np.allclose(
        np.asarray(view._get_active_state().all_atom_coords).mean(0), 0.0, atol=1e-6
    )


def test_a_second_object_borrows_the_frame_rather_than_re_centring(qapp):
    """Both were landing on the origin; the second must land 40 Å away."""
    view = MolView()
    first = _blob((0.0, 0.0, 0.0))
    first_id = _load(view, first)

    second = _blob((40.0, 0.0, 0.0))
    second_id = _load(view, second, name="second")
    assert second_id != first_id

    states = {oid: view.objects[oid].state for oid in (first_id, second_id)}
    centres = [np.asarray(state.raw_center) for state in states.values()]
    assert np.allclose(centres[0], centres[1]), "the two objects disagree on the origin"

    scale = float(view._scale_factor)
    offset = np.asarray(states[second_id].all_atom_coords).mean(0)
    assert abs(offset[0] - 40.0 * scale) < 5.0 * scale, offset
    assert np.allclose(
        np.asarray(states[first_id].all_atom_coords).mean(0), 0.0, atol=1e-6
    )


def test_the_second_objects_radius_is_measured_about_the_shared_centre(qapp):
    """`update_view` frames the camera from the largest object radius.

    Measured about a centre the object no longer uses, that radius is the
    object's own extent -- far too small to reach it -- and the camera clips it
    away.
    """
    view = MolView()
    _load(view, _blob((0.0, 0.0, 0.0), spread=2.0))
    _load(view, _blob((200.0, 0.0, 0.0), spread=2.0), name="far")

    radius = float(view._radius)
    scale = float(view._scale_factor)
    assert radius > 150.0 * scale, radius
