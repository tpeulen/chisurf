"""One amplitude of a lifetime view is held fixed as the scale reference.

Amplitudes enter the decay only as fractions ``a_i / sum a`` (the photon count
``n0`` carries the scale), so scaling them all by a constant leaves the model
bit-identical: n amplitude parameters carry n-1 degrees of freedom. Handing all
n to the optimiser makes the Jacobian's amplitude block rank-deficient, which
destroys the reported uncertainties. The view therefore holds
``lifetime.amplitude.0`` fixed; the others stay free.
"""

import numpy as np

from .test_tcspc_fit_convergence import TRUE_AMPS, TRUE_TAUS, _build, _chi2r


def _by_id(m):
    return {p.canonical_id: p for p in m.parameters_all}


def _amplitudes(m):
    return [p for p in m.parameters_all if p.canonical_id.startswith("lifetime.amplitude.")]


def _free(m):
    return [p for p in m.parameters_all if not p.fixed and not p.canonical_id.startswith("output.")]


def _jacobian(m):
    free = _free(m)
    p0 = np.array([p.value for p in free], dtype=float)
    m.update()
    r0 = np.asarray(m.weighted_residuals, dtype=float)
    jac = np.zeros((len(r0), len(p0)))
    for i, p in enumerate(free):
        step = 1e-3 * max(abs(p0[i]), 1.0)
        p.value = p0[i] + step
        m.update()
        jac[:, i] = (np.asarray(m.weighted_residuals, dtype=float) - r0) / step
        p.value = p0[i]
    m.update()
    return jac, [p.canonical_id for p in free]


def test_the_first_amplitude_is_held_and_the_other_stays_free():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    p = _by_id(m)
    assert p["lifetime.amplitude.0"].fixed
    assert not p["lifetime.amplitude.1"].fixed


def test_three_components_keep_two_degrees_of_freedom():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.structure = "lifetime.components.3"
    amps = _amplitudes(m)
    assert len(amps) == 3
    assert [a.fixed for a in amps] == [True, False, False]


def test_scaling_all_amplitudes_leaves_the_model_unchanged():
    """The invariance itself -- the reason one amplitude is held."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    before = np.array(m.y, dtype=float, copy=True)
    for a in _amplitudes(m):
        a.value = a.value * 3.7
    m.update()
    np.testing.assert_allclose(np.asarray(m.y, dtype=float), before, rtol=1e-10)


def test_jacobian_is_not_rank_deficient():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    jac, names = _jacobian(m)
    assert "lifetime.amplitude.0" not in names
    sv = np.linalg.svd(jac, compute_uv=False)
    assert sv[-1] / sv[0] > 1e-8, f"degenerate free block: {dict(zip(names, sv))}"


def test_fit_recovers_lifetimes_and_amplitude_ratio():
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()
    p = _by_id(m)
    taus = [p["lifetime.tau.0"].value, p["lifetime.tau.1"].value]
    order = np.argsort(taus)
    np.testing.assert_allclose(np.asarray(taus)[order], sorted(TRUE_TAUS), rtol=0.05)
    amps = np.array([p["lifetime.amplitude.0"].value, p["lifetime.amplitude.1"].value])[order]
    true = np.asarray(TRUE_AMPS)[np.argsort(TRUE_TAUS)]
    np.testing.assert_allclose(amps / amps.sum(), true / true.sum(), atol=0.02)
    assert _chi2r(fit) < 2.0
