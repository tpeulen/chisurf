"""The ported FRET kernels reproduce what the numba versions produced.

:mod:`chisurf.core.fluorescence.general` used to compile eight of its functions
with numba. Six were one-line expressions where the JIT dispatch cost more than
the arithmetic; two were real loops. All eight are now plain NumPy, and this is
what says the answers did not move.

**The reference is a committed fixture, not a live comparison.** Checking
against ``numba`` at test time would mean the guard evaporates -- silently, as a
skip that reads like a pass -- on the day numba leaves the environment, which is
the whole point of the exercise. So
``test/data/numba_parity/general_kernels.npz`` holds inputs *and* the outputs
the numba kernels actually produced, generated before the port landed. It
outlives the dependency.

Two details the fixture deliberately pins:

* **The histogram bins are right-closed.** ``_fast_convolve_loop`` bins with
  ``searchsorted(edges, v) - 1``, so a value equal to an interior edge lands in
  the bin *below* it and a value equal to ``edges[0]`` is dropped entirely.
  :func:`numpy.histogram` would put both somewhere else. The smallest product
  the caller feeds in is exactly ``edges[0]`` by construction, so this is a
  reachable disagreement rather than a theoretical one -- hence the dedicated
  edge case.
* **The reference for each normalisation was taken from a fresh copy.** The
  numba original divided its amplitudes through a strided *view*, rewriting the
  caller's spectrum; generating both references from one array would have
  recorded a doubly-normalised second answer as if it were correct.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence import general

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "numba_parity" / "general_kernels.npz"
)

#: Summation order differs between a nested accumulation loop and ``bincount``,
#: so the agreement is to floating-point noise rather than bit-exact.
_TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def reference():
    """The recorded numba inputs and outputs."""
    with np.load(_FIXTURE) as data:
        return {key: data[key] for key in data.files}


def test_fast_convolve_loop_matches_the_numba_reference(reference):
    """Every recorded convolution case reproduces to floating-point noise."""
    worst = 0.0
    for case in range(40):
        produced = general._fast_convolve_loop(
            reference[f"conv{case}_r_da"],
            reference[f"conv{case}_amp"],
            reference[f"conv{case}_ratio"],
            reference[f"conv{case}_weights"],
            reference[f"conv{case}_edges"],
        )
        expected = reference[f"conv{case}_expected"]
        assert produced.shape == expected.shape, f"case {case} changed shape"
        worst = max(worst, float(np.max(np.abs(produced - expected))))
    assert worst < _TOLERANCE, f"largest disagreement {worst:.3e}"


def test_fast_convolve_loop_bins_edges_the_same_way(reference):
    """Values sitting exactly on bin edges land where they used to.

    This is the case a ``numpy.histogram`` rewrite would silently get wrong: its
    bins are left-closed, the original's are right-closed, and they differ only
    here.
    """
    produced = general._fast_convolve_loop(
        reference["convedge_r_da"],
        reference["convedge_amp"],
        reference["convedge_ratio"],
        reference["convedge_weights"],
        reference["convedge_edges"],
    )
    np.testing.assert_allclose(produced, reference["convedge_expected"], atol=_TOLERANCE)


def test_fast_convolve_loop_handles_no_contributing_weights(reference):
    """All-zero weights give an all-zero histogram of the right length."""
    produced = general._fast_convolve_loop(
        reference["convedge_r_da"],
        reference["convedge_amp"],
        reference["convedge_ratio"],
        reference["convzero_weights"],
        reference["convedge_edges"],
    )
    np.testing.assert_array_equal(produced, reference["convzero_expected"])


def test_fluorescence_decay_matches_the_numba_reference(reference):
    """Every recorded decay reproduces, normalised and not."""
    worst = 0.0
    for case in range(40):
        spectrum = reference[f"decay{case}_spectrum"]
        axis = reference[f"decay{case}_axis"]
        for normalize in (True, False):
            _, produced = general.calculate_fluorescence_decay(spectrum.copy(), axis, normalize)
            expected = reference[f"decay{case}_expected_{int(normalize)}"]
            worst = max(worst, float(np.max(np.abs(produced - expected))))
    assert worst < _TOLERANCE, f"largest disagreement {worst:.3e}"


def test_fluorescence_decay_does_not_modify_its_input():
    """Asking for a decay must not renormalise the caller's spectrum.

    The numba version divided the amplitudes through ``lifetime_spectrum[0::2]``
    -- a view -- so a caller that reused its spectrum afterwards was working
    with values that had already been scaled once per call.
    """
    spectrum = np.array([1.0, 4.0, 3.0, 1.0])
    before = spectrum.copy()
    general.calculate_fluorescence_decay(spectrum, np.linspace(0, 20, 50), True)
    np.testing.assert_array_equal(spectrum, before)


def test_fluorescence_decay_is_stable_across_repeated_calls():
    """The same spectrum gives the same decay every time it is used.

    The regression this pins is the visible symptom of the in-place bug: with a
    shared view, the second call normalised already-normalised amplitudes and
    returned a different curve for identical arguments.
    """
    spectrum = np.array([1.0, 4.0, 3.0, 1.0])
    axis = np.linspace(0, 20, 64)
    _, first = general.calculate_fluorescence_decay(spectrum, axis, True)
    _, second = general.calculate_fluorescence_decay(spectrum, axis, True)
    np.testing.assert_array_equal(first, second)
