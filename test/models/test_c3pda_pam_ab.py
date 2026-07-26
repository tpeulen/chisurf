"""A/B verification of the c3PDA physics against the incumbent suite (PRD-65).

Follows the precedent of ``test/fitting/test_fcs_pam_ab.py`` and
``/references/fcs-pam-port.md``: the incumbent's MATLAB expressions are
**transcribed verbatim** into this file and asserted equal to the ChiSurf
implementation over randomised parameters. The formulas are documented prior
art, reimplemented independently — no code is copied into the shipped modules.

Why transcription rather than executing the MATLAB. The expressions live inline
inside a 6.9k-line GUI application, reading a global struct that only exists
after a session has been loaded through the interface; there is no entry point
to call. Transcribing the arithmetic is therefore not the convenient option, it
is the only faithful one — and it is reviewable, which running an opaque binary
would not be.

The transcription is kept deliberately literal: same variable names
(``pe_b``, ``cr_bg``, ``de_bg``, ``gamma_bg``, ``EBG_R``…), same term order,
same redundancies. It is meant to be diffable against the source, not elegant.
"""

from __future__ import annotations

import numpy as np
import pytest

# ── the incumbent's expressions, transcribed ───────────────────────────────


def _pam_blue_probabilities(r_bg, r_br, r_gr, corrections):
    """PBB / PBG / PBR exactly as the incumbent computes them.

    Transcribed from the blue-excitation block of the reference implementation
    (``lsq_mc_dist_3d_cor``), including its two-stage efficiency construction:
    pairwise Förster efficiencies first, then the competing-pathway forms
    ``EBG_R`` / ``EBR_G``.
    """
    R0_bg = corrections["R0_bg"]
    R0_br = corrections["R0_br"]
    R0_gr = corrections["R0_gr"]
    cr_bg = corrections["cr_bg"]
    cr_br = corrections["cr_br"]
    cr_gr = corrections["cr_gr"]
    de_bg = corrections["de_bg"]
    de_br = corrections["de_br"]
    gamma_br = corrections["gamma_br"]
    gamma_gr = corrections["gamma_gr"]
    gamma_bg = gamma_br / gamma_gr

    pe_b = 1 - de_br - de_bg  # probability of blue excitation

    E1 = 1.0 / (1 + (r_bg / R0_bg) ** 6)
    E2 = 1.0 / (1 + (r_br / R0_br) ** 6)
    EGR = 1.0 / (1 + (r_gr / R0_gr) ** 6)

    EBG_R = E1 * (1 - E2) / (1 - E1 * E2)
    EBR_G = E2 * (1 - E1) / (1 - E1 * E2)
    E1A = EBG_R + EBR_G

    PB = pe_b * (1 - E1A)

    PG = (
        pe_b * (1 - E1A) * cr_bg
        + pe_b * EBG_R * (1 - EGR) * gamma_bg
        + de_bg * (1 - EGR) * gamma_bg
    )

    PR = (
        pe_b * (1 - E1A) * cr_br
        + pe_b * EBG_R * (1 - EGR) * gamma_bg * cr_gr
        + pe_b * EBG_R * EGR * gamma_br
        + pe_b * EBR_G * gamma_br
        + de_bg * (1 - EGR) * gamma_bg * cr_gr
        + de_bg * EGR * gamma_br
        + de_br * gamma_br
    )

    P_total = PB + PG + PR
    return np.stack([PB / P_total, PG / P_total, PR / P_total], axis=-1)


def _pam_green_red_probability(r_gr, corrections):
    """PGR exactly as the incumbent computes it (green-excitation block)."""
    R0_gr = corrections["R0_gr"]
    cr_gr = corrections["cr_gr"]
    de_gr = corrections["de_gr"]
    gamma_gr = corrections["gamma_gr"]

    EGR = 1.0 / (1 + (r_gr / R0_gr) ** 6)
    return 1 - (1 + cr_gr + (((de_gr / (1 - de_gr)) + EGR) * gamma_gr) / (1 - EGR)) ** (-1)


# ── mapping the incumbent's corrections onto ThreeColorSetup ───────────────


