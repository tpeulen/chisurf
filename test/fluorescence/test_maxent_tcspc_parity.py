"""The maximum-entropy design matrices survived moving into the photon library.

``maxent_decay``'s solver used to carry three numba kernels -- a fractional IRF
shift and the single-shot and periodic exponential convolutions -- and built its
design matrix one column at a time on top of them. The kernels are gone; the
matrix now comes from ``tttrlib.tcspc_build_fi_lifetimes`` /
``tcspc_build_fi_distances`` in a single call.

**The reference is a committed fixture, not a live comparison.** Checking against
numba at test time would evaporate as a skip that reads like a pass on the day
numba leaves the environment, which is the whole point of the exercise.
``test/data/numba_parity/maxent_tcspc.npz`` holds inputs *and* the outputs the
numba solver actually produced, recorded before the port landed.

Two things the fixture deliberately pins:

* **The design matrix, not only the kernels.** Column *j* is one convolution,
  and a kernel that agrees case-by-case can still be assembled into the wrong
  column -- the distance builder mixes two curves per column and divides by a
  Poisson weight.
* **Delegating per column is not the same change.** It was measured at 10.6x
  *slower* than numba (a 512-element argument marshals in ~30 us against a ~3 us
  kernel), which is why the whole matrix crosses the boundary at once and why
  the fixture covers the builders rather than the three kernels alone.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.maxent_decay.core import solver

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "data"
    / "numba_parity"
    / "maxent_tcspc.npz"
)

#: The compiled convolution contracts its multiply-add where the interpreted one
#: did not, so the agreement is floating-point noise rather than bit-exact. It is
#: measured at 2.2e-15 relative on every recorded matrix; the threshold leaves
#: room for a different libm.
_TOLERANCE = 1e-12


@pytest.fixture(scope="module")
def reference():
    """The recorded numba inputs and outputs."""
    with np.load(_FIXTURE) as data:
        return {key: data[key] for key in data.files}


def _design_cases(reference):
    """Yield ``(index, kind, kwargs)`` for every recorded design matrix."""
    for i in range(int(reference["n_design"])):
        kind = str(reference[f"design{i}_kind"])
        keys = [
            k.split("_", 1)[1]
            for k in reference
            if k.startswith(f"design{i}_")
            and k.split("_", 1)[1] not in ("kind", "Fi", "y", "sigma", "fit_additive")
        ]
        yield i, kind, {k: reference[f"design{i}_{k}"] for k in keys}


def test_the_fixture_covers_both_axes_and_both_convolutions(reference):
    """A shrunk fixture that lost its periodic cases would still pass silently."""
    kinds = {str(reference[f"design{i}_kind"]) for i in range(int(reference["n_design"]))}
    periods = {float(reference[f"design{i}_period"]) for i in range(int(reference["n_design"]))}
    assert kinds == {"life", "dist"}
    assert periods == {0.0, 16.0}


def test_lifetime_design_matrix_matches_the_numba_reference(reference):
    """Every recorded lifetime matrix reproduces to floating-point noise."""
    decay, lamp = reference["decay"], reference["irf"]
    seen = 0
    for i, kind, kw in _design_cases(reference):
        if kind != "life":
            continue
        seen += 1
        Fi, y, sigma, add = solver._build_Fi_lifetimes(
            decay,
            lamp,
            float(kw["dt"]),
            kw["tau"],
            float(kw["timeshift"]),
            float(kw["background"]),
            float(kw["lamp_scatter"]),
            int(kw["fitstart"]),
            int(kw["fitstop"]),
            float(kw["period"]),
        )
        np.testing.assert_allclose(Fi, reference[f"design{i}_Fi"], rtol=_TOLERANCE)
        np.testing.assert_allclose(y, reference[f"design{i}_y"], rtol=0.0)
        np.testing.assert_allclose(sigma, reference[f"design{i}_sigma"], rtol=1e-15)
        np.testing.assert_allclose(
            add, reference[f"design{i}_fit_additive"], rtol=_TOLERANCE
        )
    assert seen == 2


def test_distance_design_matrix_matches_the_numba_reference(reference):
    """Including the two-component donor-only reference, which mixes per column."""
    decay, lamp = reference["decay"], reference["irf"]
    seen = 0
    for i, kind, kw in _design_cases(reference):
        if kind != "dist":
            continue
        seen += 1
        Fi, y, sigma, add = solver._build_Fi_distances(
            decay,
            lamp,
            float(kw["dt"]),
            kw["R"],
            float(kw["tau0"]),
            float(kw["R0"]),
            kw["donly"],
            float(kw["x_donly"]),
            float(kw["timeshift"]),
            float(kw["background"]),
            float(kw["lamp_scatter"]),
            int(kw["fitstart"]),
            int(kw["fitstop"]),
            float(kw["period"]),
            float(kw["irf_background"]),
        )
        np.testing.assert_allclose(Fi, reference[f"design{i}_Fi"], rtol=_TOLERANCE)
        np.testing.assert_allclose(y, reference[f"design{i}_y"], rtol=0.0)
        np.testing.assert_allclose(sigma, reference[f"design{i}_sigma"], rtol=1e-15)
        np.testing.assert_allclose(
            add, reference[f"design{i}_fit_additive"], rtol=_TOLERANCE
        )
    assert seen == 4


def test_the_builders_still_reject_what_they_used_to_reject(reference):
    """Validation stayed in ChiSurf; the compiled builder does not repeat all of it."""
    decay, lamp = reference["decay"], reference["irf"]
    dt = float(reference["dt"])

    with pytest.raises(ValueError):
        solver._build_Fi_lifetimes(decay, lamp, dt, np.array([]), 0.0, 0.0, 0.0, 0, 100, 0.0)
    with pytest.raises(ValueError):
        # a grid that is entirely non-positive is empty once filtered
        solver._build_Fi_lifetimes(
            decay, lamp, dt, np.array([-1.0, 0.0]), 0.0, 0.0, 0.0, 0, 100, 0.0
        )
    with pytest.raises(ValueError):
        solver._build_Fi_distances(
            decay, lamp, dt, np.array([50.0]), 4.1, 52.0, np.array([1.0]), 0.0,
            0.0, 0.0, 0.0, 0, 100, 0.0, 0.0,
        )
    with pytest.raises(ValueError):
        solver._build_Fi_distances(
            decay, lamp, dt, np.array([50.0, -1.0]), 4.1, 52.0, np.array([1.0, 4.1]),
            0.0, 0.0, 0.0, 0.0, 0, 100, 0.0, 0.0,
        )


def test_a_non_positive_lifetime_is_dropped_not_convolved(reference):
    """The filter is ChiSurf's; the compiled builder would divide by zero."""
    decay, lamp = reference["decay"], reference["irf"]
    dt = float(reference["dt"])
    tau = np.array([2.0, -1.0, 3.0, 0.0])
    Fi, _, _, _ = solver._build_Fi_lifetimes(
        decay, lamp, dt, tau, 0.0, 0.0, 0.0, 10, 100, 0.0
    )
    assert Fi.shape[1] == 2
    assert np.all(np.isfinite(Fi))
