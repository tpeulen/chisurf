"""What ``zoom`` and ``reset`` actually put in front of the camera.

Framing is a parity surface: a molecule of a given size has to end up the same
size on screen as it does in PyMOL, or a view tuple copied between the two
programs frames differently even when every number in it agrees.

The reference values here were measured from PyMOL on 148L with
``field_of_view 20`` and ``zoom buffer=0``.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.view_state import (
    distance_for_radius,
    framing_radius,
)

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def view(qapp):
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    v = MolView()
    v.resize(800, 600)
    v.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )
    return v


def _distance(view) -> float:
    """Camera-to-target distance from the packed view tuple."""
    v = view.get_view_state()
    return -v[11] if abs(v[9]) < 1e-9 else v[9]


def _fov(view) -> float:
    return abs(view.get_view_state()[17])


# --------------------------------------------------------------------------- #
# The framing rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("complete", [False, True])
def test_distance_follows_the_field_of_view(view, complete):
    """``d = R / tan(fov/2)``, PyMOL's rule, in both fitting modes."""
    view.zoom(complete=complete)
    radius = view._framing_radius(complete=complete)
    expected = radius / math.tan(math.radians(_fov(view)) / 2.0)
    assert _distance(view) == pytest.approx(expected, rel=1e-6)


def test_reset_frames_the_same_way_as_zoom(view):
    view.zoom()
    zoomed = _distance(view)
    view.turn("y", 40.0)
    view.reset_view()
    assert _distance(view) == pytest.approx(zoomed, rel=1e-6)


def test_turning_the_camera_does_not_change_the_zoom(view):
    """The box is measured in world space, so orientation cannot matter."""
    view.zoom()
    before = _distance(view)
    for axis, angle in (("x", 37.0), ("y", -21.0), ("z", 64.0)):
        view.turn(axis, angle)
    view.zoom()
    assert _distance(view) == pytest.approx(before, rel=1e-9)


def test_complete_pulls_the_camera_back(view):
    """Fitting the sphere cannot be tighter than fitting the box."""
    view.zoom(complete=False)
    box = _distance(view)
    view.zoom(complete=True)
    assert _distance(view) > box


def test_buffer_adds_room(view):
    view.zoom(buffer=0.0)
    tight = _distance(view)
    view.zoom(buffer=10.0)
    assert _distance(view) > tight


# --------------------------------------------------------------------------- #
# What gets fitted
# --------------------------------------------------------------------------- #
def test_zoom_fits_every_atom_not_just_the_trace(view):
    """A CA-only fit reads small: the side chains reaching furthest are omitted.

    148L's all-atom box half-extent is 23.8 A against 22.3 A for the CA trace,
    so fitting the trace would frame the molecule ~7% large and clip side chains.
    """
    all_atoms = framing_radius(view._all_atom_coords)
    trace_only = framing_radius(view._coords)
    assert all_atoms > trace_only

    view.zoom()
    expected = all_atoms / math.tan(math.radians(_fov(view)) / 2.0)
    assert _distance(view) == pytest.approx(expected, rel=1e-6)


def test_a_selection_still_fits_only_the_selection(view):
    """Passing indices must not silently widen to the whole molecule."""
    view.zoom()
    everything = _distance(view)
    view.zoom(list(range(10)))
    assert _distance(view) < everything


# --------------------------------------------------------------------------- #
# Against PyMOL
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "complete, pymol_distance",
    [
        # -get_view()[11] from PyMOL at field_of_view 20.
        (False, 138.755),
        (True, 172.899),
    ],
)
def test_camera_distance_is_within_a_few_percent_of_pymol(view, complete, pymol_distance):
    """Angstrom for Angstrom, allowing PyMOL's representation padding.

    PyMOL measures the extent of what it draws rather than of the atom centres,
    which puts its camera ~3-4% further back on 148L. That padding depends on
    which representations are shown, so it is not modelled here.
    """
    view.zoom(complete=complete)
    scale = _scene_scale(view)
    assert _distance(view) / scale == pytest.approx(pymol_distance, rel=0.05)


def _scene_scale(view) -> float:
    """Scene units per Angstrom, recovered from the stored coordinates.

    MolView works in scaled scene units; the framing rule is scale-free, so the
    comparison with PyMOL has to divide it back out.
    """
    xyz = np.array(
        [
            [float(line[30:38]), float(line[38:46]), float(line[46:54])]
            for line in _PDB_148L.read_text().splitlines()
            if line.startswith(("ATOM", "HETATM"))
        ]
    )
    return framing_radius(view._all_atom_coords) / framing_radius(xyz)


# --------------------------------------------------------------------------- #
# Read from PyMOL's C++, not inferred
# --------------------------------------------------------------------------- #
# layer1/Scene.cpp, SceneWindowSphere:
#     float dist = 2.f * radius / GetFovWidth(G);
#     if (I->Height > I->Width) dist *= (float)I->Height / (float)I->Width;
# with GetFovWidth == 2 * tan(fov * PI / 360), i.e. 2 * tan(fov/2).
# layer3/Executive.cpp, ExecutiveWindowZoom, chooses the radius:
#     inclusive ? ExecutiveGetMaxDistance(...)          // bounding sphere
#               : max(df[0], df[1], df[2]) / 2          // half-extent
#     if (radius < MAX_VDW) radius = MAX_VDW;           // MAX_VDW == 2.5


def test_a_portrait_viewport_pulls_the_camera_back():
    """PyMOL widens the fit when height exceeds width; the fov is vertical."""
    upright = distance_for_radius(10.0, 20.0, aspect=480 / 640)
    landscape = distance_for_radius(10.0, 20.0, aspect=640 / 480)
    assert upright == pytest.approx(landscape * (640 / 480))


def test_a_landscape_viewport_is_not_corrected():
    """Only Height > Width triggers it, per the source."""
    plain = distance_for_radius(10.0, 20.0)
    for aspect in (1.0, 4 / 3, 16 / 9):
        assert distance_for_radius(10.0, 20.0, aspect=aspect) == pytest.approx(plain)


@pytest.mark.parametrize(
    "width, height, pymol_distance",
    [
        # Measured from PyMOL on 148L at field_of_view 20, buffer 0.
        (640, 480, 138.755),
        (480, 640, 185.006),
        (800, 800, 138.755),
        (400, 800, 277.509),
    ],
)
def test_the_aspect_correction_matches_pymol(width, height, pymol_distance):
    """Same molecule, four viewports, against PyMOL's own numbers."""
    # PyMOL's radius on 148L, from its extent: max half-extent plus the ~0.7 A
    # it pads by (see framing_radius's note).
    radius = 24.4662
    assert distance_for_radius(radius, 20.0, aspect=width / height) == pytest.approx(
        pymol_distance, rel=1e-4
    )


def test_a_tiny_fragment_does_not_swallow_the_camera():
    """PyMOL floors the radius at MAX_VDW so one atom is not framed at nothing."""
    from chisurf.plugins.chimol.chimol.renderer.view_state import MIN_FRAMING_RADIUS

    single = np.zeros((1, 3))
    assert framing_radius(single) == pytest.approx(MIN_FRAMING_RADIUS)
    # And the floor scales with the scene, since chimol does not work in Angstrom.
    assert framing_radius(single, scale=10.0) == pytest.approx(
        MIN_FRAMING_RADIUS * 10.0
    )


def test_the_floor_does_not_disturb_a_real_molecule():
    xyz = np.array([[0.0, 0.0, 0.0], [0.0, 40.0, 0.0]])
    assert framing_radius(xyz) == pytest.approx(20.0)
