"""What makes a trajectory redraw fast, pinned so it cannot quietly come undone.

A cartoon frame change cost 238 ms when this was written -- four frames a second
-- and the reasons were all of one kind: work that does not depend on the frame
being redone for every frame, and NumPy called three floats at a time inside
per-residue Python loops.

Timing assertions are deliberately absent. They fail on a loaded machine and
tell you nothing about *why*, and this repository is worked by several agents at
once, so wall-clock here would be a coin flip. What is pinned instead is the
structure that produces the speed:

* the backbone lookup is topology and survives a frame change;
* it is *not* allowed to survive a sort or a delete, which renumber the atoms it
  points at;
* extrusion connectivity depends only on the shape of the extrusion;
* a scrub draws draft quality and a still frame does not;
* the vectorised rewrites still agree with the loops they replaced.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.atom_order import (
    permute_atom_state,
    subset_atom_state,
)
from chisurf.plugins.chimol.chimol.geometry.cartoon import (
    _build_trace_ups,
    _extrusion_faces,
    _flip_for_sign_continuity,
    backbone_index_map,
)


# --------------------------------------------------------------------------- #
# The backbone index map: topology, and only topology
# --------------------------------------------------------------------------- #
def _toy_atoms(n_res: int = 4, chains: tuple[str, ...] = ("A",)) -> np.ndarray:
    """A structured atom array with a real N/CA/C/O backbone per residue."""
    dtype = np.dtype([
        ("atom_name", "U4"), ("res_id", "i8"), ("chain", "U2"), ("xyz", "f8", 3),
    ])
    rows = []
    for chain in chains:
        for res in range(1, n_res + 1):
            for k, name in enumerate(("N", "CA", "C", "O")):
                rows.append((name, res, chain, (res * 3.0 + k, k * 1.0, 0.0)))
    return np.array(rows, dtype=dtype)


def test_the_map_finds_each_residues_backbone():
    atoms = _toy_atoms(3)
    res_ids = np.array([1, 2, 3])
    chain_ids = np.array(["A", "A", "A"])
    mapped = backbone_index_map(atoms, res_ids, chain_ids)
    assert mapped.shape == (3, 3)
    for row, res in enumerate(res_ids):
        for column, name in enumerate(("N", "C", "O")):
            index = mapped[row, column]
            assert atoms["atom_name"][index] == name
            assert atoms["res_id"][index] == res


def test_residues_sharing_a_number_across_chains_all_get_a_backbone():
    """The bug the first version of this shipped with.

    Mapping *atoms to residues* hands each atom to exactly one residue, so when
    two chains number their residues the same way -- and `chain_ids` is not
    available to tell them apart, which is the case for 1RTD's 2028 residues
    over 554 numbers -- every duplicate but one was left with no backbone at all
    and fell back to +Z. Mapping residues to atoms is what fixes it.
    """
    atoms = _toy_atoms(2, chains=("A", "B"))
    res_ids = np.array([1, 2, 1, 2])
    mapped = backbone_index_map(atoms, res_ids, None)  # no chains to separate them
    assert (mapped >= 0).all(), mapped
    # Rows with the same residue number resolve to the same (first) atoms.
    assert np.array_equal(mapped[0], mapped[2])
    assert np.array_equal(mapped[1], mapped[3])


def test_passing_the_map_changes_nothing_about_the_answer():
    """The cache is a speed-up, not a different code path."""
    atoms = _toy_atoms(5)
    res_ids = np.array([1, 2, 3, 4, 5])
    chain_ids = np.array(["A"] * 5)
    ca = np.zeros((5, 3))
    fresh = _build_trace_ups(atoms, res_ids, ca, chain_ids)
    cached = _build_trace_ups(
        atoms, res_ids, ca, chain_ids,
        index_map=backbone_index_map(atoms, res_ids, chain_ids),
    )
    assert np.allclose(fresh, cached, atol=0, rtol=0)


def test_a_stale_map_is_refused_rather_than_used():
    """A map of the wrong length is a different structure; recompute, don't index."""
    atoms = _toy_atoms(4)
    res_ids = np.array([1, 2, 3, 4])
    chain_ids = np.array(["A"] * 4)
    ca = np.zeros((4, 3))
    good = _build_trace_ups(atoms, res_ids, ca, chain_ids)
    from_wrong_size = _build_trace_ups(
        atoms, res_ids, ca, chain_ids, index_map=np.zeros((2, 3), dtype=np.int64)
    )
    assert np.allclose(good, from_wrong_size)


