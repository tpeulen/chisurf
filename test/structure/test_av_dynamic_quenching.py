"""The dye-quenching reduction, now :func:`IMP.bff.quenching_rate_per_frame`.

The kernel moved to `IMP.bff` with PRD-109 (it is general fluorescence
machinery, and here it had no caller but this file). The test moved with it in
spirit and stays here as the consumer-side check that the upstream kernel still
reduces the way ChiSurf expects.

This kernel replaced a ``numexpr.evaluate('sum(k_quench * collided,axis=1)')``,
so the tests are written as the properties that expression had rather than as a
transcription of the loop: every collided atom contributes its own rate, an
atom the dye never met contributes nothing, and the frames are independent.
"""

from __future__ import annotations

import numpy as np
import pytest

from IMP.bff.quenching import (
    quenching_rate_per_frame as _quenching_rate_per_frame,
)


def _reference(collided, k_quench):
    """Return the expression the kernel replaced, evaluated in plain NumPy."""
    return (k_quench * collided).sum(axis=1)


@pytest.mark.parametrize("n_frames, n_atoms", [(1, 1), (7, 3), (500, 64)])
def test_it_matches_the_expression_it_replaced(n_frames, n_atoms):
    rng = np.random.default_rng(0)
    collided = (rng.random((n_frames, n_atoms)) < 0.2).astype(np.uint8)
    k_quench = rng.random(n_atoms) * 3.5
    np.testing.assert_allclose(
        _quenching_rate_per_frame(collided, k_quench),
        _reference(collided, k_quench),
        rtol=1e-12,
    )


def test_each_collided_atom_contributes_its_own_rate():
    # Not a sum of collisions scaled by a mean rate: TRP quenches at 3.5 and
    # HIS at 1.5, and a frame that met one of each must report 5.0.
    k_quench = np.array([3.5, 1.5, 1.7])
    collided = np.array([[1, 1, 0], [0, 0, 1], [1, 1, 1], [0, 0, 0]], dtype=np.uint8)
    np.testing.assert_allclose(
        _quenching_rate_per_frame(collided, k_quench), [5.0, 1.7, 6.7, 0.0]
    )


def test_a_frame_with_no_collision_is_zero_not_missing():
    # An unquenched frame is a real measurement (the dye was far from every
    # quencher), so it must be a zero in the trajectory, not a dropped row.
    k_quench = np.array([3.5, 1.5])
    collided = np.zeros((4, 2), dtype=np.uint8)
    result = _quenching_rate_per_frame(collided, k_quench)
    assert result.shape == (4,)
    assert np.all(result == 0.0)


def test_frames_are_independent():
    # The reduction is per row; shuffling frames must permute the result the
    # same way and change nothing else.
    rng = np.random.default_rng(3)
    collided = (rng.random((32, 8)) < 0.3).astype(np.uint8)
    k_quench = rng.random(8) * 2.0
    order = rng.permutation(32)
    np.testing.assert_allclose(
        _quenching_rate_per_frame(collided[order], k_quench),
        _quenching_rate_per_frame(collided, k_quench)[order],
    )


def test_a_nonzero_flag_counts_once_however_large():
    # `collided` is a flag array, not a count. numexpr multiplied by it, so a
    # stray 2 would have doubled that atom's rate; the kernel tests the flag.
    k_quench = np.array([3.5, 1.5])
    np.testing.assert_allclose(
        _quenching_rate_per_frame(np.array([[2, 0]], dtype=np.uint8), k_quench), [3.5]
    )