def _setup_from_corrections(corrections):
    """Return the ChiSurf setup equivalent to the incumbent's correction set.

    The incumbent carries loose scalars (``cr_*`` crosstalk, ``gamma_*``
    relative brightness); ChiSurf folds emission-to-channel transport into one
    detection matrix. The map is lower triangular, because a redder dye never
    leaks into a bluer channel::

        [[1,     0,              0       ],
         [cr_bg, gamma_bg,       0       ],
         [cr_br, cr_gr*gamma_bg, gamma_br]]

    Note ``gamma_bg = gamma_br / gamma_gr``: the incumbent stores two of the
    three relative brightnesses and derives the third, which the single matrix
    enforces structurally instead.
    """
    from chisurf.core.fluorescence.c3pda import ThreeColorSetup

    gamma_br = corrections["gamma_br"]
    gamma_gr = corrections["gamma_gr"]
    return ThreeColorSetup.from_scalars(
        r0_bg=corrections["R0_bg"],
        r0_br=corrections["R0_br"],
        r0_gr=corrections["R0_gr"],
        crosstalk_bg=corrections["cr_bg"],
        crosstalk_br=corrections["cr_br"],
        crosstalk_gr=corrections["cr_gr"],
        gamma_bg=gamma_br / gamma_gr,
        gamma_br=gamma_br,
        direct_excitation_blue=(corrections["de_bg"], corrections["de_br"]),
        direct_excitation_green=corrections["de_gr"],
    )


def _random_corrections(rng):
    """Draw a correction set spanning realistic instrument values."""
    return {
        "R0_bg": rng.uniform(40.0, 65.0),
        "R0_br": rng.uniform(40.0, 65.0),
        "R0_gr": rng.uniform(40.0, 65.0),
        "cr_bg": rng.uniform(0.0, 0.25),
        "cr_br": rng.uniform(0.0, 0.15),
        "cr_gr": rng.uniform(0.0, 0.30),
        "de_bg": rng.uniform(0.0, 0.12),
        "de_br": rng.uniform(0.0, 0.10),
        "de_gr": rng.uniform(0.0, 0.15),
        "gamma_br": rng.uniform(0.3, 2.5),
        "gamma_gr": rng.uniform(0.3, 2.5),
    }


# ── the comparisons ────────────────────────────────────────────────────────


def test_competing_pathway_efficiencies_agree():
    """``EBG_R`` and the shared-denominator form are the same quantity.

    The two implementations parameterise the competition differently — the
    incumbent builds pairwise Förster efficiencies and combines them as
    ``E1(1-E2)/(1-E1 E2)``, ChiSurf goes straight to ``x_bg/(1+x_bg+x_br)``.
    They are algebraically identical: substituting ``E = x/(1+x)`` collapses the
    incumbent's expression onto the shared denominator. Worth pinning, because
    the equivalence is not obvious by inspection and a future edit to either
    side would break it silently.
    """
    from chisurf.core.fluorescence.c3pda import distances_to_matrix, transfer_efficiencies

    rng = np.random.default_rng(101)
    for _ in range(200):
        corrections = _random_corrections(rng)
        r_bg, r_br, r_gr = rng.uniform(25.0, 100.0, size=3)
        setup = _setup_from_corrections(corrections)

        E1 = 1.0 / (1 + (r_bg / corrections["R0_bg"]) ** 6)
        E2 = 1.0 / (1 + (r_br / corrections["R0_br"]) ** 6)
        pam_ebg = E1 * (1 - E2) / (1 - E1 * E2)
        pam_ebr = E2 * (1 - E1) / (1 - E1 * E2)

        e = transfer_efficiencies(distances_to_matrix([r_bg, r_br, r_gr]), setup)
        assert float(e[0, 1]) == pytest.approx(pam_ebg, rel=1e-12)
        assert float(e[0, 2]) == pytest.approx(pam_ebr, rel=1e-12)