# --------------------------------------------------------------------------- #
# ...which means it must not outlive a renumbering
# --------------------------------------------------------------------------- #
class _State:
    """Enough of the object state for the reorder helpers to work on."""

    def __init__(self, atoms):
        self.atoms = atoms
        self.backbone_map = np.zeros((4, 3), dtype=np.int64)
        self.bond_pairs = None
        self.bond_edits = None
        self.frames = None
        self.frames_raw = None


@pytest.mark.parametrize("operation", ["sort", "subset"])
def test_reordering_the_atoms_discards_the_map(operation):
    """Its values are atom indices, so a renumbering makes them point elsewhere.

    Keeping it would not raise; it would orient every ribbon off whatever atom
    landed in that slot -- wrong in a way only a picture shows.
    """
    atoms = _toy_atoms(4)
    state = _State(atoms)
    assert state.backbone_map is not None
    if operation == "sort":
        permute_atom_state(state, np.arange(len(atoms))[::-1])
    else:
        subset_atom_state(state, np.ones(len(atoms), dtype=bool))
    assert state.backbone_map is None


def test_the_state_field_is_classified():
    """`backbone_map` has to be in one of the two lists or `sort` guesses."""
    from chisurf.plugins.chimol.chimol.analysis.atom_order import (
        ATOM_INDEXED_FIELDS,
        NON_ATOM_INDEXED_FIELDS,
    )

    assert "backbone_map" in set(ATOM_INDEXED_FIELDS) | set(NON_ATOM_INDEXED_FIELDS)


# --------------------------------------------------------------------------- #
# Extrusion connectivity is a function of the extrusion's shape
# --------------------------------------------------------------------------- #
def test_faces_depend_only_on_the_shape_and_are_shared():
    first = _extrusion_faces(6, 8, True, True)
    second = _extrusion_faces(6, 8, True, True)
    assert first is second, "same shape must not rebuild the connectivity"
    assert _extrusion_faces(7, 8, True, True) is not first


def test_shared_faces_cannot_be_written_through():
    """Callers share one array; a caller that edited it would corrupt the rest."""
    faces = _extrusion_faces(5, 6, True, False)
    with pytest.raises(ValueError):
        faces[0, 0] = 999


def test_caps_add_the_fan_triangles():
    uncapped = _extrusion_faces(5, 6, False, False)
    capped = _extrusion_faces(5, 6, True, True)
    # Two fans of (s - 2) triangles each.
    assert capped.shape[0] == uncapped.shape[0] + 2 * (6 - 2)
    assert capped[:uncapped.shape[0]].tolist() == uncapped.tolist()


# --------------------------------------------------------------------------- #
# The cumprod identity behind the sign sweeps
# --------------------------------------------------------------------------- #
def _sign_sweep_by_hand(vectors: np.ndarray) -> np.ndarray:
    out = np.array(vectors, dtype=float)
    for i in range(1, out.shape[0]):
        if float(np.dot(out[i - 1], out[i])) < 0.0:
            out[i] = -out[i]
    return out


def test_the_vectorised_sign_sweep_matches_the_loop():
    rng = np.random.default_rng(20260727)
    for _ in range(20):
        vectors = rng.normal(size=(40, 3))
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        assert np.allclose(
            _flip_for_sign_continuity(vectors.copy()), _sign_sweep_by_hand(vectors)
        )


def test_exactly_perpendicular_neighbours_take_the_scan():
    """Where the running-product identity does not hold, behaviour is preserved."""
    vectors = np.array([
        [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],   # opposes -> flipped
        [0.0, 1.0, 0.0],    # exactly perpendicular to the flipped predecessor
        [0.0, -1.0, 0.0],
    ])
    assert np.allclose(
        _flip_for_sign_continuity(vectors.copy()), _sign_sweep_by_hand(vectors)
    )


