"""Defects that only a rendered image shows.

Every one of these passed its construction test, ran without an error and
produced the wrong picture. They share a shape: *two* arrays describe the same
thing, a command writes one of them, and whatever reads the other keeps quietly
drawing the old answer.

* ``spectrum`` writes per-*atom* colours; the cartoon and the trace read
  per-*residue* ones. ``spectrum count, rainbow`` therefore left the cartoon
  showing the load-time blue-to-orange gradient -- a picture with no green,
  cyan or yellow anywhere in it, and no error to say so;
* the sequence strip keeps a third copy, refreshed by ``color`` and not by
  ``spectrum``, so the letters and the ribbon disagreed about a residue's
  colour;
* ``nonbonded_size`` shrinks PyMOL's *nonbonded* atoms -- waters, free ions.
  Applying it to everything not in the polymer shrank bonded ligands to a
  quarter of their van-der-Waals radius, and ``show spheres, organic`` came out
  as a scatter of dots;
* the default layout asked for the 3D view and the side panels in a 3:1 split
  by writing ``sizes: [3, 1]``. QSplitter reads pixels, so the viewport got its
  minimum width -- about 40% of the window rather than 75%.

The assertions are all numbers taken off the rendered arrays rather than
opinions about how it looks.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_DATA = pathlib.Path(__file__).resolve().parents[4] / "test" / "data"
_PDB = _DATA / "atomic_coordinates" / "pdb_files" / "148l.pdb"
_SOLVATED = _DATA / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _window(qapp, path):
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(1200, 800)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win.load_structure_from_path(path)
    for _ in range(20):
        qapp.processEvents()

    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)
    return win, shared


@pytest.fixture
def lysozyme(qapp):
    win, shared = _window(qapp, _PDB)
    yield win, shared, qapp
    win.close()


def _geometry_colors(viewer):
    """Every scene geometry's vertex colours, concatenated."""
    scene = viewer.get_current_scene()
    out = []
    for obj in scene.objects:
        colors = getattr(obj.geometry, "colors", None)
        if colors is None:
            continue
        arr = np.asarray(colors, dtype=float)
        out.append(arr.reshape(-1, arr.shape[-1])[:, :3])
    return np.concatenate(out) if out else np.zeros((0, 3))


# --------------------------------------------------------------------------- #
# spectrum has to reach the cartoon
# --------------------------------------------------------------------------- #
def test_a_rainbow_cartoon_actually_contains_green(lysozyme):
    """Blue and red alone are a two-colour ramp, not a rainbow.

    Green is the tell: it is the middle of the palette and it is the one colour
    the load-time gradient cannot produce, so its presence proves the per-atom
    override reached the mesh.
    """
    win, shared, qapp = lysozyme
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    shared.do("spectrum count, rainbow, polymer")
    for _ in range(10):
        qapp.processEvents()

    colors = _geometry_colors(win.viewer)
    assert colors.size, "the cartoon should have produced geometry"
    green = (colors[:, 1] > colors[:, 0] + 0.2) & (colors[:, 1] > colors[:, 2] + 0.2)
    assert green.any(), "no green vertex: the ramp never reached the cartoon"


def test_a_rainbow_spans_all_three_channels(lysozyme):
    """The stale gradient pinned G near 0.5; a rainbow drives it to full."""
    win, shared, qapp = lysozyme
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    shared.do("spectrum count, rainbow, polymer")
    for _ in range(10):
        qapp.processEvents()

    colors = _geometry_colors(win.viewer)
    # Occlusion is multiplied into the vertex colours, so the maxima sit below
    # 1.0; what matters is that green gets as bright as red and blue do.
    assert colors[:, 1].max() > 0.7, (
        f"green never brightens (max {colors[:, 1].max():.2f}) -- "
        "the per-residue array is still the load-time one"
    )


def test_the_per_atom_override_projects_onto_residues(lysozyme):
    """The projection itself, without the renderer in the way."""
    win, shared, qapp = lysozyme
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    shared.do("spectrum count, rainbow, polymer")
    for _ in range(10):
        qapp.processEvents()

    viewer = win.viewer
    n_res = len(viewer._residue_ids)
    projected = viewer._ca_rgba(n_res)
    assert projected is not None
    assert projected.shape == (n_res, 4)
    assert projected[:, 1].max() > 0.9, "green is missing from the residue colours"
    # A ramp, not a constant: consecutive residues differ.
    assert np.abs(np.diff(projected[:, :3], axis=0)).sum() > 1.0


def test_no_override_leaves_the_residue_colours_alone(lysozyme):
    """The projection must be inert when nothing has been overridden.

    Otherwise it would overwrite ``by_chain`` and every other colour mode with
    a default, which is the same class of bug pointed the other way.
    """
    win, shared, qapp = lysozyme
    for _ in range(5):
        qapp.processEvents()
    viewer = win.viewer
    viewer._colors_per_atom_override = None
    assert viewer._ca_rgba(len(viewer._residue_ids)) is None


