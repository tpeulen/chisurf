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

from chimol.core.view_state import distance_for_radius, framing_centre, framing_radius

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
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

    v = MolView()
    v.resize(800, 600)
    # The *renderer* is given a real landscape viewport, not left at whatever
    # size Qt gives an unshown widget. Without this the fixture measures the
    # backend's default geometry rather than the framing rule: the OpenGL widget
    # reports 100x30 (a scene column of 1 pixel, which the aspect guard reads as
    # "no window") while the WebGPU one reports 640x480 (portrait once the panel
    # takes its column, so PyMOL's portrait correction fires). Same code, two
    # different answers, neither of them about framing.
    v.renderer.resize(1000, 600)
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
def test_camera_distance_matches_pymol(view, complete, pymol_distance):
    """Angstrom for Angstrom, now that the centroid box is accounted for."""
    view.zoom(complete=complete)
    scale = _scene_scale(view)
    assert _distance(view) / scale == pytest.approx(pymol_distance, rel=0.01)


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
    from chimol.core.view_state import MIN_FRAMING_RADIUS

    single = np.zeros((1, 3))
    assert framing_radius(single) == pytest.approx(MIN_FRAMING_RADIUS)
    # And the floor scales with the scene, since chimol does not work in Angstrom.
    assert framing_radius(single, scale=10.0) == pytest.approx(
        MIN_FRAMING_RADIUS * 10.0
    )


def test_the_floor_does_not_disturb_a_real_molecule():
    xyz = np.array([[0.0, 0.0, 0.0], [0.0, 40.0, 0.0]])
    assert framing_radius(xyz) == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# The box is symmetric about the centroid, not about itself
# --------------------------------------------------------------------------- #
# ExecutiveWindowZoom asks ExecutiveGetExtent for a *weighted* extent, and that
# flag makes it average the atom coordinates and rebuild the box symmetrically
# about that average:
#     op2.v1 /= op2.i1;  f1 = op2.v1[a] - op.v1[a];  f2 = op.v2[a] - op2.v1[a];
#     fmx = max(f1, f2);  op.v1[a] = op2.v1[a] - fmx;  op.v2[a] = op2.v1[a] + fmx;
#
# This accounted for what had looked like a mystery constant: a radius +0.70 A
# over the reported extent on globular 148L, but +11.65 A on the long coiled coil
# of 1DG3, and exactly zero on symmetric pseudoatom pairs. It is not padding at
# all -- it is the box being re-centred on where the atoms actually are.


def test_the_centre_is_the_centroid():
    """Lopsided mass: the centroid is nowhere near the box centre."""
    pts = np.array([[0.0, 0.0, 0.0]] * 9 + [[90.0, 0.0, 0.0]])
    assert framing_centre(pts)[0] == pytest.approx(9.0)
    assert (pts.min(axis=0)[0] + pts.max(axis=0)[0]) / 2 == pytest.approx(45.0)


def test_lopsided_mass_widens_the_fit():
    """The box stays symmetric about the centroid, so it has to grow."""
    pts = np.array([[0.0, 0.0, 0.0]] * 9 + [[90.0, 0.0, 0.0]])
    # Centroid at x = 9, far atom 81 away: the half-width is 81, not 45.
    assert framing_radius(pts) == pytest.approx(81.0)


def test_a_symmetric_object_is_unaffected():
    """Which is exactly why pseudoatom pairs showed no residual."""
    pair = np.array([[0.0, -30.0, 0.0], [0.0, 30.0, 0.0]])
    assert framing_radius(pair) == pytest.approx(30.0)


def test_an_empty_set_has_no_centre():
    assert np.allclose(framing_centre(np.zeros((0, 3))), 0.0)


def _pdb_coords(path) -> np.ndarray:
    return np.array(
        [
            [float(line[30:38]), float(line[38:46]), float(line[46:54])]
            for line in path.read_text().splitlines()
            if line.startswith(("ATOM", "HETATM"))
        ]
    )


def test_the_radius_now_matches_pymol_exactly():
    """148L, against PyMOL's own zoom -- previously off by 0.70 A."""
    xyz = _pdb_coords(_PDB_148L)
    assert framing_radius(xyz) == pytest.approx(24.4662, abs=1e-3)
    assert framing_radius(xyz, complete=True) == pytest.approx(30.487, abs=1e-3)


