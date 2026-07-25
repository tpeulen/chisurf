"""Tests for the 18-float camera tuple and the framing rule.

Both are parity surfaces: a view tuple has to mean the same thing here as in
PyMOL for a copy-pasted ``set_view`` to reproduce the same picture, and ``zoom``
has to put a molecule of a given size at the same place in front of the camera.

The constants checked here were measured from PyMOL itself:

* ``cmd.get_view()[17]`` is *negative* for the default perspective camera and
  positive once ``orthoscopic`` is on -- the opposite of the intuitive reading.
* ``cmd.zoom()`` settles at ``distance = radius / tan(fov / 2)``, confirmed for
  radii 5/10/20 A at 20 and 45 degrees.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.view_state import (
    DEFAULT_FOV,
    distance_for_radius,
    pack_view_state,
    unpack_view_state,
)


def _rotation(angle_deg: float = 30.0) -> np.ndarray:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# --------------------------------------------------------------------------- #
# Field-of-view sign convention
# --------------------------------------------------------------------------- #
def test_perspective_writes_a_negative_field_of_view():
    view = pack_view_state(np.eye(3), 10.0, [0, 0, 0], 1.0, 100.0, 20.0,
                           orthoscopic=False)
    assert view[17] == pytest.approx(-20.0)


def test_orthoscopic_writes_a_positive_field_of_view():
    view = pack_view_state(np.eye(3), 10.0, [0, 0, 0], 1.0, 100.0, 20.0,
                           orthoscopic=True)
    assert view[17] == pytest.approx(20.0)


@pytest.mark.parametrize("ortho", [False, True])
def test_field_of_view_round_trips_with_its_flag(ortho):
    view = pack_view_state(_rotation(), 42.0, [1, 2, 3], 0.5, 500.0, 35.0,
                           orthoscopic=ortho)
    state = unpack_view_state(view)
    assert state.fov == pytest.approx(35.0)
    assert state.orthoscopic is ortho


def test_a_view_copied_from_pymol_is_read_as_perspective():
    """A real ``cmd.get_view()`` from PyMOL, defaults everywhere.

    Read with the sign inverted this would come back as an orthoscopic camera.
    """
    pymol_view = [
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
        0.0, 0.0, -138.7545623779297,
        7.012499809265137, 47.04399871826172, 34.04500198364258,
        109.39515686035156, 168.1139678955078, -20.0,
    ]
    state = unpack_view_state(pymol_view)
    assert state.orthoscopic is False
    assert state.fov == pytest.approx(20.0)
    assert state.distance == pytest.approx(138.7545623779297)


def test_legacy_tuples_are_not_read_as_orthoscopic():
    """Older chimol layouts always wrote a positive fov and meant nothing by it."""
    legacy = [*np.eye(3).reshape(-1), 30.0, 20.0, 45.0, 0.0, 0.0, 0.0,
              0.1, 1000.0, 45.0]
    state = unpack_view_state(legacy)
    assert state.orthoscopic is False
    assert state.distance == pytest.approx(30.0)


def test_default_field_of_view_matches_pymol():
    assert DEFAULT_FOV == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "radius, fov, expected",
    [
        # Measured from PyMOL: two pseudoatoms at +/-R on the vertical axis,
        # `zoom buffer=0`, then -get_view()[11].
        (5.0, 20.0, 28.3564),
        (5.0, 45.0, 12.0711),
        (10.0, 20.0, 56.7128),
        (10.0, 45.0, 24.1421),
        (20.0, 20.0, 113.4256),
        (20.0, 45.0, 48.2843),
    ],
)
def test_framing_matches_pymol_zoom(radius, fov, expected):
    assert distance_for_radius(radius, fov) == pytest.approx(expected, rel=1e-5)


def test_widening_the_lens_pulls_the_camera_in():
    """Field of view controls perspective, not apparent size."""
    near = distance_for_radius(10.0, 45.0)
    far = distance_for_radius(10.0, 20.0)
    assert near < far


def test_framing_ignores_the_sign_of_the_field_of_view():
    assert distance_for_radius(10.0, -20.0) == pytest.approx(
        distance_for_radius(10.0, 20.0)
    )


def test_degenerate_field_of_view_does_not_divide_by_zero():
    assert distance_for_radius(10.0, 0.0) == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# Rotation, which the sign work must not disturb
# --------------------------------------------------------------------------- #
def test_rotation_survives_the_round_trip():
    rot = _rotation(37.0)
    state = unpack_view_state(pack_view_state(rot, 20.0, [0, 0, 0], 1.0, 100.0))
    assert np.allclose(state.rotation, rot, atol=1e-9)


def test_pymol_keeps_the_camera_basis_in_the_columns():
    """Slots 0-8 are the transpose of chimol's world-to-camera rotation."""
    rot = _rotation(37.0)
    view = pack_view_state(rot, 20.0, [0, 0, 0], 1.0, 100.0)
    assert np.allclose(np.array(view[:9]).reshape(3, 3), rot.T, atol=1e-9)
