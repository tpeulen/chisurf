"""Splitting an ALV intensity trace into per-run pieces must not need NumPy 1.

`mysplit` is reached by every ALV-5000/6000 file that records more than one
run: `openASC_old` cuts the single recorded trace into one piece per curve.
It computed the piece length with `np.int`, an alias for the builtin that
NumPy removed in 1.24, so on the project's NumPy the whole multi-run path
died with `AttributeError` before any data was produced.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.fcs.asc_alv import mysplit


@pytest.fixture()
def trace():
    """Return a 12-point ``(time, countrate)`` trace with a non-trivial mean."""
    time = np.linspace(0.0, 11.0, 12)
    return np.column_stack([time, 10.0 + np.sin(time)])


def test_a_trace_splits_into_one_piece_per_run(trace):
    """The regression: this raised `AttributeError: module 'numpy' has no attribute 'int'`."""
    pieces = mysplit(trace, 3)

    assert len(pieces) == 3
    assert all(piece.shape == (4, 2) for piece in pieces), [p.shape for p in pieces]


def test_the_split_preserves_the_average(trace):
    """The docstring's contract — the signal average survives the interpolation."""
    pieces = mysplit(trace, 3)
    joined = np.concatenate(pieces)

    assert joined[:, 1].mean() == pytest.approx(trace[:, 1].mean())
    # Time runs forward across the pieces, once per run.
    assert np.all(np.diff(joined[:, 0]) > 0)


def test_a_single_run_is_returned_unchanged(trace):
    """The early-out path, which never reached the removed alias."""
    for n in (0, 1):
        pieces = mysplit(trace, n)
        assert len(pieces) == 1
        np.testing.assert_allclose(pieces[0], trace)


def test_a_length_that_does_not_divide_evenly_still_splits(trace):
    """`ceil` rounds the piece length up, so 12 points in 5 runs give 5 × 3."""
    pieces = mysplit(trace, 5)

    assert len(pieces) == 5
    assert all(piece.shape == (3, 2) for piece in pieces), [p.shape for p in pieces]
