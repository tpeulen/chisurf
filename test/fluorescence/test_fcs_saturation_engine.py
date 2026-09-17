"""The saturated FCS forward model runs in imp.bff — pinned against numpy.

Ported on the owner's placement ruling (2026-09-02): a forward model belongs
in bff regardless of how fast its Python is. The chisurf orchestrators
(`saturated_curve_shape`, `compute_bunching_factor`, `gaussian_g_diff`)
forward to the engine; the numpy building blocks they used to compose stay
for the analysis utilities (power sweeps, calculator plugin) and double as
this A/B's reference.
"""

import IMP.bff as bff
import numpy as np
import pytest

from chisurf.core.fluorescence.fcs import saturation as sat

TAU = np.logspace(-7, -1, 61)
# K[target, source]: excitation 0->1, emission 1->0, ISC 1->2, return 2->0.
DARK = np.array([[0, 1e8, 5e4], [0, 0, 0], [0, 2e5, 0]], float)
EXC = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 0]], float)
Q = np.array([0.0, 1.0, 0.0])
KW = dict(w0=0.25e-6, z0=1.25e-6, D=4.0e-10)


def _reference_shape(brightness_b=None, power=20e-6, include_bunching=True):
    """The numpy pipeline, composed from the surviving building blocks."""
    k0 = sat.excitation_rate_peak(power, 73000.0, KW["w0"]) if power > 0 else 0.0
    if k0 <= 0.0:
        g = (
            1.0
            / (1.0 + 4.0 * KW["D"] * TAU / KW["w0"] ** 2)
            / np.sqrt(1.0 + 4.0 * KW["D"] * TAU / KW["z0"] ** 2)
        )
    else:
        r = np.linspace(0.0, 5.0 * KW["w0"], 120)
        z = np.linspace(-5.0 * KW["z0"], 5.0 * KW["z0"], 40)
        R, Z = np.meshgrid(r, z, indexing="ij")
        k_exc = sat.excitation_rate(R, Z, KW["w0"], KW["z0"], power, 73000.0)
        profile = sat.emission_profile(k_exc, DARK, EXC, Q)
        profile_b = (
            None if brightness_b is None else sat.emission_profile(k_exc, DARK, EXC, brightness_b)
        )
        v0 = np.pi**1.5 * KW["w0"] ** 2 * KW["z0"]
        g = sat.fcs_numerical_g_diff(TAU, r, z, profile, KW["D"], v_ref=v0, profile_b=profile_b)
    if include_bunching:
        # The engine's own bunching (already pinned below) closes the loop.
        g = g * sat.compute_bunching_factor(k0, DARK, EXC, Q, TAU, brightness_b=brightness_b)
    return g


def test_j0_is_machine_precise():
    from scipy.special import j0

    x = np.linspace(0.0, 35.0, 401)
    err = max(abs(bff.bessel_j0(float(v)) - j0(v)) for v in x)
    assert err < 5e-15


@pytest.mark.parametrize("brightness_b", [None, np.array([0.0, 0.8, 0.1])])
def test_the_saturated_shape_matches_numpy(brightness_b):
    want = _reference_shape(brightness_b)
    got = sat.saturated_curve_shape(
        TAU, 20e-6, 73000.0, DARK, EXC, Q, brightness_b=brightness_b, **KW
    )
    np.testing.assert_allclose(got, want, rtol=0, atol=1e-12 * np.max(np.abs(want)))


def test_the_zero_power_limit_is_the_gaussian():
    got = sat.saturated_curve_shape(TAU, 0.0, 73000.0, DARK, EXC, Q, include_bunching=False, **KW)
    want = (
        1.0
        / (1.0 + 4.0 * KW["D"] * TAU / KW["w0"] ** 2)
        / np.sqrt(1.0 + 4.0 * KW["D"] * TAU / KW["z0"] ** 2)
    )
    np.testing.assert_allclose(got, want, rtol=1e-14)


def test_bunching_handles_complex_relaxation_modes():
    """A near-unidirectional cycle's generator has complex eigenvalue pairs;
    the factor is real regardless, and must match an independent numpy eigen
    transcription (independent because the chisurf function now forwards to
    the same engine under test).
    """
    cyc = np.array([[0, 0, 9e5], [8e5, 0, 0], [0, 7e5, 0]], float)
    q = np.array([1.0, 0.2, 0.05])
    K = _generator(cyc)
    evals, evecs = np.linalg.eig(K)
    assert np.iscomplex(evals).any(), "the fixture must exercise complex modes"

    # Independent reference: stationary state + eigen expansion, numpy only.
    K_eq = K.copy()
    K_eq[-1, :] = 1.0
    b = np.zeros(3)
    b[-1] = 1.0
    p_eq = np.linalg.solve(K_eq, b)
    p_eq = np.maximum(p_eq, 0.0)
    p_eq /= p_eq.sum()
    norm = float(q @ p_eq) ** 2
    ev = np.minimum(evals.real, 0.0) + 1j * evals.imag
    c_m = (q @ evecs) * np.linalg.solve(evecs, q * p_eq)
    want = np.real(c_m @ np.exp(ev[:, None] * TAU[None, :])) / norm

    got = np.asarray(
        bff.fcs_bunching_factor(
            [float(v) for v in TAU],
            0.0,
            [float(v) for v in cyc.ravel()],
            [0.0] * 9,
            3,
            [float(v) for v in q],
        )
    )
    np.testing.assert_allclose(got, want, rtol=1e-9)
    assert got[-1] == pytest.approx(1.0, abs=1e-6)


def _generator(m):
    k = np.array(m, float)
    np.fill_diagonal(k, 0.0)
    np.fill_diagonal(k, -k.sum(axis=0))
    return k