def test_colouring_one_residue_leaves_the_others_alone(qapp):
    """A *partial* per-atom override must not flatten the rest of the cartoon.

    The override is normally partial -- ``color red, resi 4`` touches one
    residue -- and the projection used to hand every untouched residue the base
    colour, which the caller then assigned over the whole array. One named
    residue therefore destroyed the load-time gradient everywhere else.
    """
    win, shared = _window(qapp, _SOLVATED)
    try:
        viewer = win.viewer
        before = np.asarray(viewer._colors_per_ca, dtype=float).copy()
        assert np.abs(np.diff(before[:, :3], axis=0)).sum() > 0.1, (
            "the fixture should load with a gradient to destroy"
        )

        shared.do("color red, resi 4")
        for _ in range(10):
            qapp.processEvents()

        after = np.asarray(viewer._colors_per_ca, dtype=float)
        i_red = int(np.flatnonzero(np.asarray(viewer._residue_ids) == 4)[0])
        assert after[i_red, 0] > 0.9 and after[i_red, 1] < 0.1, (
            "the residue that was named is not red"
        )
        others = np.ones(after.shape[0], dtype=bool)
        others[i_red] = False
        assert np.allclose(after[others], before[others]), (
            "colouring one residue changed the colour of the others"
        )
    finally:
        win.close()


def test_an_untouched_residue_abstains_from_the_projection(qapp):
    """The projection reports "no colour" as NaN, not as the base colour.

    That is what lets the caller blend on the finite mask; a fallback colour
    here is indistinguishable from a residue the user really did paint in the
    base colour.
    """
    win, shared = _window(qapp, _SOLVATED)
    try:
        viewer = win.viewer
        shared.do("color red, resi 4")
        for _ in range(10):
            qapp.processEvents()

        projected = viewer._ca_rgba(len(viewer._residue_ids))
        assert projected is not None
        finite = np.all(np.isfinite(projected), axis=1)
        i_red = int(np.flatnonzero(np.asarray(viewer._residue_ids) == 4)[0])
        assert finite[i_red], "the residue that was coloured has no colour"
        assert not finite[np.arange(len(finite)) != i_red].any(), (
            "an untouched residue was given a colour instead of abstaining"
        )
    finally:
        win.close()


def test_spectrum_refreshes_the_sequence_strip(lysozyme):
    """The letters and the ribbon are two views of one colouring."""
    win, shared, qapp = lysozyme
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    for _ in range(10):
        qapp.processEvents()

    def strip_colors():
        # The in-viewport strip, not the deleted `seq_list` dock: one
        # `SequenceRow` per chain, each carrying the per-residue colours the
        # strip paints. Flattened, so the comparison is the same one as before
        # -- "did the colouring change" -- over the same numbers.
        win.sync_internal_gui()
        gui = win.viewer.gui
        # Scaled to 0-255. `SequenceRow.colors` is float 0-1 where the dock's
        # `QColor.getRgb()` was an int triple, and the green test below is
        # written in the latter -- left in those units so the threshold still
        # means what it says rather than becoming 0.16.
        return [
            tuple(int(round(float(c) * 255)) for c in colour[:3])
            for row in gui.sequences
            for colour in row.colors
        ]

    before = strip_colors()
    shared.do("spectrum count, rainbow, polymer")
    for _ in range(10):
        qapp.processEvents()
    after = strip_colors()

    assert before != after, "the sequence strip kept its old colours"
    greens = [c for c in after if c[1] > c[0] + 40 and c[1] > c[2] + 40]
    assert greens, "the strip shows no green, so it is not the rainbow"


