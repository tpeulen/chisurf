"""Watching a trajectory: how fast it steps, how calm it looks, what colour it is.

A trajectory sampled finely enough to be smooth in time is rarely smooth to
*look* at. Thermal motion moves every atom a little in every frame, so the
picture shimmers even when nothing is happening, and stepping such a trajectory
one frame at a time is indistinguishable from standing still.

Two separate knobs, because they answer different questions: **step** skips
frames to cover a long trajectory in reasonable time, **smoothing** averages
neighbouring frames so the picture stops being restless. Neither may change what
the current frame *is*.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.io.atoms import make_bead_rows
from chimol.core.viewer import MolView


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def jittery(_qt_app):
    """Build a steady drift with heavy per-frame jitter laid over it.

    The shape of a real trajectory's problem: the motion worth watching is slow,
    and it is buried under noise that changes every frame.
    """
    rng = np.random.default_rng(0)
    n_frames, n_atoms = 60, 40
    drift = np.linspace(0, 10, n_frames)[:, None, None] * np.array([1.0, 0.0, 0.0])
    base = rng.normal(scale=5.0, size=(1, n_atoms, 3))
    frames = base + drift + rng.normal(scale=1.2, size=(n_frames, n_atoms, 3))

    view = MolView()
    view.set_coordinates(
        frames[0],
        atoms=make_bead_rows(frames[0]),
        atom_radii=np.full(n_atoms, 2.0),
    )
    view.set_frames(frames)
    return view, frames


def _walk(view, n_frames):
    """Return the path of atom 0 as every frame is shown in turn."""
    out = []
    for frame in range(n_frames):
        view.set_current_frame(frame)
        out.append(np.asarray(view._all_atom_coords, dtype=float)[0].copy())
    return np.asarray(out)


# --------------------------------------------------------------------------- #
# Smoothing
# --------------------------------------------------------------------------- #
def test_smoothing_calms_the_jitter_and_keeps_the_motion(jittery):
    """The whole point: less shimmer, same journey.

    A filter that also removed the drift would be hiding the data rather than
    steadying the picture, so both are measured.
    """
    view, frames = jittery
    n = frames.shape[0]

    view.set_trajectory_smoothing(0)
    raw = _walk(view, n)
    view.set_trajectory_smoothing(9)
    smooth = _walk(view, n)

    jump_raw = float(np.median(np.linalg.norm(np.diff(raw, axis=0), axis=1)))
    jump_smooth = float(np.median(np.linalg.norm(np.diff(smooth, axis=0), axis=1)))
    assert jump_smooth < jump_raw / 3.0, "the jitter should drop several-fold"

    drift_raw = float(np.linalg.norm(raw[-1] - raw[0]))
    drift_smooth = float(np.linalg.norm(smooth[-1] - smooth[0]))
    assert drift_smooth > 0.85 * drift_raw, "the real motion must survive"


def test_a_wider_window_is_calmer(jittery):
    view, frames = jittery
    n = frames.shape[0]

    def jitter(window):
        view.set_trajectory_smoothing(window)
        path = _walk(view, n)
        return float(np.median(np.linalg.norm(np.diff(path, axis=0), axis=1)))

    assert jitter(9) < jitter(3) < jitter(0)


@pytest.mark.parametrize("window", [0, 1])
def test_no_window_means_the_trajectory_as_recorded(jittery, window):
    """0 and 1 both mean "do not touch it" -- a window of one is no window.

    Compared against the *stored* frames rather than the input: `set_frames`
    centres and scales the trajectory into scene units, so raw input
    coordinates are the wrong frame of reference to check against.
    """
    view, _frames = jittery
    stored = np.asarray(view._get_active_state().frames, dtype=float)
    view.set_trajectory_smoothing(window)
    view.set_current_frame(7)
    np.testing.assert_allclose(
        np.asarray(view._all_atom_coords, dtype=float), stored[7], atol=1e-9
    )


def test_smoothing_does_not_change_which_frame_it_is(jittery):
    """Display only. The frame number, and anything keyed on it, must not move.

    Otherwise a measurement or an export taken while smoothing is on would
    silently describe a frame that does not exist in the file.
    """
    view, frames = jittery
    view.set_trajectory_smoothing(11)
    view.set_current_frame(12)

    assert view.get_current_frame() == 12
    state = view._get_active_state()
    assert state.active_frame == 12
    # `frames_raw` is what everything else reads back; it stays untouched.
    np.testing.assert_allclose(np.asarray(state.frames_raw)[12], frames[12], atol=1e-9)


def test_the_window_is_clipped_at_the_ends_not_wrapped(jittery):
    """A trajectory's last frame is not next to its first.

    Wrapping would average the end into the beginning and invent a motion that
    never happened -- most visible exactly where a viewer starts and stops.

    Asserted as the *property* rather than as a formula. This used to compare
    against ``stored[0:5].mean(axis=0)``, which encoded two things that have
    since deliberately changed: the window is now **clamped rather than
    shrunk** (the end frame repeats, so smoothing does not quietly weaken
    exactly where it is least even) and weighted by a **Bartlett triangle**
    rather than a boxcar. Re-deriving either here would make the test a copy of
    the implementation -- it would agree with any future change and catch
    nothing.

    So: move the far end of the trajectory a long way, and require that the
    near end does not notice. That is what "not wrapped" means, and it holds
    whatever the window's shape.
    """
    view, frames = jittery
    n = frames.shape[0]
    view.set_trajectory_smoothing(9)

    view.set_current_frame(0)
    first_before = np.asarray(view._all_atom_coords, dtype=float).copy()
    view.set_current_frame(n - 1)
    last_before = np.asarray(view._all_atom_coords, dtype=float).copy()

    # Displace the last frames far enough that any leakage is unmistakable.
    state = view._get_active_state()
    stored = np.asarray(state.frames, dtype=float).copy()
    stored[n - 3:] += 1000.0
    state.frames = stored
    view.set_trajectory_smoothing(9)  # drop any cached smoothed frame

    view.set_current_frame(0)
    first_after = np.asarray(view._all_atom_coords, dtype=float)
    np.testing.assert_allclose(
        first_after, first_before, atol=1e-9,
        err_msg="the first frame moved when the last frames did -- the window "
                "wrapped around the seam",
    )

    # ... and the far end *did* see it, or the displacement proved nothing.
    view.set_current_frame(n - 1)
    last_after = np.asarray(view._all_atom_coords, dtype=float)
    assert not np.allclose(last_after, last_before, atol=1e-9), (
        "the last frame ignored a 1000-unit displacement of itself, so the "
        "check above cannot distinguish clipping from a dead code path"
    )


# --------------------------------------------------------------------------- #
# Step
# --------------------------------------------------------------------------- #
def test_the_step_drives_the_same_setting_as_the_command(jittery):
    """The control beside the slider and `mset` must not disagree."""
    view, _frames = jittery
    view.set_frame_step(7)
    assert view.get_frame_step() == 7
    assert view.movie_step == 7


def test_the_step_is_at_least_one(jittery):
    """A step of zero would advance nowhere and play forever."""
    view, _frames = jittery
    view.set_frame_step(0)
    assert view.get_frame_step() == 1