# --------------------------------------------------------------------------- #
# Draft quality is entered by rate, not by a mode
# --------------------------------------------------------------------------- #
def test_draft_only_coarsens_and_never_invents_a_setting():
    """Every draft key must exist in the real cartoon config.

    A typo here would not raise -- it would add a key nothing reads, and the
    setting it was meant to lower would stay at full quality with no sign of it.
    """
    from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    real = _DISPLAY_CONFIG.get("cartoon", {})
    for key, value in MolView._DRAFT_CARTOON.items():
        assert key in real, f"draft sets {key!r}, which the cartoon config has no such key for"
        if isinstance(value, bool):
            continue
        assert value <= real[key], f"draft {key} ({value}) is not coarser than {real[key]}"


def test_the_ribbons_facing_is_never_drafted():
    """Coarser is fine mid-scrub; differently-twisted is not.

    Dropping these would make the ribbon flip face while scrubbing and snap back
    on settle, which reads as a glitch rather than as a redraw.
    """
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    for setting in ("refine_normals", "flat_sheets", "refine_tips", "smooth_loops"):
        assert setting not in MolView._DRAFT_CARTOON


# --------------------------------------------------------------------------- #
# ...and entering it is a decision about rate, not a mode the caller sets
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_one_frame_change_on_its_own_is_never_drafted(qapp):
    """A headless render or a single click gets the real thing.

    This is why the decision is made on rate rather than on a flag somebody sets
    around playback: a flag left on -- or a render that happens to run through
    the playback path -- would silently produce a coarse picture and say nothing.
    Nothing here can downgrade an isolated frame.
    """
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        view._note_frame_change()
        assert view._draft_quality is False
    finally:
        view.deleteLater()


def test_frames_arriving_back_to_back_are_drafted(qapp):
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        view._note_frame_change()      # first: nothing to compare against
        view._note_frame_change()      # hard on its heels -> a scrub
        assert view._draft_quality is True
    finally:
        view.deleteLater()


def test_a_pause_returns_to_full_quality(qapp, monkeypatch):
    """The settle timer is a bonus; the rate test alone must recover."""
    import time as _time

    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        clock = [1000.0]
        monkeypatch.setattr(_time, "perf_counter", lambda: clock[0])
        view._note_frame_change()
        clock[0] += 0.01
        view._note_frame_change()
        assert view._draft_quality is True
        clock[0] += 5.0                # the user stopped scrubbing
        view._note_frame_change()
        assert view._draft_quality is False
    finally:
        view.deleteLater()


# --------------------------------------------------------------------------- #
# Playback: step, interpolation, and not starving the event loop
# --------------------------------------------------------------------------- #
def test_a_fractional_position_splits_into_a_pair_and_a_weight():
    from chisurf.plugins.chimol.chimol.renderer.view import _frame_blend

    assert _frame_blend(3.0, 10) == (3, 0.0, 3)
    index, blend, nxt = _frame_blend(3.25, 10)
    assert (index, nxt) == (3, 4) and blend == pytest.approx(0.25)
    # The last frame has nothing to blend toward.
    assert _frame_blend(9.0, 10) == (9, 0.0, 9)
    assert _frame_blend(9.7, 10) == (9, 0.0, 9)
    # Out of range and nonsense are clamped, never raised.
    assert _frame_blend(-4.0, 10) == (0, 0.0, 0)
    assert _frame_blend(float("nan"), 10) == (0, 0.0, 0)
    assert _frame_blend("not a number", 10) == (0, 0.0, 0)
    assert _frame_blend(2.5, 0) == (0, 0.0, 0)


