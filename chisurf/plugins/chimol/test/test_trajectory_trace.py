"""A trajectory must not break the cartoon: the trace, the sign, the averaging.

Three faults lived here, and each looked like a different bug.

**The trace became every atom.** ``load_traj`` laid 464 frames of 5,235 atoms
onto a 570-residue protein and the render trace went from 570 points to 5,235,
so the cartoon splined a ribbon through every atom in file order -- a spiky
hairball. The cause was one field: ``_select_state_frame`` extracts the CA trace
through ``state._ca_indices``, and that was filled only by ``set_coordinates``,
so a structure loaded any other way left it ``None`` and the fallback is "use
the whole frame".

**The ribbon's face flipped every frame.** A ribbon's up-vector carries the
twist and its sign is arbitrary -- ``u`` and ``-u`` describe the same plane --
so the sign is resolved along the chain from whatever seed the first residue
gives. Every frame reseeded, and 48 % of the vectors flipped between consecutive
frames.

**And the twist was never averaged.** Those vectors are built from
``atoms["xyz"]``, which was synced from the *raw* frames while the render
coordinates went through the smoother. So ``Avg`` smoothed the cartoon's path
and not its twist.

The tests are written against numbers rather than pixels, because a hairball and
a ribbon differ in ways no threshold can state while ``570 != 5235`` is exact.

They run in a **child process**: the toolkit-free host needs ``MolView`` bound
without Qt, and that is decided once per process at import. See
:mod:`.toolkit_free` for the two approaches that failed before this one.
"""
from __future__ import annotations

import pytest

from toolkit_free import DATA, probe

#: 570 residues, 5,235 atoms, 464 frames.
HGBP1 = DATA / "atomic_coordinates" / "trajectory" / "hgbp1"
TOPOLOGY = HGBP1 / "topol.pdb"
FRAMES = HGBP1 / "hgbp1_transition.dcd"


@pytest.fixture(scope="module")
def loaded():
    """Load the topology, then lay the trajectory on it."""
    if not TOPOLOGY.is_file() or not FRAMES.is_file():
        pytest.skip("the hgbp1 trajectory fixture is not present")
    return probe(f"""
        app = open_app(size=(640, 480))
        app.cmd.do("load {TOPOLOGY}")
        emit("residues", len(app.viewer._residue_ids))
        emit("atoms", len(app.viewer._atoms))
        emit("trace_before", app.viewer._coords.shape[0])
        app.cmd.do("load_traj {FRAMES}")
        emit("trace_after", app.viewer._coords.shape[0])
    """)


def test_the_trace_is_one_point_per_residue_before_any_trajectory(loaded):
    """The baseline everything else is measured against."""
    assert int(loaded["trace_before"]) == int(loaded["residues"])


def test_a_trajectory_does_not_replace_the_trace_with_every_atom(loaded):
    """The bug, stated as the number that changed."""
    atoms, residues = int(loaded["atoms"]), int(loaded["residues"])
    assert atoms > residues, "fixture assumption: more atoms than residues"
    assert int(loaded["trace_after"]) != atoms, (
        f"the trace became one point per *atom* ({atoms}); the cartoon will "
        "spline a ribbon through every atom in file order"
    )
    assert int(loaded["trace_after"]) == residues


@pytest.fixture(scope="module")
def played():
    """Step through frames with the cartoon shown, reporting what moved."""
    if not TOPOLOGY.is_file() or not FRAMES.is_file():
        pytest.skip("the hgbp1 trajectory fixture is not present")
    return probe(f"""
        app = open_app(size=(640, 480))
        app.cmd.do("load {TOPOLOGY}")
        app.cmd.do("load_traj {FRAMES}")
        app.cmd.do("hide everything")
        app.cmd.do("show cartoon, polymer")
        viewer = app.viewer
        scale = float(getattr(viewer, "_scale_factor", 1.0)) or 1.0

        def walk(window):
            viewer.set_trajectory_smoothing(window)
            previous, flips, angles, lengths = None, [], [], []
            for frame in range(20, 26):
                app.cmd.do("frame %d" % frame)
                lengths.append(viewer._coords.shape[0])
                ups = np.asarray(viewer._trace_ups, dtype=float)
                if previous is not None and previous.shape == ups.shape:
                    dot = np.einsum("ij,ij->i", ups, previous)
                    flips.append(float((dot < 0).mean()))
                    angles.append(float(np.degrees(
                        np.arccos(np.clip(np.abs(dot), -1, 1))).mean()))
                previous = ups
            return lengths, flips, angles

        emit("residues", len(viewer._residue_ids))

        lengths, flips, angles = walk(0)
        emit("trace_lengths", ",".join(str(x) for x in lengths))
        emit("max_flip_unsmoothed", max(flips))
        emit("swing_unsmoothed", sum(angles) / len(angles))

        _, flips, angles = walk(15)
        emit("max_flip_smoothed", max(flips))
        emit("swing_smoothed", sum(angles) / len(angles))

        # A real CA trace steps about 3.8 Angstrom per residue. The median, not
        # the max: this fixture has two chains and a break is a real large jump.
        app.cmd.do("frame 10")
        steps = np.linalg.norm(
            np.diff(np.asarray(viewer._coords), axis=0), axis=1) / scale
        emit("median_step", float(np.median(steps)))
    """)


def test_the_trace_stays_per_residue_as_frames_change(played):
    """Stepping must not reintroduce it -- the extraction runs per frame."""
    residues = int(played["residues"])
    lengths = [int(x) for x in played["trace_lengths"].split(",")]
    assert lengths, "no frames were stepped"
    assert set(lengths) == {residues}, f"trace lengths across frames: {lengths}"


def test_the_trace_still_looks_like_a_backbone(played):
    """Length alone is not enough: picking the wrong 570 atoms also gives 570."""
    assert 3.0 < float(played["median_step"]) < 4.5, (
        f"median consecutive step is {played['median_step']} A -- not a backbone"
    )


@pytest.mark.parametrize("key", ["max_flip_unsmoothed", "max_flip_smoothed"])
def test_the_ribbon_does_not_flip_its_face_between_frames(played, key):
    """No up-vector may reverse between frames, smoothed or not.

    Both are checked because averaging does not fix this and never did: with a
    fifteen-frame window the *orientation* is smooth and the sign flipped just
    as often, which is exactly why turning ``Avg`` up did nothing.
    """
    assert float(played[key]) == 0.0, (
        f"{float(played[key]) * 100:.0f}% of the ribbon's up-vectors flipped "
        "sign between frames -- the cartoon will flicker as it plays"
    )


def test_averaging_actually_smooths_the_ribbon(played):
    """`Avg` must reduce frame-to-frame motion, not merely exist."""
    unsmoothed = float(played["swing_unsmoothed"])
    smoothed = float(played["swing_smoothed"])
    assert unsmoothed > 0.0, "the trajectory does not move at all"
    assert smoothed < unsmoothed * 0.5, (
        f"averaging barely helped: {unsmoothed:.1f} deg -> {smoothed:.1f} deg"
    )