def test_blue_channel_probabilities_match_the_incumbent():
    """Full A/B on PBB / PBG / PBR over randomised distances and corrections."""
    from chisurf.core.fluorescence.c3pda import blue_channel_probabilities

    rng = np.random.default_rng(202)
    worst = 0.0
    for _ in range(500):
        corrections = _random_corrections(rng)
        r_bg, r_br, r_gr = rng.uniform(25.0, 100.0, size=3)
        setup = _setup_from_corrections(corrections)

        expected = _pam_blue_probabilities(r_bg, r_br, r_gr, corrections)
        obtained = blue_channel_probabilities(r_bg, r_br, r_gr, setup)[0]
        worst = max(worst, float(np.abs(obtained - expected).max()))
        assert np.allclose(obtained, expected, rtol=1e-10, atol=1e-12)
    assert worst < 1e-12, worst


def test_green_red_probability_matches_the_incumbent():
    """Full A/B on PGR, the green-excitation binomial parameter."""
    from chisurf.core.fluorescence.c3pda import green_channel_probabilities

    rng = np.random.default_rng(303)
    for _ in range(500):
        corrections = _random_corrections(rng)
        r_gr = rng.uniform(25.0, 100.0)
        setup = _setup_from_corrections(corrections)

        expected = _pam_green_red_probability(r_gr, corrections)
        obtained = green_channel_probabilities(r_gr, setup)[0, 1]
        assert float(obtained) == pytest.approx(expected, rel=1e-10, abs=1e-12)


def test_the_excitation_partition_is_what_the_incumbent_does():
    """Regression: direct excitation *takes* probability, it does not add it.

    Found by this A/B. ChiSurf originally added direct excitation of G and R as
    extra emission weight while leaving the blue dye's share at 1, whereas the
    incumbent scales every blue-excitation pathway by ``pe_b = 1 - de_bg -
    de_br``. Because the probabilities are normalised afterwards, the error was
    invisible at zero direct excitation and grew with it — a silent bias in
    exactly the correction meant to remove one.
    """
    from chisurf.core.fluorescence.c3pda import ThreeColorSetup, blue_channel_probabilities

    corrections = {
        "R0_bg": 49.0, "R0_br": 52.0, "R0_gr": 51.0,
        "cr_bg": 0.1, "cr_br": 0.05, "cr_gr": 0.2,
        "de_bg": 0.08, "de_br": 0.06, "de_gr": 0.1,
        "gamma_br": 1.3, "gamma_gr": 0.9,
    }
    setup = _setup_from_corrections(corrections)
    reference = _pam_blue_probabilities(50.0, 60.0, 55.0, corrections)
    assert np.allclose(blue_channel_probabilities(50.0, 60.0, 55.0, setup)[0], reference)

    # The un-partitioned variant (direct excitation added on top) is a different
    # answer, so the test above is actually discriminating.
    naive = ThreeColorSetup(
        forster_radii=setup.forster_radii,
        excitation=np.array([[1.0, 0.08, 0.06], [0.0, 0.9, 0.1]]),  # NOT normalised
        emission=setup.emission,
    )
    # __post_init__ normalises, so build the un-partitioned variant explicitly.
    naive.excitation = np.array([[1.0, 0.08, 0.06], [0.0, 0.9, 0.1]])
    assert not np.allclose(blue_channel_probabilities(50.0, 60.0, 55.0, naive)[0], reference)