def test_interpolation_lands_between_the_two_frames(qapp):
    """A half-step must be the midpoint, not one of the ends rounded to.

    Checked on ``all_atom_coords``, which is the selected frame itself. The
    render coordinates are re-centred per frame, so a *uniform* translation --
    the obvious thing to build a fixture from -- is subtracted straight back out
    of them and every frame compares equal.
    """
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        frames = np.zeros((3, 4, 3), dtype=float)
        frames[1, :, 0] = 10.0          # frame 1 is 10 A along x
        frames[2, :, 0] = 20.0
        view.add_coordinates(frames[0])
        view.set_frames(frames)

        # Expectations come from the *stored* frames: `set_frames` scales and
        # centres on ingest, so asserting the numbers that went in would be
        # testing the ingest transform rather than the interpolation.
        stored = np.asarray(view._get_active_state().frames, dtype=float)

        def shown_at(position):
            view.set_frame_position(position)
            return np.asarray(
                view._get_active_state().all_atom_coords, dtype=float
            )

        assert shown_at(0.0) == pytest.approx(stored[0])
        assert shown_at(0.5) == pytest.approx(0.5 * (stored[0] + stored[1]))
        assert shown_at(1.25) == pytest.approx(0.75 * stored[1] + 0.25 * stored[2])
        # A whole number is the stored frame, untouched.
        assert shown_at(2.0) == pytest.approx(stored[2])
    finally:
        view.deleteLater()


def test_the_whole_frame_setter_does_not_keep_its_own_position(qapp):
    """One position, or a spinbox and a picture will disagree about the frame."""
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        frames = np.zeros((5, 4, 3), dtype=float)
        for i in range(5):
            frames[i, :, 0] = float(i)
        view.add_coordinates(frames[0])
        view.set_frames(frames)
        view.set_frame_position(2.5)
        assert view.get_current_frame() == 2
        view.set_current_frame(4)
        assert view.get_frame_position() == pytest.approx(4.0)
    finally:
        view.deleteLater()


def test_playback_reschedules_itself_instead_of_repeating(qapp):
    """The event-loop starvation fix, pinned where it lives.

    A repeating timer whose interval is shorter than the redraw never lets the
    loop idle, and the window stops answering the mouse -- measured at a 266 ms
    median gap between event-loop turns before this, and 25 ms after. What makes
    the difference is that the next frame is asked for only once the last one is
    drawn, so the guarantee to keep is `setSingleShot`.
    """
    from qtpy import QtCore

    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    try:
        timer = QtCore.QTimer(view)
        view._animation_timer = timer
        timer.setSingleShot(True)
        assert timer.isSingleShot(), "playback must not repeat on a fixed interval"
    finally:
        view.deleteLater()


# --------------------------------------------------------------------------- #
# The numba kernels and the NumPy fallback must be the same function
# --------------------------------------------------------------------------- #
def _ring_shape(s: int):
    """A circular cross-section: vertices and their outward normals."""
    angle = np.linspace(0.0, 2.0 * np.pi, s, endpoint=False)
    verts = np.zeros((s, 3))
    norms = np.zeros((s, 3))
    verts[:, 1] = norms[:, 1] = np.cos(angle)
    verts[:, 2] = norms[:, 2] = np.sin(angle)
    return verts, norms



# The pair of tests that used to live here compared the compiled path against a
# pure-Python one and forced `_HAVE_NUMBA = False` to exercise the second. Both
# are gone with the branch they tested: numba is a hard requirement now, so
# there is no "plain path" to agree with, and a test that monkeypatches away a
# constant which no longer exists tests nothing.


