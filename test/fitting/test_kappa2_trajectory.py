"""Per-frame kappa2 over a trajectory: what a frame that cannot be computed says.

``calculate_kappa_distance`` walks a trajectory and evaluates the orientation
factor frame by frame. A frame whose dipole endpoints coincide -- a missing or
duplicated atom -- makes ``kappa_distance`` divide by a zero dipole length and
raise, so that frame is skipped.

It used to be skipped *silently* into an ``np.empty`` buffer: the entry kept
whatever was on the heap, and the same all-zero trajectory answered ``0.0`` on a
clean allocator and ``7777.0`` after some other array had passed through. Both
look like real orientation factors. They must be ``NaN``.
"""

from __future__ import annotations

import logging

import numpy as np

from chisurf.core.fluorescence.anisotropy.kappa2 import calculate_kappa_distance

#: Donor dipole (0 -> 1), acceptor dipole (2 -> 3); the geometry of the doctest.
ATOMS = (0, 1, 2, 3)

#: One well-defined frame: kappa == 1.0 at a center distance of 0.86603.
GOOD_FRAME = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.5, 1.0]]

#: All four atoms on top of each other: both dipoles have zero length.
DEGENERATE_FRAME = [[0.0, 0.0, 0.0]] * 4


def _dirty_the_allocator(pattern: float = 7777.0) -> None:
    """Leave a recognisable float32 pattern in freed heap memory.

    Parameters
    ----------
    pattern : float, optional
        Value written into the throw-away buffers (default: 7777.0).
    """
    junk = [np.full(64, pattern, dtype=np.float32) for _ in range(256)]
    del junk


def test_a_degenerate_frame_is_nan_not_whatever_was_on_the_heap():
    """Unevaluable frames read NaN, and read the same on a dirty allocator."""
    xyz = np.array([DEGENERATE_FRAME] * 3, dtype=np.float64)

    ds_clean, ks_clean = calculate_kappa_distance(xyz, *ATOMS)
    _dirty_the_allocator()
    ds_dirty, ks_dirty = calculate_kappa_distance(xyz, *ATOMS)

    for a in (ds_clean, ks_clean, ds_dirty, ks_dirty):
        assert np.all(np.isnan(a))


def test_a_good_frame_survives_next_to_a_degenerate_one():
    """Only the frames that raise are NaN; the rest keep their values."""
    xyz = np.array([GOOD_FRAME, DEGENERATE_FRAME, GOOD_FRAME], dtype=np.float64)
    _dirty_the_allocator()

    ds, ks = calculate_kappa_distance(xyz, *ATOMS)

    assert np.isnan(ds[1]) and np.isnan(ks[1])
    np.testing.assert_allclose(ds[[0, 2]], 0.86603, atol=1e-5)
    np.testing.assert_allclose(ks[[0, 2]], 1.0, atol=1e-5)


def test_a_skipped_frame_is_logged_not_printed(caplog):
    """The skip reaches the logging system, where a caller can see it."""
    xyz = np.array([DEGENERATE_FRAME], dtype=np.float64)

    with caplog.at_level(logging.WARNING):
        calculate_kappa_distance(xyz, *ATOMS)

    assert any(r.levelno == logging.WARNING for r in caplog.records)
