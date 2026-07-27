"""The G-factor has to correct the same channel in numerator and denominator.

``LifetimeModel._tcspc_rt_curves`` turns a measured VV/VH pair into r(t) with
the Schaffer/Eggeling equation. It used to compute ``(VV - VH) / (g VV + 2 VH)``
— the denominator corrected, the numerator raw — which agrees with the truth
only at ``g = 1`` and otherwise reports anisotropy where there is none.

The tests build the measurement instead of asserting a formula: pick a true
anisotropy, split it into parallel and perpendicular intensities, scale each by
its detector's sensitivity, and require the recovered r to be the one we started
from. That is independent of which algebraic form is used, so it stays valid if
the expression is ever rewritten.
"""

import numpy as np
import pytest

#: Detection sensitivities of the parallel and perpendicular channels.
S_PARALLEL, S_PERPENDICULAR = 1.0, 0.65

#: G is the parallel/perpendicular ratio — Schaffer/Eggeling, and the
#: convention tttrlib's estimators and ``compute_g_factor_perrin`` share.
G_FACTOR = S_PARALLEL / S_PERPENDICULAR


def _measured(r_true):
    """Return the (VV, VH) a detector pair would record for ``r_true``."""
    intensity_parallel = 1.0 + 2.0 * r_true
    intensity_perpendicular = 1.0 - r_true
    return (S_PARALLEL * intensity_parallel,
            S_PERPENDICULAR * intensity_perpendicular)


def _recover(r_true, l1=0.0, l2=0.0):
    """Return ``(r_uncorrected, r_corrected)`` for a constructed measurement."""
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    vv, vh = _measured(r_true)
    t = np.array([1.0, 2.0, 3.0])
    _, r_unc, r_cor = LifetimeModel._tcspc_rt_curves(
        t=t, vv=np.full(3, vv), vh=np.full(3, vh), g=G_FACTOR, l1=l1, l2=l2
    )
    return float(r_unc[0]), float(r_cor[0])


@pytest.mark.parametrize("r_true", [0.0, 0.05, 0.2, 0.38, -0.1])
def test_the_measured_anisotropy_is_the_one_that_was_put_in(r_true):
    """Recovery is exact for any anisotropy, including zero and negative."""
    r_unc, r_cor = _recover(r_true)
    assert r_unc == pytest.approx(r_true, abs=1e-9)
    assert r_cor == pytest.approx(r_true, abs=1e-9)


def test_an_isotropic_sample_reads_zero_whatever_the_g_factor():
    """The case that exposed the bug: no anisotropy must measure as none.

    With the G-factor on only one side of the fraction, an isotropic sample read
    +0.167 at g = 2 — an artefact indistinguishable from real, slow-tumbling
    signal.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    t = np.array([1.0, 2.0])
    for sensitivity in (0.5, 0.65, 1.0, 1.4, 2.0):
        vv = np.full(2, 1.0)                       # isotropic: equal true intensities
        vh = np.full(2, 1.0 / sensitivity)
        _, r_unc, _ = LifetimeModel._tcspc_rt_curves(
            t=t, vv=vv, vh=vh, g=sensitivity, l1=0.0, l2=0.0
        )
        assert r_unc[0] == pytest.approx(0.0, abs=1e-12), f"g = {sensitivity}"


def test_g_of_one_is_unchanged():
    """The old expression was right at g = 1, and the new one must agree there.

    This is why the fault survived: the default G is 1, so every default-run
    number was correct and only calibrated setups were wrong.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    t = np.array([1.0, 2.0])
    vv, vh = np.full(2, 1.4), np.full(2, 0.8)
    _, r_unc, _ = LifetimeModel._tcspc_rt_curves(t=t, vv=vv, vh=vh, g=1.0, l1=0.0, l2=0.0)
    assert r_unc[0] == pytest.approx((1.4 - 0.8) / (1.4 + 2 * 0.8))