# --------------------------------------------------------------------------- #
# A colour query is not a scene rebuild
# --------------------------------------------------------------------------- #
def test_reading_residue_colours_does_not_rebuild_the_scene(qapp):
    """`get_residue_colors` must compute colours and nothing else.

    The sequence strip has no signal to tell it that `color`, `spectrum` or `ss`
    ran, so `_refresh_gui_state` re-reads these colours **once per object on
    every frame**, from inside `paintGL`. That is fine as long as the call is
    what its call site claims -- "a cached array copy, which costs nothing".

    It was not. It went through `_build_scene_for_current_object`, so every
    frame rebuilt every representation to recover one array: with a surface
    shown, a density grid, marching cubes, the gradients and the ambient
    occlusion, sixty times a second. Measured on 148L at 1280x860, that was
    **82 ms of an 82 ms frame** -- and it is why frame time did not move when
    the window was resized 8x, which is the measurement that found it.

    Pinned structurally rather than by a clock, like everything else in this
    file: the scene builder must not be entered at all.
    """
    import pathlib

    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )

    view = MolView()
    try:
        object_id = view.add_structure(
            _read_full_model(cs_struct.Structure, pdb),
            name="148l",
            source_path=str(pdb),
        )

        builds = []
        original = view._build_scene_for_current_object

        def counted(*args, **kwargs):
            builds.append(1)
            return original(*args, **kwargs)

        view._build_scene_for_current_object = counted
        colours = view.get_residue_colors(object_id)

        assert colours is not None, "the colours themselves must still come back"
        assert colours.ndim == 2 and colours.shape[0] > 0
        assert not builds, (
            f"get_residue_colors entered the scene builder {len(builds)} time(s); "
            "it runs once per object per frame from paintGL"
        )
    finally:
        view.deleteLater()


# --------------------------------------------------------------------------- #
# Re-enabling an object is not a scene rebuild
# --------------------------------------------------------------------------- #
def test_reenabling_an_object_does_not_rebuild_its_scene(qapp):
    """`disable` then `enable` must not re-enter the scene builder.

    The report: "when i disable an object and reenable it that is kind of
    slow, why there should be no recompute needed." It was not just slow for
    the toggled object -- `_update_view` rebuilt *every visible entry* on
    every call, with no way to tell "a boolean flipped" from "the geometry
    moved". Measured on 148L with a surface, sticks and a cartoon shown, one
    disable/enable cycle cost 37.6 ms; none of it was needed, because nothing
    about the object's coordinates, colours or representations had changed --
    only whether it was drawn.

    `_update_view` now takes a `visibility_only` flag, set only by
    `set_object_visible`. Every other mutation -- colouring, editing, `set`,
    every representation change -- still asks for the unconditional rebuild,
    which bumps `_scene_build_generation` and rebuilds every visible entry for
    real; that is what makes trusting the cache safe without tracking what
    changed. `set_object_visible` reuses an entry's last-built scene exactly
    when it was built at the *current* generation, which after this session
    (add the structure, no other command) it always is.

    Pinned structurally, like the colour-query case above: the scene builder
    must not be entered by `disable` or `enable` when nothing else has
    touched the object in between, and the object must still draw once
    re-enabled.
    """
    import pathlib

    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )

    view = MolView()
    try:
        object_id = view.add_structure(
            _read_full_model(cs_struct.Structure, pdb),
            name="148l",
            source_path=str(pdb),
        )
        # A representative scene -- a surface and sticks are the expensive
        # representations a rebuild would otherwise redo.
        view._surface_visible = True
        view._show_sticks = True
        view._update_view()  # one general rebuild, so there is a cache to reuse

        builds = []
        original = view._build_scene_for_current_object

        def counted(*args, **kwargs):
            builds.append(1)
            return original(*args, **kwargs)

        view._build_scene_for_current_object = counted

        view.set_object_visible(object_id, False)
        view.set_object_visible(object_id, True)

        assert not builds, (
            f"disable/enable entered the scene builder {len(builds)} time(s); "
            "nothing about the object's geometry changed, only whether it is drawn"
        )
        assert view._scene is not None and view._scene.objects, (
            "the object must still be drawn after re-enabling"
        )

        # A genuine change in between must still be picked up: this is not a
        # cache that can never invalidate, only one that skips work it can
        # prove is unnecessary.
        view._build_scene_for_current_object = original
        view.set_object_visible(object_id, False)
        # What `color`/`set`/an edit does under the hood: change a state
        # field, then ask for the *general* (non-visibility-only) rebuild --
        # which always rebuilds for real and bumps `_scene_build_generation`.
        view._color_mode = "chain"
        view._update_view()
        view._build_scene_for_current_object = counted
        view.set_object_visible(object_id, True)
        assert builds, (
            "a colour change between disable and enable must force a real "
            "rebuild, not reuse the pre-change scene"
        )
    finally:
        view.deleteLater()