# --------------------------------------------------------------------------- #
# The portrait correction, and the viewport that is not one
# --------------------------------------------------------------------------- #
def test_a_widget_that_was_never_laid_out_frames_square(view):
    """An aspect measured from a 1-pixel column is not a measurement.

    A never-shown ``MolView`` is 100x30 with a 220-pixel panel column, so the
    scene width comes out negative and is clamped to **1**. Read as a real
    viewport that says the window is thirty times taller than it is wide, and
    PyMOL's portrait correction then puts the camera thirty times too far away
    -- which is exactly what the five framing tests above were measuring before
    this guard existed. The correction has nothing to correct until there is a
    window.
    """
    renderer = view.renderer
    # Constructed, not hoped for. This used to rely on the OpenGL widget
    # happening to report 100x30 before layout -- which the WebGPU widget does
    # not, so the test silently stopped covering the guard rather than failing.
    #
    # Docked explicitly, for the same reason and after the same kind of silent
    # miss: the panel now starts **floating**, and a floating panel takes no
    # column at all (`scene_width` says so). So the resize below left a full
    # 221-pixel scene, the degenerate viewport never happened, and the test was
    # asserting against a state it no longer built. Only a docked panel can
    # squeeze the scene to nothing, which is the case the guard is for.
    renderer._internal_gui.docked = True
    renderer.resize(int(renderer._internal_gui.column_width) + 1, 30)
    assert renderer.scene_width() < renderer._MIN_MEASURABLE_SCENE, (
        "the degenerate viewport was not reproduced"
    )
    assert renderer._aspect() == 1.0


def test_a_real_portrait_viewport_still_corrects(view):
    """The guard must not disable the correction it is protecting."""
    renderer = view.renderer
    renderer.resize(400, 900)
    if renderer.scene_width() < renderer._MIN_MEASURABLE_SCENE:
        pytest.skip("the panel column leaves no scene at this size")
    assert renderer._aspect() < 1.0


def test_a_portrait_resize_re_derives_the_distance(view):
    """Nothing else re-derives it: a resize triggers no rebuild.

    The correction only applies to a portrait viewport, so the distance that
    framed a molecule in a wide window is wrong in a tall one and the molecule
    spills off the sides. Applied once at whatever shape the window had when the
    structure was framed, it is wrong for every shape after that.
    """
    renderer = view.renderer
    renderer.resize(900, 600)
    view.zoom()
    landscape = _distance(view)
    assert renderer._aspect() > 1.0

    renderer.resize(400, 900)
    renderer.resize_viewport(400, 900)
    assert renderer._aspect() < 1.0
    assert _distance(view) > landscape, "the camera did not pull back"

    renderer.resize(900, 600)
    renderer.resize_viewport(900, 600)
    assert _distance(view) == pytest.approx(landscape, rel=1e-9), (
        "returning to the original shape did not restore the original framing"
    )


def test_a_resize_that_keeps_the_shape_costs_nothing(view):
    """Same aspect, same distance -- and no work done to find that out."""
    renderer = view.renderer
    renderer.resize(900, 600)
    view.zoom()
    before = _distance(view)
    renderer.resize_viewport(900, 600)
    assert _distance(view) == pytest.approx(before, rel=1e-12)


def test_a_resize_preserves_a_hand_zoomed_view(view):
    """The wheel moves the camera without changing what was framed.

    So the resize correction has to *scale* the distance it finds, not recompute
    it from the framed radius -- recomputing would snap a hand-zoomed view back
    to wherever the last `zoom` left it, which is the same class of bug the
    framing work exists to fix.
    """
    renderer = view.renderer
    renderer.resize(900, 600)
    view.zoom()
    renderer._distance *= 0.25          # what a few scroll clicks do
    hand_zoomed = _distance(view)

    renderer.resize(400, 900)
    renderer.resize_viewport(400, 900)
    renderer.resize(900, 600)
    renderer.resize_viewport(900, 600)
    assert _distance(view) == pytest.approx(hand_zoomed, rel=1e-9), (
        "the round trip discarded the hand-zoomed distance"
    )
