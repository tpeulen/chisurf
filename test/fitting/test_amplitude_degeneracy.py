"""The lifetime amplitude block is exactly scale-invariant.

``Lifetime.amplitudes`` normalises by ``|a| / sum|a|``, and the decay is *also*
autoscaled to the data (``rescale_w_bg``, enabled by fixing ``n0``). So the
overall amplitude scale is redundant twice over: n amplitude parameters carry
n-1 degrees of freedom, and the "scale all amplitudes together" direction has
exactly zero gradient.

This is not a hypothetical. At equal starting amplitudes the two amplitude
Jacobian columns are exact mirror images, leaving the block rank-deficient and
LM's normal equations singular in that direction.

**Removing the redundancy does not fix convergence.** Pinning one amplitude was
measured across 24 randomised starts: parameter recovery was 16/24 either way.
It moves median chi2r 2.98 -> 1.01 (the nuisance parameters ``sc``/``bg``
converge better once conditioning improves) at ~24% more fit time, but the
lifetimes -- the thing being measured -- are unaffected. That is why the
parameterisation is left as-is and this file pins the behaviour instead of
asserting a fix.
"""
import numpy as np
import pytest

from test_tcspc_fit_convergence import _build, TRUE_AMPS, TRUE_TAUS


def _jacobian(m):
    """Forward-difference Jacobian of the weighted residuals."""
    p0 = np.asarray(m.parameter_values, dtype=float)
    m.update_model()
    r0 = np.asarray(m.weighted_residuals, dtype=float)
    jac = np.zeros((len(r0), len(p0)))
    for i in range(len(p0)):
        p = p0.copy()
        h = 1e-6 * max(abs(p[i]), 1.0)
        p[i] += h
        m.parameter_values = p
        m.update_model()
        jac[:, i] = (np.asarray(m.weighted_residuals, dtype=float) - r0) / h
    m.parameter_values = p0
    m.update_model()
    return jac, [p.name for p in m.parameters]


def test_equal_amplitudes_give_antiparallel_jacobian_columns():
    """The degeneracy, stated precisely: the columns are mirror images."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    jac, names = _jacobian(m)
    c1 = jac[:, names.index("xL1")]
    c2 = jac[:, names.index("xL2")]

    # Analytically the columns are identical in magnitude; the tolerance here is
    # set by forward-difference truncation (~1e-6 relative), not by the property.
    assert np.linalg.norm(c1) == pytest.approx(np.linalg.norm(c2), rel=1e-5), (
        "equal amplitudes must give equal-magnitude Jacobian columns")

    cos = float(c1 @ c2 / (np.linalg.norm(c1) * np.linalg.norm(c2)))
    assert cos == pytest.approx(-1.0, abs=1e-6), (
        f"amplitude columns should be exactly anti-parallel, cos={cos:.9f}")


def test_scaling_all_amplitudes_leaves_the_model_unchanged():
    """The null direction, shown directly rather than through the Jacobian."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.update_model()
    before = np.array(m.y, dtype=float, copy=True)

    for p in m.lifetimes._amplitudes:
        p.value = p.value * 3.7
    m.update_model()

    np.testing.assert_allclose(
        np.asarray(m.y, dtype=float), before, rtol=1e-10,
        err_msg="scaling every amplitude must be a no-op — it is not a free DOF")


def test_amplitude_block_is_rank_deficient_by_one():
    """n amplitude parameters, n-1 degrees of freedom."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    jac, names = _jacobian(m)
    amp = jac[:, [names.index("xL1"), names.index("xL2")]]

    sv = np.linalg.svd(amp, compute_uv=False)
    assert sv[0] > 0
    assert sv[-1] / sv[0] < 1e-6, (
        f"amplitude block should be numerically rank 1, singular values {sv}")


def test_lifetime_block_is_full_rank_as_a_control():
    """Guards against the above passing for a trivial reason."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    jac, names = _jacobian(m)
    tau = jac[:, [names.index("tL1"), names.index("tL2")]]

    sv = np.linalg.svd(tau, compute_uv=False)
    assert sv[-1] / sv[0] > 1e-6, (
        f"lifetime block must be full rank, singular values {sv}")
