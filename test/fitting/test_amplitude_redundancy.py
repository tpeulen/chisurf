"""One amplitude per :class:`Lifetime` is held out of the optimiser.

Amplitudes are normalised by ``|a| / sum|a|``, so scaling them all by a constant
leaves the model bit-identical: n amplitude parameters carry n-1 degrees of
freedom. Handing all n to the optimiser makes the Jacobian's amplitude block
rank-deficient, and while that barely moves the fitted values it destroys their
uncertainties -- which is what gets reported.

Measured on this fixture, before and after holding one amplitude out:

===================  ==============  ==========
quantity             all n free      n-1 free
===================  ==============  ==========
``cond(J)``          5.49e7          554
amplitude error      4,801,893%      1.8%
chi2r                1.014           1.017
``tL1`` / ``tL2``    4.0089/1.2007   4.0089/1.2003
amplitude ratio      0.694384        0.693764
===================  ==============  ==========

The held-out amplitude is marked ``redundant``, not ``fixed``: :meth:`Lifetime.
update` writes the normalised values back into the parameters, and a ``fixed``
parameter ignores writes, so the stored values would drift away from the
normalised ones on every update.
"""
import numpy as np
import pytest

from test_tcspc_fit_convergence import _build, _chi2r, TRUE_AMPS, TRUE_TAUS


def _jacobian(m):
    p0 = np.asarray(m.parameter_values, dtype=float)
    m.update_model()
    r0 = np.asarray(m.weighted_residuals, dtype=float)
    jac = np.zeros((len(r0), len(p0)))
    for i in range(len(p0)):
        p = p0.copy()
        p[i] += 1e-6 * max(abs(p[i]), 1.0)
        m.parameter_values = p
        m.update_model()
        jac[:, i] = (np.asarray(m.weighted_residuals, dtype=float) - r0) / (p[i] - p0[i])
    m.parameter_values = p0
    m.update_model()
    return jac


def test_one_amplitude_is_held_out(qapp_unused=None):
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    redundant = [a for a in m.lifetimes._amplitudes if a.redundant]
    assert len(redundant) == 1
    assert redundant[0] is m.lifetimes._amplitudes[0]
    assert redundant[0] not in m.parameters, "redundant amplitude reached the optimiser"


def test_the_other_amplitude_stays_free():
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    assert m.lifetimes._amplitudes[1] in m.parameters


def test_jacobian_is_no_longer_rank_deficient():
    """The point of the change: conditioning, not the fitted values."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    cond = np.linalg.cond(_jacobian(m))
    assert cond < 1e5, f"amplitude degeneracy still present, cond(J)={cond:.3g}"


def test_fit_still_recovers_the_lifetimes():
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()
    taus = sorted(p.value for p in m.lifetimes._lifetimes)
    np.testing.assert_allclose(taus, sorted(TRUE_TAUS), rtol=0.05)
    assert _chi2r(m) < 2.0


def test_amplitudes_still_sum_to_one_and_do_not_drift():
    """``update()`` must stay idempotent — the reason for ``redundant`` != ``fixed``."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()

    first = [float(a.value) for a in m.lifetimes._amplitudes]
    assert sum(first) == pytest.approx(1.0)
    for _ in range(5):
        m.lifetimes.update()
        now = [float(a.value) for a in m.lifetimes._amplitudes]
        assert now == pytest.approx(first, abs=1e-12), "amplitudes drifted on update()"


def test_redundant_amplitude_gets_the_constrained_uncertainty():
    """For two components the fractions sum to 1, so the errors must be equal."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    fit.run()
    fit.update_error_estimates()

    a0, a1 = m.lifetimes._amplitudes
    assert a0.redundant and not a1.redundant
    assert a0.error_estimate is not None, "held-out amplitude reported no uncertainty"
    assert a0.error_estimate == pytest.approx(a1.error_estimate, rel=1e-9)
    assert a0.error_estimate < 0.1 * float(a0.value), "uncertainty still degenerate"


def test_a_single_component_holds_out_its_amplitude():
    """With one component the normalised amplitude is always 1 — no freedom at all."""
    fit, m = _build(start=[(1.0, 4.0)])
    assert m.lifetimes._amplitudes[0].redundant
    assert not [a for a in m.lifetimes._amplitudes if a in m.parameters]


def test_an_already_fixed_amplitude_pins_the_scale():
    """If the user fixed one, it is the reference — nothing else is held out."""
    fit, m = _build(start=[(1.0, 8.0), (1.0, 0.4)])
    m.lifetimes._amplitudes[0].fixed = True
    m.lifetimes.update()
    assert not [a for a in m.lifetimes._amplitudes if a.redundant]
    assert m.lifetimes._amplitudes[1] in m.parameters


def test_three_components_keep_two_degrees_of_freedom():
    fit, m = _build(start=[(0.5, 6.0), (0.3, 2.0), (0.2, 0.5)])
    amps = m.lifetimes._amplitudes
    assert sum(a.redundant for a in amps) == 1
    assert len([a for a in amps if a in m.parameters]) == 2


def test_disabling_normalisation_frees_every_amplitude():
    """The redundancy comes from the normalisation, so it goes with it."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.lifetimes.normalize_amplitudes = False
    m.lifetimes.update()
    assert not [a for a in m.lifetimes._amplitudes if a.redundant]


def test_popping_a_component_reassigns_the_hold_out():
    fit, m = _build(start=[(0.5, 6.0), (0.3, 2.0), (0.2, 0.5)])
    removed, _ = m.lifetimes.pop()
    assert not removed.redundant, "detached parameter kept the flag"
    assert sum(a.redundant for a in m.lifetimes._amplitudes) == 1


# ---------------------------------------------------------------------------
# Why one amplitude has to be held out (previously test_amplitude_degeneracy.py)
# ---------------------------------------------------------------------------


def test_scaling_all_amplitudes_leaves_the_model_unchanged():
    """The invariance itself: it is a property of the model, not the optimiser.

    This is *why* an amplitude is held out, and it stays true afterwards --
    holding one out removes the redundant coordinate, it does not remove the
    normalisation.
    """
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    m.update_model()
    before = np.array(m.y, dtype=float, copy=True)

    for p in m.lifetimes._amplitudes:
        p.value = p.value * 3.7
    m.update_model()

    np.testing.assert_allclose(
        np.asarray(m.y, dtype=float), before, rtol=1e-10,
        err_msg="scaling every amplitude must be a no-op — it is not a free DOF")


def test_lifetime_block_is_full_rank_as_a_control():
    """Guards the conditioning test above from passing for a trivial reason."""
    fit, m = _build(start=list(zip(TRUE_AMPS, TRUE_TAUS)))
    jac = _jacobian(m)
    names = [p.name for p in m.parameters]
    tau = jac[:, [names.index("tL1"), names.index("tL2")]]

    sv = np.linalg.svd(tau, compute_uv=False)
    assert sv[-1] / sv[0] > 1e-6, f"lifetime block must be full rank, {sv}"
