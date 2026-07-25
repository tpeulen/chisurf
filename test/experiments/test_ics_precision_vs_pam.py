"""Numerical parity of the RICS precision predictor against PAM/MIA RICSPE.

The reference kernels (``RICSPE.m``, ``res_covariance.m``, ``g3.m``,
``RICS_CorrFun.m``, ``nearestSPD.m``) were run unmodified in Octave and every
intermediate frozen into ``test/data/rics/pam_ricspe_reference.npz``. The
generating script is archived beside it as ``pam_ricspe_reference.m``, so the
fixture can be regenerated against any PAM checkout.

The result of that comparison, and the reason this file exists:

* The brightness correction, shape factors, volume, mean count rate, the ideal
  correlation grid and the **entire** estimator covariance agree with the
  reference to full double precision -- about 5e-13, which is the round trip
  through text.
* Exactly one kernel deviates **deliberately**: ``g3``. The reference's
  ``g3.m`` opens by converting the lag vectors to microns in place
  (``rho1 = rho1 .* S``) and then forms the time lag from the *converted*
  vector, so every tau it uses is multiplied by the pixel size in microns.
  ChiSurf forms tau from the raw lag and uses the scaled vector only for the
  spatial norms. See :func:`test_the_reference_g3_loses_its_time_dependence`
  for why that is not a matter of taste.

Layout note: the reference stores lag grids with xi along *rows* (it transposes
its meshgrid), ChiSurf with xi along *columns*. Both flatten to the same
vector -- lag ``(xi, psi)`` at index ``xi + size * psi`` -- so the covariance
orderings agree and only 2-D grids need a transpose to line up.
"""
from __future__ import annotations

import math
import pathlib

import numpy as np
import pytest

from chisurf.core.experiments.ics import precision as P

_REF = pathlib.Path(__file__).resolve().parents[1] / "data" / "rics" / "pam_ricspe_reference.npz"

pytestmark = pytest.mark.skipif(
    not _REF.exists(), reason="PAM RICSPE reference fixture not present"
)

# The settings the fixture was generated with; changing one invalidates it.
D, WR, WZ, PS = 10.0, 0.25, 1.25, 0.05
NX = NY = 16
N_PARTICLES, BRIGHTNESS = 50.0, 1e5
TP, TL = 1e-5, 1e-3
N_LAGS = 3


@pytest.fixture(scope="module")
def reference():
    """Return the frozen Octave output of the reference implementation."""
    with np.load(_REF) as fh:
        return {k: fh[k] for k in fh.files}


@pytest.fixture(scope="module")
def scalars():
    """Return the ChiSurf scalar block for the fixture's settings."""
    alpha = WZ / WR
    gamma = P.gamma_factors(False)
    volume = (NX * PS + 2) * (NY * PS + 2) * ((NX + NY) / 2 * PS)
    omega = math.pi ** 1.5 * WR ** 3 * alpha
    beta = 1.0 / alpha ** 2
    tau_c = WR ** 2 / (4.0 * D)
    rise = math.sqrt(1.0 + beta * TP / tau_c) - 1.0
    norm = beta + rise
    q = BRIGHTNESS * 4 * tau_c ** 2 * rise * (
        beta * (1 + TP / tau_c)
        * P._atanh_over_argument((1.0 - beta) * (rise / norm) ** 2) / norm
        - 1.0
    ) / (TP * beta)
    n_apparent = N_PARTICLES * BRIGHTNESS * TP / q
    m = n_apparent * omega / volume
    f = n_apparent * q * omega * gamma[0] / volume
    return dict(alpha=alpha, gamma=gamma, volume=volume, omega=omega, q=q,
                n_apparent=n_apparent, m=m, f=f)


def _g3_reference_rule(rho1, rho2, rho3, d, w, alpha, tp, tl, s):
    """``g3.m`` verbatim: the lag is converted to microns before tau is formed.

    Kept here only so the rest of the covariance can be compared against the
    reference without the one known deviation in the way.
    """
    r1 = np.asarray(rho1, float) * s
    r2 = np.asarray(rho2, float) * s
    r3 = np.asarray(rho3, float) * s
    t1 = abs(r1[0] * tp + r1[1] * tl)
    t2 = abs(r2[0] * tp + r2[1] * tl)
    t3 = abs(r3[0] * tp + r3[1] * tl)
    a1, a2, a3 = (1 + 4 * d * t / w ** 2 for t in (t1, t2, t3))
    b1, b2, b3 = (1 + 4 * d * t / (alpha * w) ** 2 for t in (t1, t2, t3))
    t7 = 8 * a1 * a2 * a3 - 8 * d * (t1 + t3) / w ** 2 - 4
    t8 = 8 * b1 * b2 * b3 - 8 * d * (t1 + t3) / (alpha * w) ** 2 - 4
    t9 = w ** 2 / 4 + 2 * d * t1
    t10 = w ** 2 / 4 + 2 * d * t2
    t11 = w ** 2 / 4 + 2 * d * t3
    t12 = w ** 2 / 2 + 2 * d * t3
    e1 = math.exp(-0.5 * float(np.dot(r2 - r3, r2 - r3)) / t12)
    v13 = r1 * t12 - r3 * w ** 2 / 4 + r2 * t10
    e2 = math.exp(-0.5 * float(np.dot(v13, v13))
                  / (t12 * (t10 * t12 + w ** 2 / 4 * t11)))
    v15 = r1 * (w ** 2 / 4 * t11 + 2 * d * t2 * t12) + r3 * w ** 4 / 16 + r2 * t11
    t17 = t9 * (t10 * t12 + w ** 2 / 4 * t11) * w ** 6 / 64 * t7
    e3 = math.exp(-0.5 * float(np.dot(v15, v15)) / t17)
    return 8.0 * e1 * e2 * e3 * t7 ** -1.0 * t8 ** -0.5


