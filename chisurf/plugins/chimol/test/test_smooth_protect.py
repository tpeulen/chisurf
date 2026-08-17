"""``smooth`` and ``protect``/``deprotect``.

The smoothing is transcribed from ``layer3/Executive.cpp::ExecutiveSmooth``, and
the tests target the four details that are not visible in the command's help:

* the half-windows are ``window // 2`` **each**, taken independently, so an even
  window spans an odd number of states;
* ``ends`` is a four-way choice, not a flag, and it decides how many states at
  each end are left alone;
* the average divides by the number of states actually **found**, not by the
  window width -- dividing by the width pulls states near an end towards the
  origin, which looks like the trajectory collapsing;
* ``cutoff`` stops the window extending across a jump and pads with the last good
  position, so an atom that crosses a periodic boundary is not averaged with its
  own image.

Two mathematical properties are asserted as well, because they hold for *any*
correct running mean and so catch mistakes the transcription tests cannot: a
constant trajectory is unchanged, and a linear ramp is preserved away from the
ends.

``protect`` is only meaningful if something honours it, so it is tested through
``translate`` and ``rotate`` rather than by reading the flag back.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.analysis.smoothing import (
    END_MODES,
    smooth_frames,
)

_FRAGMENT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"
)


def _noisy_ramp(n_states=21, n_atoms=4, noise=0.4, seed=0):
    rng = np.random.default_rng(seed)
    ramp = np.linspace(0.0, 4.0, n_states)[:, None, None] * np.array([1.0, 0.0, 0.0])
    base = np.zeros((n_states, n_atoms, 3))
    base += np.arange(n_atoms)[None, :, None] * 3.0
    return base + ramp + rng.normal(0.0, noise, (n_states, n_atoms, 3))


def _roughness(frames):
    """Mean absolute step between consecutive states -- what smoothing reduces."""
    return float(np.abs(np.diff(np.asarray(frames), axis=0)).mean())


# --------------------------------------------------------------------------- #
# Properties any correct running mean has
# --------------------------------------------------------------------------- #
def test_a_constant_trajectory_is_unchanged():
    frames = np.tile(np.array([[1.0, 2.0, 3.0]]), (11, 1, 1))
    out = smooth_frames(frames, window=5)
    assert np.allclose(out, frames)


def test_a_linear_ramp_survives_away_from_the_ends():
    """A running mean of a linear function is that same function.

    This is what catches an off-by-one in the window, which noise would hide.
    """
    n = 21
    frames = (
        np.linspace(0.0, 10.0, n)[:, None, None] * np.array([1.0, 0.0, 0.0])
    ).repeat(2, axis=1)
    out = smooth_frames(frames, window=5, ends=2)
    interior = slice(5, n - 5)
    assert np.allclose(out[interior], frames[interior], atol=1e-9)


def test_smoothing_reduces_roughness():
    frames = _noisy_ramp()
    out = smooth_frames(frames, window=5)
    assert _roughness(out) < _roughness(frames) / 2


def test_the_input_is_not_modified():
    frames = _noisy_ramp()
    before = frames.copy()
    smooth_frames(frames, window=5)
    assert np.allclose(frames, before)


# --------------------------------------------------------------------------- #
# The transcription details
# --------------------------------------------------------------------------- #
def test_the_window_halves_are_integer_division():
    """``window=4`` gives two back and two forward -- five states, not four.

    A single spike is the probe: it spreads over exactly ``2*(window//2)+1``
    states, and where it lands tells us both half-widths.
    """
    n = 21
    frames = np.zeros((n, 1, 3))
    frames[10, 0, 0] = 1.0
    out = smooth_frames(frames, window=4, ends=1)
    touched = np.nonzero(np.abs(out[:, 0, 0]) > 1e-12)[0]
    assert touched.min() == 8 and touched.max() == 12


def test_an_odd_window_is_symmetric():
    n = 21
    frames = np.zeros((n, 1, 3))
    frames[10, 0, 0] = 1.0
    out = smooth_frames(frames, window=5, ends=1)
    touched = np.nonzero(np.abs(out[:, 0, 0]) > 1e-12)[0]
    assert touched.min() == 8 and touched.max() == 12


def test_the_average_divides_by_what_was_found():
    """Not by the window width.

    With ``ends=1`` the first state averages only itself and the two after it, so
    a constant trajectory must stay at that constant. Dividing by the window
    width instead would give three fifths of it.
    """
    frames = np.ones((11, 1, 3)) * 5.0
    out = smooth_frames(frames, window=5, ends=1)
    assert out[0, 0, 0] == pytest.approx(5.0)
    assert out[-1, 0, 0] == pytest.approx(5.0)


def test_ends_zero_leaves_one_state_at_each_end():
    frames = _noisy_ramp()
    out = smooth_frames(frames, window=5, ends=0)
    assert np.allclose(out[0], frames[0])
    assert np.allclose(out[-1], frames[-1])
    assert not np.allclose(out[1], frames[1])


def test_ends_one_smooths_to_the_very_ends():
    frames = _noisy_ramp()
    out = smooth_frames(frames, window=5, ends=1)
    assert not np.allclose(out[0], frames[0])
    assert not np.allclose(out[-1], frames[-1])


def test_ends_two_leaves_a_half_window():
    frames = _noisy_ramp()
    out = smooth_frames(frames, window=5, ends=2)
    # backward = 5 // 2 = 2, so the first two and last two are untouched.
    assert np.allclose(out[:2], frames[:2])
    assert np.allclose(out[-2:], frames[-2:])
    assert not np.allclose(out[2], frames[2])


def test_ends_three_wraps_the_trajectory():
    """Cyclic averaging: the first state sees the last ones.

    A step between the ends is what shows it -- with wrapping, both ends move
    towards each other; without it they cannot.
    """
    n = 12
    frames = np.zeros((n, 1, 3))
    frames[:, 0, 0] = np.concatenate([np.zeros(n // 2), np.ones(n // 2)])
    wrapped = smooth_frames(frames, window=5, ends=3)
    straight = smooth_frames(frames, window=5, ends=1)
    assert wrapped[0, 0, 0] > straight[0, 0, 0] + 1e-9


def test_every_documented_end_mode_is_handled():
    frames = _noisy_ramp()
    for mode in END_MODES:
        out = smooth_frames(frames, window=5, ends=mode)
        assert out.shape == frames.shape


def test_passes_are_sequential_not_one_wide_window():
    """Each pass reads the previous pass's output, as PyMOL's cycle loop does."""
    frames = _noisy_ramp()
    twice = smooth_frames(frames, window=5, passes=2)
    once = smooth_frames(frames, window=5, passes=1)
    wider = smooth_frames(frames, window=9, passes=1)
    assert not np.allclose(twice, once)
    assert not np.allclose(twice, wider)
    # Two passes of a narrow window smooth more than one.
    assert _roughness(twice) < _roughness(once)


def test_the_cutoff_stops_the_window_at_a_jump():
    """An atom crossing a boundary must not be averaged with its own image."""
    n = 11
    frames = np.zeros((n, 1, 3))
    frames[:, 0, 0] = np.arange(n) * 0.01
    frames[6:, 0, 0] += 50.0          # a jump

    without = smooth_frames(frames, window=5, ends=1, cutoff=-1)
    with_cutoff = smooth_frames(frames, window=5, ends=1, cutoff=1.0)
    # Without the guard, states either side of the jump land in between.
    assert 5.0 < without[5, 0, 0] < 45.0
    # With it, state 5 stays near its own side.
    assert with_cutoff[5, 0, 0] < 1.0


def test_the_mask_leaves_other_atoms_alone():
    frames = _noisy_ramp(n_atoms=4)
    mask = np.array([True, False, True, False])
    out = smooth_frames(frames, window=5, mask=mask)
    assert np.allclose(out[:, ~mask], frames[:, ~mask])
    assert not np.allclose(out[:, mask], frames[:, mask])


def test_an_empty_mask_is_a_no_op():
    frames = _noisy_ramp(n_atoms=3)
    out = smooth_frames(frames, window=5, mask=np.zeros(3, dtype=bool))
    assert np.allclose(out, frames)


def test_the_state_range_is_respected():
    frames = _noisy_ramp(n_states=21)
    out = smooth_frames(frames, window=5, first=8, last=16, ends=1)
    assert np.allclose(out[:8], frames[:8])
    assert np.allclose(out[17:], frames[17:])
    assert not np.allclose(out[10], frames[10])


def test_a_reversed_range_is_accepted():
    """PyMOL swaps them rather than refusing."""
    frames = _noisy_ramp()
    a = smooth_frames(frames, window=5, first=16, last=8, ends=1)
    b = smooth_frames(frames, window=5, first=8, last=16, ends=1)
    assert np.allclose(a, b)


# --------------------------------------------------------------------------- #
# What it refuses
# --------------------------------------------------------------------------- #
def test_a_window_below_two_is_refused():
    with pytest.raises(ValueError, match="at least size 2"):
        smooth_frames(_noisy_ramp(), window=1)


def test_a_window_wider_than_the_trajectory_is_refused():
    """Rather than quietly doing nothing, which PyMOL also refuses."""
    with pytest.raises(ValueError, match="fewer than the window"):
        smooth_frames(_noisy_ramp(n_states=6), window=9)


def test_the_wrong_shape_is_refused():
    with pytest.raises(ValueError, match="shape"):
        smooth_frames(np.zeros((5, 4)), window=3)


# --------------------------------------------------------------------------- #
# protect / deprotect, through the commands that must honour them
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.commands import cmd as shared

    win = MolViewPluginWindow()
    win.resize(900, 650)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win._load_structure_from_path(_FRAGMENT)
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win.viewer, do, errors
    win.close()


def _xyz(viewer):
    return np.asarray(viewer._atoms["xyz"], dtype=float).copy()


def test_protected_atoms_do_not_translate(session):
    """The whole point: `protect` then `translate` moves only the rest."""
    viewer, do, errors = session
    before = _xyz(viewer)
    residues = np.asarray(viewer._atoms["res_id"])

    do("protect resi 1-3")
    do("translate [10, 0, 0]")
    assert errors == []
    moved = np.linalg.norm(_xyz(viewer) - before, axis=1)

    held = residues <= 3
    assert float(moved[held].max()) == pytest.approx(0.0, abs=1e-9)
    assert float(moved[~held].min()) == pytest.approx(10.0, abs=1e-6)


def test_protected_atoms_do_not_rotate(session):
    """Rotation goes through the same seam, so it must honour it too."""
    viewer, do, errors = session
    before = _xyz(viewer)
    residues = np.asarray(viewer._atoms["res_id"])

    do("protect resi 1-3")
    do("rotate y, 45")
    assert errors == []
    moved = np.linalg.norm(_xyz(viewer) - before, axis=1)
    assert float(moved[residues <= 3].max()) == pytest.approx(0.0, abs=1e-9)
    assert float(moved[residues > 3].max()) > 1.0


def test_deprotect_releases_them(session):
    viewer, do, errors = session
    do("protect resi 1-3")
    do("deprotect all")
    before = _xyz(viewer)
    do("translate [10, 0, 0]")
    assert errors == []
    moved = np.linalg.norm(_xyz(viewer) - before, axis=1)
    assert float(moved.min()) == pytest.approx(10.0, abs=1e-6)


def test_deprotect_can_release_part_of_a_protected_set(session):
    viewer, do, errors = session
    residues = np.asarray(viewer._atoms["res_id"])
    do("protect resi 1-3")
    do("deprotect resi 2")
    before = _xyz(viewer)
    do("translate [10, 0, 0]")
    moved = np.linalg.norm(_xyz(viewer) - before, axis=1)
    assert float(moved[residues == 1].max()) == pytest.approx(0.0, abs=1e-9)
    assert float(moved[residues == 2].min()) == pytest.approx(10.0, abs=1e-6)


def test_nothing_protected_leaves_the_common_path_untouched(session):
    """No protection must not cost a rebuild or change the result."""
    viewer, do, errors = session
    before = _xyz(viewer)
    do("translate [5, 0, 0]")
    assert errors == []
    moved = np.linalg.norm(_xyz(viewer) - before, axis=1)
    assert float(moved.min()) == pytest.approx(5.0, abs=1e-6)
    assert float(moved.max()) == pytest.approx(5.0, abs=1e-6)


def test_smooth_on_a_single_state_object_says_so(session):
    """Averaging over a trajectory needs a trajectory."""
    viewer, do, errors = session
    do("smooth all")
    assert errors and "single state" in errors[-1]


def test_smooth_through_the_command_reduces_roughness(session):
    viewer, do, errors = session
    n_atoms = len(viewer._atoms)
    rng = np.random.default_rng(1)
    base = np.asarray(viewer._atoms["xyz"], dtype=float)
    trajectory = base[None, :, :] + rng.normal(0.0, 0.35, (21, n_atoms, 3))
    viewer.set_frames(trajectory)

    def stored():
        state = viewer._objects[viewer.get_active_object_id()].state
        return np.asarray(state.frames_raw, dtype=float)

    before = _roughness(stored())
    do("smooth all, 1, 5")
    assert errors == []
    assert _roughness(stored()) < before / 2


def test_smooth_reports_a_bad_window_through_the_command(session):
    viewer, do, errors = session
    n_atoms = len(viewer._atoms)
    base = np.asarray(viewer._atoms["xyz"], dtype=float)
    viewer.set_frames(np.repeat(base[None, :, :], 8, axis=0))
    do("smooth all, 1, 99")
    assert errors and "fewer than the window" in errors[-1]
