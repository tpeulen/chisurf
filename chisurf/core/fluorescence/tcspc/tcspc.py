from __future__ import annotations

import numpy as np

import chisurf.core.math
import chisurf.core.math.datatools


# bin_lifetime_spectrum = skf.decay.rate_spectra.bin_lifetime_spectrum
def bin_lifetime_spectrum(
    lifetime_spectrum: np.array, n_lifetimes: int, discriminate: bool, discriminator=None
) -> np.array:
    """Takes an interleaved lifetime spectrum

    :param lifetime_spectrum: interleaved lifetime spectrum
    :param n_lifetimes:
    :param discriminate:
    :param discriminator:
    :return: lifetime_spectrum
    """
    amplitudes, lifetimes = chisurf.core.math.datatools.interleaved_to_two_columns(
        lifetime_spectrum, sort=False
    )
    print(lifetimes)
    print(amplitudes)
    # histogram1D has *inverted* sentinel limits (tth_max < tth_min) that skip
    # every value, so the range has to be passed explicitly. A spectrum with a
    # single distinct lifetime has nothing to bin (and would divide by zero).
    if lifetimes.size and lifetimes.min() < lifetimes.max():
        lt, am = chisurf.core.math.datatools.histogram1D(
            values=lifetimes,
            weights=amplitudes,
            n_bins=n_lifetimes,
            tth_min=float(lifetimes.min()),
            tth_max=float(lifetimes.max()),
        )
    else:
        lt, am = lifetimes, amplitudes
    if discriminate and discriminator is not None:
        lt, am = chisurf.core.math.datatools.discriminate(
            values=lt, weights=am, discriminator=discriminator
        )
    binned_lifetime_spectrum = chisurf.core.math.datatools.two_column_to_interleaved(x=am, t=lt)
    return binned_lifetime_spectrum


def rescale_w_bg(
    model_decay: np.array,
    experimental_decay: np.array,
    experimental_weights: np.array,
    experimental_background: float,
    start: int,
    stop: int,
) -> float:
    """Computes a scaling factor that scales a model decay to an
    experimental decay on a defined range.

    The scale is the weighted least-squares solution of
    ``e - b = scale * m``, i.e. the value that minimises
    ``sum_i w_i**2 * (e_i - b - scale * m_i)**2``.

    Parameters
    ----------
    model_decay : numpy.ndarray
        Model decay for which a scaling factor is computed.
    experimental_decay : numpy.ndarray
        Experimental decay to which `model_decay` is scaled.
    experimental_weights : numpy.ndarray
        Weights of the experimental decay, i.e. **inverse** errors
        (``w = 1 / ey``), following the convention of
        :meth:`chisurf.core.data.DataCurve.set_weights`. Each channel
        therefore enters the sums with ``w**2 = 1 / sigma**2``.
    experimental_background : float
        Constant offset in the experimental data that is subtracted from the
        experimental decay.
    start : int
        Start index of the range in which the model decay is scaled.
    stop : int
        Stop index of the range in which the model decay is scaled.

    Returns
    -------
    float:
        The scaling factor that was used to scale the model function to the
        experimental decay.

    """
    w = np.asarray(experimental_weights[start:stop], dtype=float)
    e = np.asarray(experimental_decay[start:stop], dtype=float)
    m = np.asarray(model_decay[start:stop], dtype=float)
    b = experimental_background

    # Note this is deliberately *not* the photon library's `rescale_w_bg`,
    # which is otherwise the same least-squares solution. That one guards only
    # on `decay > 0`, adds a 1e-12 floor to the squared weight, and rescales the
    # model in place as a side effect. The finite-weight guard here matters --
    # an empty channel can carry an infinite weight and would otherwise poison
    # the whole sum -- and the caller wants the factor, not a mutated model.
    contributing = (e > 0.0) & np.isfinite(w)
    if not contributing.any():
        return 0.0

    weight_squared = w[contributing] ** 2
    model = m[contributing]
    sum_nom = float(np.sum(model * (e[contributing] - b) * weight_squared))
    sum_denom = float(np.sum(model * model * weight_squared))
    return sum_nom / sum_denom if sum_denom != 0.0 else 0.0


