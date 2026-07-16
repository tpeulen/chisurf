"""General matrix-based FRET correction.

The scalar Hellenkamp factors (alpha/beta/gamma/delta) are the two-colour
reduction of a correction stated in terms of the light-path **excitation** and
**emission** crosstalk matrices. These tests check that

1. for two colours the matrix form is algebraically identical to
   :func:`corrected_es`, and
2. the matrix form recovers pairwise efficiencies in a three-chromophore system
   with acceptor->acceptor spectral leakage, which the scalar per-pair factors
   cannot express.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.es import (
    corrected_es,
    corrected_es_general,
    corrected_es_matrix,
)


@pytest.mark.parametrize("e_true", [0.2, 0.4, 0.75])
def test_two_colour_matrix_reduces_to_corrected_es(e_true):
    """emission=[[1, α], [0, γ]], excitation=[[1, δ], [0, 1]] reproduces corrected_es."""
    alpha, delta, gamma = 0.08, 0.05, 1.4
    tot = 1000.0

    # forward model in true-emission units, then apply the emission matrix
    e_emit = np.array([
        [(1 - e_true) * tot, e_true * tot + delta * tot],  # donor laser
        [0.0, tot],                                        # acceptor laser
    ])
    emission = np.array([[1.0, alpha], [0.0, gamma]])      # chromophore x detector
    excitation = np.array([[1.0, delta], [0.0, 1.0]])      # laser x chromophore
    inten = e_emit @ emission                              # I[laser, detector]

    e_general = corrected_es_general(inten, excitation, emission)[(0, 1)]["E"]

    # scalar path from the same measured channels
    scalar = corrected_es(
        inten[0, 0], inten[0, 1], inten[1, 1],
        gamma=gamma, alpha=alpha, delta=delta,
    )["E"]

    assert float(e_general) == pytest.approx(e_true, abs=1e-9)
    assert float(e_general) == pytest.approx(float(scalar), abs=1e-9)


@pytest.mark.parametrize("e01,e02", [(0.3, 0.4), (0.6, 0.1), (0.25, 0.25)])
def test_three_colour_with_inter_acceptor_leakage(e01, e02):
    """Donor feeds two acceptors whose emission channels also bleed into each other."""
    tot = 1000.0
    # laser x chromophore: donor laser directly excites both acceptors a little
    excitation = np.array([
        [1.0, 0.04, 0.03],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    # chromophore x detector: note the off-diagonal acceptor<->acceptor leakage
    emission = np.array([
        [1.0, 0.05, 0.02],
        [0.0, 1.3, 0.15],   # acceptor 1 bleeds into channel 2
        [0.0, 0.10, 0.9],   # acceptor 2 bleeds into channel 1
    ])

    # true emission per (laser, chromophore)
    e_emit = np.array([
        [(1 - e01 - e02) * tot,
         e01 * tot + excitation[0, 1] / excitation[1, 1] * tot,
         e02 * tot + excitation[0, 2] / excitation[2, 2] * tot],
        [0.0, tot, 0.0],
        [0.0, 0.0, tot],
    ])
    inten = e_emit @ emission  # I[laser, detector]

    res = corrected_es_general(inten, excitation, emission, pairs=[(0, 1), (0, 2)])
    assert float(res[(0, 1)]["E"]) == pytest.approx(e01, abs=1e-6)
    assert float(res[(0, 2)]["E"]) == pytest.approx(e02, abs=1e-6)


def test_scalar_matrix_path_is_biased_by_inter_acceptor_leakage():
    """The scalar N-cube path cannot undo acceptor<->acceptor bleed; general can."""
    e01, e02 = 0.4, 0.3
    tot = 1000.0
    excitation = np.array([
        [1.0, 0.04, 0.03],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    emission = np.array([
        [1.0, 0.05, 0.02],
        [0.0, 1.3, 0.15],
        [0.0, 0.35, 0.9],   # strong acceptor 2 -> channel 1 bleed
    ])
    e_emit = np.array([
        [(1 - e01 - e02) * tot,
         e01 * tot + excitation[0, 1] / excitation[1, 1] * tot,
         e02 * tot + excitation[0, 2] / excitation[2, 2] * tot],
        [0.0, tot, 0.0],
        [0.0, 0.0, tot],
    ])
    inten = e_emit @ emission

    # general form: exact
    gen = corrected_es_general(inten, excitation, emission, pairs=[(0, 1), (0, 2)])
    assert float(gen[(0, 1)]["E"]) == pytest.approx(e01, abs=1e-6)

    # scalar per-pair path with only diagonal gamma / per-pair alpha,delta: biased,
    # because it ignores the acceptor1<->acceptor2 channel bleed.
    gamma = np.ones((3, 3))
    gamma[0, 1], gamma[0, 2] = emission[1, 1], emission[2, 2]
    alpha = np.zeros((3, 3))
    alpha[0, 1], alpha[0, 2] = emission[0, 1], emission[0, 2]
    delta = np.zeros((3, 3))
    delta[0, 1], delta[0, 2] = excitation[0, 1], excitation[0, 2]
    scalar = corrected_es_matrix(inten, gamma, alpha, delta, pairs=[(0, 1), (0, 2)])
    assert not np.isclose(float(scalar[(0, 1)]["E"]), e01, atol=0.02)


def test_general_correction_from_lightpath_payload():
    """The light-path payload builds the matrices and recovers E end-to-end."""
    from chisurf.core.fluorescence.fret.calibration import (
        crosstalk_matrices_from_lightpath,
        general_correction_from_lightpath,
    )

    e_true = 0.55
    tot = 1000.0
    alpha, delta, gamma = 0.08, 0.05, 1.4

    # light-path payloads: excitation (laser x dye), emission (dye x detector)
    matrices = {
        "excitation": {
            "rows": ["L_green", "L_red"],
            "columns": ["D", "A"],
            "values": [[1.0, delta], [0.0, 1.0]],
        },
        "emission": {
            "rows": ["D", "A"],
            "columns": ["green", "red"],
            "values": [[1.0, alpha], [0.0, gamma]],
        },
    }
    chromophores, lasers, detectors = ["D", "A"], ["L_green", "L_red"], ["green", "red"]

    exc, emis = crosstalk_matrices_from_lightpath(matrices, chromophores, lasers, detectors)
    assert exc.shape == (2, 2)
    assert emis.shape == (2, 2)

    # forward-generate the measured intensity from known E
    e_emit = np.array([
        [(1 - e_true) * tot, e_true * tot + delta * tot],
        [0.0, tot],
    ])
    inten = e_emit @ emis

    res = general_correction_from_lightpath(
        inten, matrices, chromophores, lasers, detectors
    )
    assert float(res[(0, 1)]["E"]) == pytest.approx(e_true, abs=1e-9)


def _three_colour_setup():
    excitation = np.array([
        [1.0, 0.04, 0.03],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    emission = np.array([
        [1.0, 0.05, 0.02],
        [0.0, 1.3, 0.15],
        [0.0, 0.35, 0.9],
    ])
    return excitation, emission


def _forward(excitation, emission, e01, e02, tot=1000.0):
    e_emit = np.array([
        [(1 - e01 - e02) * tot,
         e01 * tot + excitation[0, 1] / excitation[1, 1] * tot,
         e02 * tot + excitation[0, 2] / excitation[2, 2] * tot],
        [0.0, tot, 0.0],
        [0.0, 0.0, tot],
    ])
    return e_emit @ emission


def test_stable_matches_naive_on_clean_data():
    """With no noise the NNLS (stable) unmix gives the same E as the naive pinv."""
    exc, emis = _three_colour_setup()
    e01, e02 = 0.4, 0.3
    inten = _forward(exc, emis, e01, e02)

    naive = corrected_es_general(inten, exc, emis, pairs=[(0, 1), (0, 2)], unmix="naive")
    stable = corrected_es_general(inten, exc, emis, pairs=[(0, 1), (0, 2)], unmix="stable")
    assert float(stable[(0, 1)]["E"]) == pytest.approx(float(naive[(0, 1)]["E"]), abs=1e-6)
    assert float(stable[(0, 1)]["E"]) == pytest.approx(e01, abs=1e-6)


def test_nnls_unmix_stays_nonnegative_where_pinv_does_not():
    """The positivity guarantee lives in the emission un-mixing itself."""
    from chisurf.core.fluorescence.crosstalk import invert_mixing

    # two nearly-identical acceptor spectra -> ill-conditioned emission matrix
    emission = np.array([
        [1.0, 0.05, 0.05],
        [0.0, 1.00, 0.98],   # acceptor 1 and 2 almost the same channel response
        [0.0, 0.98, 1.00],
    ])
    assert np.linalg.cond(emission) > 50  # genuinely ill-conditioned

    # a true, physical (non-negative) emission vector + measurement noise
    true_e = np.array([300.0, 5.0, 4.0])  # acceptors barely emitting
    rng = np.random.default_rng(1)
    measured = true_e @ emission
    noisy = measured[:, None] + rng.normal(0.0, 20.0, size=(3, 500))

    naive = invert_mixing(emission, noisy, nonneg=False)
    stable = invert_mixing(emission, noisy, nonneg=True)

    # the plain pseudo-inverse pushes the small, correlated acceptors negative
    assert np.mean(naive < 0) > 0.1
    # non-negative least squares never returns a negative emission
    assert np.all(stable >= -1e-9)


def test_stable_unmix_keeps_efficiency_bounded_under_ill_conditioning():
    """On ill-conditioned noisy data, stable E stays in [0, 1] far more often."""
    excitation = np.array([
        [1.0, 0.04, 0.03],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    emission = np.array([
        [1.0, 0.05, 0.05],
        [0.0, 1.00, 0.98],
        [0.0, 0.98, 1.00],
    ])
    clean = _forward(excitation, emission, 0.35, 0.35)
    rng = np.random.default_rng(1)
    noisy = clean[:, :, None] + rng.normal(0.0, 25.0, size=clean.shape + (400,))

    naive = corrected_es_general(noisy, excitation, emission,
                                 pairs=[(0, 1)], unmix="naive")
    stable = corrected_es_general(noisy, excitation, emission,
                                  pairs=[(0, 1)], unmix="stable")

    def frac_out_of_range(res):
        e = np.asarray(res[(0, 1)]["E"])
        return np.mean((e < -0.05) | (e > 1.05))

    assert frac_out_of_range(stable) < frac_out_of_range(naive)


def test_ridge_reduces_variance_of_recovered_efficiency():
    """Tikhonov damping lowers the burst-to-burst variance on ill-conditioned data."""
    excitation = np.array([
        [1.0, 0.04, 0.03],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    emission = np.array([
        [1.0, 0.05, 0.05],
        [0.0, 1.00, 0.98],
        [0.0, 0.98, 1.00],
    ])
    clean = _forward(excitation, emission, 0.35, 0.35)
    rng = np.random.default_rng(2)
    noisy = clean[:, :, None] + rng.normal(0.0, 25.0, size=clean.shape + (500,))

    plain = corrected_es_general(noisy, excitation, emission,
                                 pairs=[(0, 1)], unmix="naive", ridge=0.0)
    ridged = corrected_es_general(noisy, excitation, emission,
                                  pairs=[(0, 1)], unmix="naive", ridge=1.0)
    assert np.std(ridged[(0, 1)]["E"]) < np.std(plain[(0, 1)]["E"])


def test_unmix_invalid_raises():
    exc, emis = _three_colour_setup()
    inten = _forward(exc, emis, 0.4, 0.3)
    with pytest.raises(ValueError, match="unmix"):
        corrected_es_general(inten, exc, emis, unmix="bogus")