def _max_rel(a, b):
    """Return the largest relative deviation between two arrays."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    scale = np.maximum(np.abs(a), np.abs(b))
    return float(np.max(np.abs(a - b) / np.where(scale == 0, 1.0, scale)))


# --- the scalar block ------------------------------------------------------
def test_the_scalar_block_matches_the_reference(reference, scalars):
    """Shape factors, volume, the brightness correction and the count rate.

    ``q`` is the interesting one: the reference writes it with ``sqrt(1-beta)``
    inside the atanh *and* as a divisor, which is singular at a spherical focus.
    ChiSurf pulls that factor out as ``atanh(z)/z``. For an elongated focus the
    two must agree to machine precision, and this pins that they do.
    """
    (alpha, volume, omega, _beta, _tau_c, _fact, q, n_apparent, m, f,
     *gamma) = reference["scalars"]

    assert _max_rel(scalars["gamma"], gamma) < 1e-14
    assert _max_rel(scalars["volume"], volume) < 1e-14
    assert _max_rel(scalars["omega"], omega) < 1e-14
    assert _max_rel(scalars["q"], q) < 1e-11
    assert _max_rel(scalars["n_apparent"], n_apparent) < 1e-11
    assert _max_rel(scalars["m"], m) < 1e-11
    assert _max_rel(scalars["f"], f) < 1e-11


def test_the_ideal_correlation_grid_matches_the_reference(reference, scalars):
    """``correlation_grid`` reproduces the reference's ``RICS_CorrFun``.

    The (0,0) lag is excluded: both implementations drop it from the fit, the
    reference by zeroing its weight coefficient and ChiSurf by zeroing the fit
    weight, so the reference stores 0 there and ChiSurf stores the real value.
    """
    size = N_LAGS + 1
    xi, psi = np.meshgrid(np.arange(size, dtype=float), np.arange(size, dtype=float))
    mine = P.correlation_grid(xi, psi, D, WR, scalars["alpha"], TP, TL, PS) / scalars["m"]
    # reference grids are the transpose of ours; both flatten identically
    assert _max_rel(mine.T.ravel()[1:], reference["giD0"].ravel()[1:]) < 1e-11
    assert reference["giD0"][0, 0] == 0.0
    assert mine[0, 0] > 0.0


def test_the_reference_g3_helper_is_a_faithful_transcription(reference, scalars):
    """``_g3_reference_rule`` reproduces Octave's ``g3.m`` on every frozen triple.

    Without this the covariance-parity test below could pass for the wrong
    reason -- a helper that happens to agree with ChiSurf rather than with the
    reference would hide the very deviation this file documents.
    """
    devs = []
    for row in reference["g3"]:
        r1, r2, r3, value = row[0:2], row[2:4], row[4:6], row[6]
        got = _g3_reference_rule(r1, r2, r3, D, WR, scalars["alpha"], TP, TL, PS)
        devs.append(_max_rel(got, value))
    assert len(devs) >= 20
    assert max(devs) < 1e-12

    # and it is genuinely a different function from the shipped one
    worst = max(
        _max_rel(
            P.triple_correlation(row[0:2], row[2:4], row[4:6],
                                 D, WR, scalars["alpha"], TP, TL, PS),
            row[6],
        )
        for row in reference["g3"]
    )
    assert worst > 0.1, "the shipped g3 should NOT match the reference"


# --- the covariance --------------------------------------------------------
def test_the_covariance_matches_the_reference_exactly(reference, scalars, monkeypatch):
    """Full double-precision parity of the estimator covariance.

    With the reference's own ``g3`` rule installed, every one of the 256
    entries agrees to ~5e-13. That covers the master-grid slicing that replaced
    the reference's four nested loops, the closed-form pair counts, the
    placement of the shot term, term2, term3 and the symmetrisation -- i.e.
    everything except the one deliberate deviation.
    """
    monkeypatch.setattr(P, "triple_correlation", _g3_reference_rule)
    cov = P.correlation_covariance(
        N_LAGS, NX, NY, D, scalars["f"], WR, scalars["alpha"], TP, TL, PS,
        scalars["m"], scalars["q"], scalars["gamma"],
    )
    assert cov.shape == reference["covariance"].shape
    assert _max_rel(cov, reference["covariance"]) < 1e-11


def test_the_only_deviation_from_the_reference_is_g3(reference, scalars):
    """As shipped, the covariance differs from the reference only on term1.

    ``term1`` is the shot-noise term, the only place ``g3`` enters, and it is
    non-zero only on the diagonal (``nu == xi and mu == psi``). Everything
    off that diagonal must therefore still be at full parity.
    """
    cov = P.correlation_covariance(
        N_LAGS, NX, NY, D, scalars["f"], WR, scalars["alpha"], TP, TL, PS,
        scalars["m"], scalars["q"], scalars["gamma"],
    )
    ref = reference["covariance"]
    off = ~np.eye(ref.shape[0], dtype=bool)
    assert _max_rel(cov[off], ref[off]) < 1e-11

    # ... and on the diagonal the deviation stays small: it is one additive
    # term among three, so a large change in g3 moves the total by <1 %.
    assert _max_rel(np.diag(cov), np.diag(ref)) < 0.01


# --- why g3 deviates -------------------------------------------------------
def test_the_reference_g3_loses_its_time_dependence(scalars):
    """The reference's ``g3`` stops decorrelating as the pixel size shrinks.

    Because its tau carries a factor of the pixel size, shrinking the pixel
    while holding the *line lag* fixed drives every time lag to zero. Two time
    points many diffusion times apart then correlate perfectly, which no
    diffusing sample does. ChiSurf's tau does not depend on the pixel size, so
    it converges to the finite value the time lag implies.
    """
    alpha = scalars["alpha"]
    lag = (0, 20)  # 20 line times = 20 ms, about 13 diffusion times
    ref_tail = [_g3_reference_rule(lag, (0, 0), lag, D, WR, alpha, TP, TL, s)
                for s in (1e-3, 1e-4, 1e-6)]
    mine_tail = [P.triple_correlation(lag, (0, 0), lag, D, WR, alpha, TP, TL, s)
                 for s in (1e-3, 1e-4, 1e-6)]

    assert ref_tail[-1] > 0.999, "the reference should tend to perfect correlation"
    assert max(mine_tail) < 0.01, "chisurf should stay decorrelated"
    # and ChiSurf's limit is a limit, not a drift
    assert abs(mine_tail[-1] - mine_tail[-2]) / mine_tail[-1] < 1e-3


def test_g3_agrees_with_the_two_point_function_on_the_same_time_scale(scalars):
    """``g3`` must decay on the diffusion time, like the ``g1`` beside it.

    ``res_covariance`` builds its two-point correlation from the *raw* lag, so
    within the reference itself g1 and g3 disagree about what tau means. Held
    at a negligible pixel size, the reference's g3 is still at ~1.0 where its
    own g1 has already fallen by 40 %; ChiSurf's decays alongside it.
    """
    alpha, tiny = scalars["alpha"], 1e-6
    for psi in (1, 2, 4):
        g1 = float(P.correlation_grid(np.array(0.0), np.array(float(psi)),
                                      D, WR, alpha, TP, TL, tiny))
        mine = P.triple_correlation((0, psi), (0, 0), (0, psi),
                                    D, WR, alpha, TP, TL, tiny)
        ref = _g3_reference_rule((0, psi), (0, 0), (0, psi),
                                 D, WR, alpha, TP, TL, tiny)
        assert g1 < 0.7, "the two-point function should have decayed"
        assert mine < g1, "g3 decays at least as fast as g1"
        assert ref > 0.999, "the reference's g3 has not decayed at all"


def test_the_deviation_does_not_change_the_advice(scalars, monkeypatch):
    """Both conventions pick the same dwell time, so the fix is safe.

    ``g3`` only enters one of three additive terms on the covariance diagonal,
    so a large relative change in it moves the predicted error by well under
    the Monte-Carlo uncertainty the prediction already carries.
    """
    from chisurf.plugins.microscopy.img_precision import core as pc

    common = dict(nx=32, ny=32, pixel_size=PS, n_particles=N_PARTICLES,
                  w_r=WR, w_z=WZ, brightness=BRIGHTNESS, n_images=100,
                  n_lags=3, n_repeats=40, seed=1)
    grid = pc.default_dwell_range(5)

    shipped = pc.sweep_dwell(D, grid, **common)
    monkeypatch.setattr(P, "triple_correlation", _g3_reference_rule)
    bug_compatible = pc.sweep_dwell(D, grid, **common)

    assert shipped.best_dwell == bug_compatible.best_dwell
    ratio = shipped.best_error / bug_compatible.best_error
    assert 0.8 < ratio < 1.25, f"predicted error moved by {ratio:.2f}x"