def _pam_burst_likelihood(f_blue, f_green, p_blue, p_gr, bg_blue, bg_green, n_bg):
    """Return the burst likelihood as the incumbent's C kernel computes it.

    Transcribed from ``eval_prob_3c_bg_lib.c``: a nested sum over each channel's
    background count, each term a Poisson background weight times the
    multinomial of the background-subtracted counts (the kernel reads its log
    coefficient from a precomputed library, spelled out here). The trinomial and
    binomial parts are computed separately and **multiplied per burst**, and
    there is no photon-number weight — which is where ChiSurf's default
    ``photon_number_pmf=None`` convention comes from.

    ``n_bg`` is the kernel's hard per-channel summation bound; it truncates at
    ``min(F, n_bg)`` with ``n_bg`` a user-set integer rather than on any
    numerical criterion.
    """
    import itertools

    from scipy.special import gammaln
    from scipy.stats import poisson

    p_bb, p_bg, p_br = p_blue

    trinomial = 0.0
    for a, b, c in itertools.product(
        range(int(min(f_blue[0], n_bg[0])) + 1),
        range(int(min(f_blue[1], n_bg[1])) + 1),
        range(int(min(f_blue[2], n_bg[2])) + 1),
    ):
        signal = np.array([f_blue[0] - a, f_blue[1] - b, f_blue[2] - c], dtype=float)
        log_coefficient = gammaln(signal.sum() + 1) - gammaln(signal + 1).sum()
        trinomial += (
            poisson.pmf(a, bg_blue[0])
            * poisson.pmf(b, bg_blue[1])
            * poisson.pmf(c, bg_blue[2])
            * np.exp(
                log_coefficient
                + np.log(p_bb) * signal[0]
                + np.log(p_bg) * signal[1]
                + np.log(p_br) * signal[2]
            )
        )

    binomial = 0.0
    for a, b in itertools.product(
        range(int(min(f_green[0], n_bg[3])) + 1),
        range(int(min(f_green[1], n_bg[4])) + 1),
    ):
        signal = np.array([f_green[0] - a, f_green[1] - b], dtype=float)
        log_coefficient = gammaln(signal.sum() + 1) - gammaln(signal + 1).sum()
        binomial += (
            poisson.pmf(a, bg_green[0])
            * poisson.pmf(b, bg_green[1])
            * np.exp(
                log_coefficient
                + np.log(p_gr) * signal[1]
                + np.log(1 - p_gr) * signal[0]
            )
        )

    return trinomial * binomial


def test_burst_likelihood_matches_the_incumbent_kernel():
    """A/B on the likelihood itself, not just the probabilities.

    ChiSurf reaches the same number by a different route — the nested sum is
    factorised into two matrix products — so agreeing here checks the
    factorisation against an independent statement of the definition, on the
    three-channel case that the two-colour ``tttrlib.Pda`` cross-check cannot
    reach.

    The summation bound is set generously so the incumbent's hard ``min(F,
    n_bg)`` truncation is not what is being compared; ChiSurf truncates on an
    effective rate instead, which is strictly the more careful rule.
    """
    from chisurf.core.fluorescence.c3pda import burst_log_likelihood

    rng = np.random.default_rng(505)
    for _ in range(30):
        f_blue = rng.integers(0, 9, size=3)
        f_green = rng.integers(0, 9, size=2)
        p_blue = rng.dirichlet(np.ones(3))
        p_gr = float(rng.uniform(0.1, 0.9))
        bg_blue = rng.uniform(0.1, 1.2, size=3)
        bg_green = rng.uniform(0.1, 1.2, size=2)

        expected = _pam_burst_likelihood(
            f_blue, f_green, p_blue, p_gr, bg_blue, bg_green, n_bg=[99] * 5
        )

        # ChiSurf keeps the two periods as separate partitions and sums their
        # log-likelihoods, which is the same product.
        obtained = float(
            burst_log_likelihood(f_blue[None, :], p_blue[None, :], bg_blue)[0, 0]
            + burst_log_likelihood(
                f_green[None, :], np.array([[1 - p_gr, p_gr]]), bg_green
            )[0, 0]
        )
        assert obtained == pytest.approx(np.log(expected), rel=1e-9)


def test_agreement_holds_with_corrections_switched_off():
    """The clean-instrument limit must also agree, not just the messy one."""
    from chisurf.core.fluorescence.c3pda import (
        blue_channel_probabilities,
        green_channel_probabilities,
    )

    corrections = {
        "R0_bg": 50.0, "R0_br": 50.0, "R0_gr": 50.0,
        "cr_bg": 0.0, "cr_br": 0.0, "cr_gr": 0.0,
        "de_bg": 0.0, "de_br": 0.0, "de_gr": 0.0,
        "gamma_br": 1.0, "gamma_gr": 1.0,
    }
    setup = _setup_from_corrections(corrections)
    rng = np.random.default_rng(404)
    for _ in range(100):
        r_bg, r_br, r_gr = rng.uniform(25.0, 100.0, size=3)
        assert np.allclose(
            blue_channel_probabilities(r_bg, r_br, r_gr, setup)[0],
            _pam_blue_probabilities(r_bg, r_br, r_gr, corrections),
            rtol=1e-12,
        )
        assert float(green_channel_probabilities(r_gr, setup)[0, 1]) == pytest.approx(
            _pam_green_red_probability(r_gr, corrections), rel=1e-12
        )