def test_it_is_the_published_equation_with_the_reciprocal_g():
    """Agrees term for term with Schaffer/Eggeling/Seidel, JPCA 103 (1999) 331.

    ``r = (Fp - G Fs) / ((1 - 3 l2) Fp + (2 - 3 l1) G Fs)``, term for term and
    with the *same* G — the ratio a paper quotes can be typed straight in, and
    is the number tttrlib's estimators take.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    fp, fs = 1.4, 0.52
    t = np.array([1.0, 2.0])
    for G in (0.8, 1.0, 1.3, 1.9):
        for l1, l2 in ((0.0, 0.0), (0.03, 0.05), (0.02, 0.01)):
            published = (fp - G * fs) / ((1 - 3 * l2) * fp + (2 - 3 * l1) * G * fs)
            _, _, r_cor = LifetimeModel._tcspc_rt_curves(
                t=t, vv=np.full(2, fp), vh=np.full(2, fs),
                g=G, l1=l1, l2=l2,
            )
            assert r_cor[0] == pytest.approx(published, abs=1e-12), f"G={G} l1={l1} l2={l2}"


def test_the_curve_agrees_with_the_integrals_module(qapp=None):
    """One anisotropy equation, two call sites, the same number.

    ``anisotropy_from_integrals`` is the other implementation; a difference
    between them would mean the curve on screen and the reported steady-state
    value disagree about the same measurement.
    """
    from chisurf.core.fluorescence.anisotropy.integrals import anisotropy_from_integrals
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    for r_true, l1, l2 in ((0.0, 0.0, 0.0), (0.2, 0.0, 0.0),
                           (0.25, 0.03, 0.05), (0.38, 0.02, 0.01)):
        vv, vh = _measured(r_true)
        _, _, r_cor = LifetimeModel._tcspc_rt_curves(
            t=np.array([1.0, 2.0]), vv=np.full(2, vv), vh=np.full(2, vh),
            g=G_FACTOR, l1=l1, l2=l2,
        )
        reference = anisotropy_from_integrals(
            s_p=np.full(2, vv), s_s=np.full(2, vh), G=G_FACTOR, l1=l1, l2=l2
        )
        assert r_cor[0] == pytest.approx(reference.r_e, abs=1e-12)


def test_the_generator_round_trips_at_any_g():
    """chisurf's own forward model must invert to the anisotropy it was given.

    ``vm_rt_to_vv_vh`` is where the convention is stated in code, and it is the
    same forward model tttrlib fits: ``VV = vm(1 + (2-3 l1) r)`` and
    ``VH = vm(1 - (1-3 l2) r)/G``. A round trip through it checks the whole
    chain, not just that one formula matches another — and it must hold with a
    non-unit G *and* non-zero mixing at once, which is the combination that
    exposed the previous parameterisation.
    """
    from chisurf.core.fluorescence.anisotropy.decay import vm_rt_to_vv_vh
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    t, vm, r0 = np.array([0.0, 1.0, 2.0]), np.ones(3), 0.30
    for g in (0.65, 1.0, 1.5, 2.2):
        for l1, l2 in ((0.0, 0.0), (0.03, 0.05), (0.08, 0.02)):
            vv, vh = vm_rt_to_vv_vh(t, vm, np.array([r0, 1e12]), g_factor=g, l1=l1, l2=l2)
            _, _, r_cor = LifetimeModel._tcspc_rt_curves(t=t, vv=vv, vh=vh, g=g, l1=l1, l2=l2)
            assert r_cor[0] == pytest.approx(r0, abs=1e-9), f"g={g} l1={l1} l2={l2}"


def test_the_calibration_returns_the_ratio_the_consumers_expect():
    """``compute_g_factor_perrin`` must return S_par/S_perp, not its reciprocal.

    The same stored number reaches tttrlib's estimators and the VM combination
    `vv + 2 G vh`; returning the inverse silently inverted the correction for
    every one of them.
    """
    from chisurf.core.fluorescence.anisotropy.integrals import (
        anisotropy_from_integrals,
        compute_g_factor_perrin,
        perrin_steady_state_anisotropy,
    )

    tau, rho, r0 = 3.2, 6.8, 0.38
    r_true = perrin_steady_state_anisotropy(tau=tau, rho=rho, r0=r0)
    sp = S_PARALLEL * (1 + 2 * r_true)
    ss = S_PERPENDICULAR * (1 - r_true)

    g = compute_g_factor_perrin(sp, ss, tau=tau, rho=rho, r0=r0)
    assert g == pytest.approx(S_PARALLEL / S_PERPENDICULAR)

    # It closes the loop with its own consumer ...
    assert anisotropy_from_integrals(sp, ss, G=g).r_e == pytest.approx(r_true)
    # ... with tttrlib's estimator, which takes the same ratio ...
    assert (sp - g * ss) / (sp + 2 * g * ss) == pytest.approx(r_true)
    # ... and with the VM / total-intensity combination used across the readers.
    assert sp + 2 * g * ss == pytest.approx((1 + 2 * r_true) + 2 * (1 - r_true))