# --------------------------------------------------------------------------- #
# nonbonded_size belongs to unbonded atoms
# --------------------------------------------------------------------------- #
def test_a_bonded_ligand_keeps_its_van_der_waals_radius(lysozyme):
    """It was being shrunk to a quarter for not being polymer.

    The cartoon has to be shown too, and that is not incidental: the old rule
    read a residue colour map that is only populated when the polymer is drawn,
    so with spheres alone it found nothing to compare against and skipped the
    shrink. The defect appeared exactly in the combination anyone actually
    uses -- protein as cartoon, ligand as spheres.
    """
    win, shared, qapp = lysozyme
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    shared.do("show spheres, organic")
    for _ in range(10):
        qapp.processEvents()

    viewer = win.viewer
    unbonded = viewer._unbonded_atom_mask()
    assert unbonded is not None, "148L has bonds, so the mask must exist"

    _, _, ligand_mask = shared._resolve_selection_to_atom_mask(viewer, "organic")
    ligand = np.asarray(ligand_mask, dtype=bool)
    assert ligand.any(), "148L has organic ligands"
    # Every ligand atom is bonded to another, so none may be shrunk.
    assert not unbonded[ligand].any(), (
        "a bonded ligand atom was classified nonbonded and would be drawn small"
    )

    # And the drawn mesh has to be the size that implies. Compare the sphere
    # mesh's extent against the ligand's atom centres grown by their van-der-
    # Waals radii: at the old quarter-size it fell far short of that envelope.
    centres = np.asarray(viewer._all_atom_coords, dtype=float)[ligand]
    radii = np.asarray(viewer._all_atom_radii, dtype=float)[ligand]
    expected = (centres + radii[:, None]).max(axis=0) - (centres - radii[:, None]).min(axis=0)

    # Only the spheres: the cartoon spans the whole protein and would swamp any
    # measurement of the ligand.
    #
    # Each object's extent is its positions **grown by its own radii**, because
    # a sphere is an impostor now: its geometry carries one position and a
    # radius, where the tessellation carried a shell of vertices a radius away.
    # Measuring the raw positions reads 86% of the envelope for a perfectly
    # correct picture -- it is missing one radius at each end.
    lows: list[np.ndarray] = []
    highs: list[np.ndarray] = []
    for obj in viewer.get_current_scene().objects:
        geometry = obj.geometry
        positions = getattr(geometry, "positions", None)
        if positions is None or "cartoon" in str(obj.id):
            continue
        points = np.asarray(positions, dtype=float)
        if not points.size:
            continue
        grow = 0.0
        if getattr(geometry, "radii", None) is not None:
            grow = np.asarray(geometry.radii, dtype=float).reshape(-1, 1)
        lows.append((points - grow).min(axis=0))
        highs.append((points + grow).max(axis=0))
    assert lows, "show spheres, organic produced no geometry"
    actual = np.max(highs, axis=0) - np.min(lows, axis=0)

    # The margin has to be tight. A bounding box is dominated by how far apart
    # the atom *centres* are, so quartering every ligand radius only pulls this
    # ratio from 0.998 down to 0.892 -- a change that is glaring on screen and
    # easy to sleep through in an assertion. Anything looser than ~0.95 does
    # not distinguish the two.
    ratio = float(np.min(actual / expected))
    assert ratio > 0.95, (
        f"the ligand spheres span only {ratio:.0%} of their vdW envelope -- "
        "they are being drawn at nonbonded size"
    )


def test_waters_are_the_atoms_that_do_get_shrunk(qapp):
    """The rule has to still fire for what it was written for.

    ``solvated_fragment`` is the fixture with actual waters and a free ion --
    the case every plain-protein fixture in the tree misses.
    """
    win, shared = _window(qapp, _SOLVATED)
    try:
        viewer = win.viewer
        unbonded = viewer._unbonded_atom_mask()
        if unbonded is None:
            pytest.skip("no bonds inferred for this fixture")
        _, _, water_mask = shared._resolve_selection_to_atom_mask(viewer, "solvent")
        waters = np.asarray(water_mask, dtype=bool)
        assert waters.any(), "the fixture has waters"
        # Oxygens with no hydrogens in the file are genuinely unbonded.
        assert unbonded[waters].any(), (
            "no water was classified nonbonded, so nothing would be shrunk"
        )
    finally:
        win.close()


def test_the_unbonded_mask_is_none_without_bonds(lysozyme):
    """With no bond list every atom would qualify, which is worse than none."""
    win, _shared, _qapp = lysozyme
    viewer = win.viewer
    viewer._bond_pairs = None
    assert viewer._unbonded_atom_mask() is None


# --------------------------------------------------------------------------- #
# the default layout
# --------------------------------------------------------------------------- #
def test_the_viewport_gets_most_of_the_window(qapp):
    """``sizes: [3, 1]`` is pixels, not a ratio, and gave the view 40%.

    The mechanism this guarded is gone: the 3-D view **is** the window now, as
    the central widget, and everything that used to sit beside it is drawn
    inside the viewport by ``InternalGui``. So ``win.dock_area`` is ``None``
    and driving it was an ``AttributeError`` -- the test had been red on the
    tree rather than protecting anything.

    The property is still worth asserting, and is now stronger than "the
    larger half": there is nothing to take a share. Written against the
    central widget so it keeps meaning if a second widget is ever put back.
    """
    from chimol.hosts.qt import window as mw

    win = mw.MolViewPluginWindow()
    win.resize(1600, 950)
    win.show()
    for _ in range(15):
        qapp.processEvents()
    try:
        assert win.centralWidget() is win.viewer
        share = win.viewer.width() / win.width()
        assert share > 0.5, f"the 3D view got only {share:.0%} of the window"
    finally:
        win.close()


def test_the_default_layout_sizes_are_pixels(qapp):
    """A guard on the value itself, so a ratio cannot creep back in.

    Every other ``sizes`` in the state is in pixels; one entry written as a
    ratio is indistinguishable from a very small pixel count, which is exactly
    how this went unnoticed.
    """
    from chimol.hosts.qt import window as mw

    def walk(node):
        if node.get("type") == "splitter":
            for size in node.get("sizes", []):
                assert size >= 20, (
                    f"{size} is a ratio, not a pixel count: "
                    "QSplitter will clamp it to a minimum width"
                )
            for child in node.get("children", []):
                walk(child)

    walk(mw._DEFAULT_DOCK_AREA_STATE["root"])
