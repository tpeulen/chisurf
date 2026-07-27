"""The G-factor has to correct the same channel in numerator and denominator.

``LifetimeModel._tcspc_rt_curves`` turns a measured VV/VH pair into r(t). It
used to compute ``(VV - VH) / (g VV + 2 VH)`` — the denominator corrected, the
numerator raw — which agrees with the truth only at ``g = 1`` and otherwise
reports anisotropy where there is none.

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

#: chisurf's G is the perpendicular/parallel ratio — the convention
#: ``compute_g_factor_perrin`` returns.
G_FACTOR = S_PERPENDICULAR / S_PARALLEL


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
        vh = np.full(2, sensitivity * 1.0)
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


def test_the_leakage_correction_changes_the_curve_and_stays_finite():
    """With l1/l2 non-zero the corrected branch must differ, and be usable.

    Deliberately *not* asserted against a constructed truth: doing so requires
    committing to an order — whether the polarisation leakage happens before or
    after the detectors' sensitivity difference — and the two give different
    answers. The code unmixes the raw pair and applies G afterwards, which is
    self-consistent only under one of those readings. That question is recorded
    in known-issues rather than frozen here by a test that would simply restate
    whichever order the implementation happens to use.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    vv, vh = _measured(0.25)
    _, r_unc, r_cor = LifetimeModel._tcspc_rt_curves(
        t=np.array([1.0, 2.0, 3.0]), vv=np.full(3, vv), vh=np.full(3, vh),
        g=G_FACTOR, l1=0.03, l2=0.05,
    )
    assert np.all(np.isfinite(r_cor))
    assert r_cor[0] != pytest.approx(r_unc[0])
    assert r_unc[0] == pytest.approx(0.25, abs=1e-9)     # no leakage in the input