def pddem_rates(
    decayA: np.ndarray,
    decayB: np.ndarray,
    ks: np.ndarray,
    px: np.ndarray,
    pm: np.ndarray,
    pAB: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    """The PDDEM spectrum for a whole FRET-rate spectrum, in one call.

    Rate-vectorised :func:`pddem`: the caller used to invoke the pair kernel
    once per rate of the FRET-rate spectrum -- 96 calls per model evaluation
    on the standard distance axis, each on a (1, 1) pair grid where numpy's
    per-call overhead dwarfs the arithmetic, plus a fresh read of every
    parameter property per iteration. That loop was 29% of *all* movable
    model compute on the 2026-09-02 scoreboard. Here the pair grid gains a
    leading rate axis and the whole spectrum is one broadcast; only the
    per-rate keep-mask assembly remains a (trivial) loop, because each
    rate's kept components interleave with its own pure-A/pure-B tail and
    the tail lengths are rate-independent while the kept counts are not.

    Bit-for-bit the concatenation of ``pddem(decayA, decayB, [kAB*r, kBA*r],
    ...) * weight`` over the rates, in the same order -- pinned by
    ``test_pddem_rates_matches_the_per_rate_loop``.

    Parameters
    ----------
    decayA, decayB : numpy.ndarray
        Interleaved (amplitude, lifetime) spectra of the two pure dyes.
    ks : numpy.ndarray
        ``(n, 2)`` transfer-rate pairs ``(kAB, kBA)``, one row per rate of
        the FRET-rate spectrum.
    px, pm, pAB : numpy.ndarray
        Excitation and emission probabilities and the pure-AB pair, exactly
        :func:`pddem`'s.
    weights : numpy.ndarray
        One weight per rate; each rate's whole sub-spectrum (pure components
        included) is scaled by it, as the caller's loop did.

    Returns
    -------
    numpy.ndarray
        The interleaved (amplitude, lifetime) spectrum, rate-major.
    """
    eps = 1e-9
    ks = np.asarray(ks, dtype=float).reshape(-1, 2)
    weights = np.asarray(weights, dtype=float)
    n_rates = ks.shape[0]
    nA = decayA.shape[0] // 2
    nB = decayB.shape[0] // 2

    kAB = ks[:, 0][:, None, None]
    kBA = ks[:, 1][:, None, None]
    pxA, pxB = px[0], px[1]
    pmA, pmB = pm[0], pm[1]

    piA = (pAB[0] * (1.0 - pAB[1])) / (1.0 - pAB[0] * pAB[1])
    piB = (pAB[1] * (1.0 - pAB[0])) / (1.0 - pAB[0] * pAB[1])
    piAB = 1.0 - piA - piB

    cA = np.asarray(decayA[0::2], dtype=float)[:nA][None, :, None]
    tauA = np.asarray(decayA[1::2], dtype=float)[:nA][None, :, None]
    cB = np.asarray(decayB[0::2], dtype=float)[:nB][None, None, :]
    tauB = np.asarray(decayB[1::2], dtype=float)[:nB][None, None, :]

    pair_ok = (cA != 0.0) & (cB != 0.0) & (tauA != 0.0) & (tauB != 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        itauA = np.where(tauA != 0.0, 1.0 / np.where(tauA != 0.0, tauA, 1.0), 0.0)
        itauB = np.where(tauB != 0.0, 1.0 / np.where(tauB != 0.0, tauB, 1.0), 0.0)

        root = np.sqrt((itauA - itauB + kAB - kBA) ** 2 + 4 * kAB * kBA)
        l1 = 0.5 * (-itauA - itauB - kAB - kBA + root)
        l2 = l1 - root

        common = piAB * cA * cB / (l1 - l2 + eps)
        shape = (n_rates,) + np.broadcast(cA, cB).shape[1:]
        amplitude = np.empty(shape + (2,), dtype=float)
        amplitude[..., 0] = common * (
            pmA * (pxA * (-l2 - itauA - kAB) + pxB * kBA)
            + pmB * (pxA * kAB + pxB * (-l2 - itauB - kBA))
        )
        amplitude[..., 1] = common * (
            pmA * (pxA * (l1 + itauA + kAB) - pxB * kBA)
            + pmB * (-pxA * kAB + pxB * (l1 + itauB + kBA))
        )
        lifetime = np.empty_like(amplitude)
        lifetime[..., 0] = np.broadcast_to(-1.0 / l1, shape)
        lifetime[..., 1] = np.broadcast_to(-1.0 / l2, shape)

    keep = (np.abs(amplitude) > 1e-10) & pair_ok[..., None]

    # The pure components are rate-independent in value; only their weight
    # changes per rate. Computed once, appended per rate.
    pure_a = pmA * pxA * piA * cA[0, :, 0]
    keep_a = np.abs(pure_a) > 1e-10
    pure_a, tail_tau_a = pure_a[keep_a], tauA[0, :, 0][keep_a]
    pure_b = pmB * pxB * piB * cB[0, 0, :]
    keep_b = np.abs(pure_b) > 1e-10
    pure_b, tail_tau_b = pure_b[keep_b], tauB[0, 0, :][keep_b]

    amplitudes, lifetimes = [], []
    for i in range(n_rates):
        ki = keep[i]
        w = weights[i]
        amplitudes += [amplitude[i][ki] * w, pure_a * w, pure_b * w]
        lifetimes += [lifetime[i][ki], tail_tau_a, tail_tau_b]

    c = np.concatenate(amplitudes) if amplitudes else np.empty(0)
    tau = np.concatenate(lifetimes) if lifetimes else np.empty(0)
    d = np.empty(2 * c.size, dtype=np.float64)
    d[0::2] = c
    d[1::2] = tau
    return d


def pddem(
    decayA: np.ndarray,
    decayB: np.ndarray,
    k: np.ndarray,
    px: np.ndarray,
    pm: np.ndarray,
    pAB: np.ndarray,
):
    """
    Electronic Energy Transfer within Asymmetric
    Pairs of Fluorophores: Partial Donor-Donor
    Energy Migration (PDDEM)
    Stanislav Kalinin
    http://www.diva-portal.org/smash/get/diva2:143149/FULLTEXT01


    Kalinin, S.V., Molotkovsky, J.G., and Johansson, L.B.
    Partial Donor-Donor Energy Migration (PDDEM) as a Fluorescence
    Spectroscopic Tool for Measuring Distances in Biomacromolecules.
    Spectrochim. Acta A, 58 (2002) 1087-1097.

    -> same results as Stas pddem code (pddem_t.c)

    :param decayA: model_decay A in form of [ampl lifetime, apml, lifetime...]
    :param decayB: model_decay B in form of [ampl lifetime, apml, lifetime...]
    :param k: rates of energy transfer [kAB, kBA]
    :param px: probabilities of excitation (pxA, pxB)
    :param pm: probabilities of emission (pmA, pmB)
    :param pAB: pure AB [0., 0]
    :return:
    """
    # return _tcspc.pddem(decayA, decayB, k, px, pm, pAB)
    eps = 1e-9

    nA = decayA.shape[0] // 2
    nB = decayB.shape[0] // 2

    kAB, kBA = k[0], k[1]
    pxA, pxB = px[0], px[1]
    pmA, pmB = pm[0], pm[1]

    ####  PDDEM-calculations ####
    # initial probabilities
    piA = (pAB[0] * (1.0 - pAB[1])) / (1.0 - pAB[0] * pAB[1])
    piB = (pAB[1] * (1.0 - pAB[0])) / (1.0 - pAB[0] * pAB[1])
    piAB = 1.0 - piA - piB

    # Every (A, B) pair contributes two components, and the emission order is
    # pair-major with the two branches adjacent -- iA outer, iB inner, branch
    # innermost. Building the pair grids and interleaving along a trailing
    # axis of length two reproduces that order exactly; getting it wrong would
    # reorder the spectrum rather than change any value, which no amplitude
    # check would catch.
    cA = np.asarray(decayA[0::2], dtype=float)[:nA, None]
    tauA = np.asarray(decayA[1::2], dtype=float)[:nA, None]
    cB = np.asarray(decayB[0::2], dtype=float)[None, :nB]
    tauB = np.asarray(decayB[1::2], dtype=float)[None, :nB]

    # A zero amplitude or a zero lifetime skipped the whole pair, both branches.
    pair_ok = (cA != 0.0) & (cB != 0.0) & (tauA != 0.0) & (tauB != 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        itauA = np.where(tauA != 0.0, 1.0 / np.where(tauA != 0.0, tauA, 1.0), 0.0)
        itauB = np.where(tauB != 0.0, 1.0 / np.where(tauB != 0.0, tauB, 1.0), 0.0)

        root = np.sqrt((itauA - itauB + kAB - kBA) ** 2 + 4 * kAB * kBA)
        l1 = 0.5 * (-itauA - itauB - kAB - kBA + root)
        l2 = l1 - root

        common = piAB * cA * cB / (l1 - l2 + eps)
        amplitude = np.empty(np.broadcast(cA, cB).shape + (2,), dtype=float)
        amplitude[..., 0] = common * (
            pmA * (pxA * (-l2 - itauA - kAB) + pxB * kBA)
            + pmB * (pxA * kAB + pxB * (-l2 - itauB - kBA))
        )
        amplitude[..., 1] = common * (
            pmA * (pxA * (l1 + itauA + kAB) - pxB * kBA)
            + pmB * (-pxA * kAB + pxB * (l1 + itauB + kBA))
        )
        lifetime = np.empty_like(amplitude)
        lifetime[..., 0] = np.broadcast_to(-1.0 / l1, amplitude.shape[:-1])
        lifetime[..., 1] = np.broadcast_to(-1.0 / l2, amplitude.shape[:-1])

    keep = (np.abs(amplitude) > 1e-10) & pair_ok[..., None]
    amplitudes = [amplitude[keep]]
    lifetimes = [lifetime[keep]]

    #  adding pureA, pureB
    pure_a = pmA * pxA * piA * cA[:, 0]
    keep_a = np.abs(pure_a) > 1e-10
    amplitudes.append(pure_a[keep_a])
    lifetimes.append(tauA[:, 0][keep_a])

    pure_b = pmB * pxB * piB * cB[0, :]
    keep_b = np.abs(pure_b) > 1e-10
    amplitudes.append(pure_b[keep_b])
    lifetimes.append(tauB[0, :][keep_b])

    c = np.concatenate(amplitudes)
    tau = np.concatenate(lifetimes)

    d = np.empty(2 * c.size, dtype=np.float64)
    d[0::2] = c
    d[1::2] = tau
    return d
