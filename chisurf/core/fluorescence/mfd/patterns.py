"""What one conformational state emits, into which channel, with what micro times.

A state is a mean donor–acceptor distance and a rotational correlation time. From
those, and the optics, follow the two things the forward model needs per state:

* a **branching probability** — given a signal photon, how likely it is to land in
  the acceptor channel — which drives the FRET axis;
* a **micro-time pattern** per detection channel, whose first two moments drive the
  lifetime axis.

Three conventions are fixed here rather than left implicit, because each has more
than one defensible spelling and the histogram would absorb a mismatch into a
distance rather than reveal it.

**The distance is distributed, and the distribution is not Gaussian.** With both dye
positions Gaussian in three dimensions, their separation follows the non-central chi
distribution with three degrees of freedom::

    p(R) = R / (d σ √(2π)) · [ exp(−(R−d)²/2σ²) − exp(−(R+d)²/2σ²) ]

with ``σ² = σ_D² + σ_A²``. This is what produces the familiar linker-broadened
static line, and it is why ``σ`` must not be a free broadening parameter tacked on
afterwards — it is imprinted on the *decay shape*, so the sources that keep the
shape can see it instead of inferring it from a shift.

**p(R) is static on the nanosecond scale and averaged on the millisecond scale.**
Linker sampling is slow compared with the excited-state lifetime, so the decay is a
genuine *lifetime distribution*; a burst is long compared with linker sampling, so
the burst's efficiency is the ``p(R)``-average. The same distribution therefore
enters twice, in two different ways, and swapping them is a real error: averaging
the efficiency first and quenching once would give the wrong decay shape, and
averaging the decay to a single lifetime would give the wrong efficiency.

**Direct excitation is defined against the donor-only green signal.** ``δ`` here is
the acceptor-channel signal from directly excited acceptors as a fraction of the
signal a donor-only molecule would put in the green channel. It is stated because
the literature also carries definitions relative to the acceptor's own maximum, and
the two differ by ``γ``.

**The spectrum algebra is not written here.** A FRET-quenched donor spectrum and a
polarised spectrum are the *same* transforms the TCSPC decay graph applies, and they
live in its producer nodes — :class:`IMP.bff.FRETSpectrumNode` and
:class:`IMP.bff.PhotophysicsAnisotropySpectrumNode`, the two this module drives directly. Keeping a
numpy twin here is the failure shape the decay stack has already paid for: two
owners of one piece of photophysics drift, and the histogram absorbs the drift into
a distance rather than reporting it. See
:mod:`chisurf.core.fluorescence.anisotropy.decay` for the polarisation conventions
and ``okf/architecture/`` for the graph. The one piece that has *no* producer is the
sensitized-acceptor rise; :func:`acceptor_lifetime_spectrum` says so explicitly
rather than quietly keeping a second implementation of something that does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.fret.lines import donor_lifetime_spectrum
from chisurf.core.fluorescence.mfd.moments import (
    background_moments,
    mixture_moments,
    pattern_moments,
    wrapped_exponential_pattern,
)

__all__ = [
    "ChannelResponse",
    "FretState",
    "Optics",
    "acceptor_lifetime_spectrum",
    "donor_lifetime_spectrum_of_state",
    "noncentral_chi_distance_distribution",
    "perrin_anisotropy",
    "polarized_patterns",
    "red_probability",
    "state_efficiency",
]

#: Relative separation forced between the acceptor lifetime and a donor component
#: that happens to equal it. The sensitized-acceptor amplitudes carry a
#: ``1/(τ_A − τ_D)`` factor that is removable but not evaluable at equality; nudging
#: is a hair more accurate than the ``t·exp(−t/τ)`` special case is worth, and
#: unlike a division by zero it cannot produce an infinity that survives into a
#: fitted parameter.
_DEGENERACY_EPS = 1e-6

#: The orientation factor the Förster radii in :class:`Optics` are quoted at.
#: MFD reports one ``R₀`` per dye pair with the isotropic κ² folded into it, so the
#: producer node — which takes ``R₀`` and ``κ²`` separately — is handed the value
#: that leaves ``R₀`` meaning what this module's docstring says it means. A κ²
#: *distribution* is a different model and belongs upstream of here.
_ISOTROPIC_KAPPA2 = 2.0 / 3.0


def _bff():
    """Return the ``IMP.bff`` module, or raise saying why it is needed.

    Imported lazily and never guarded by a numpy fallback. A fallback is what
    would let the two implementations of this photophysics diverge unnoticed,
    which is the whole reason the algebra moved onto the producers; a missing
    engine is a broken installation and must read as one.

    Returns
    -------
    module
    """
    try:
        import IMP.bff as bff
    except ImportError as error:                      # pragma: no cover
        raise ImportError(
            "chisurf.core.fluorescence.mfd.patterns needs IMP.bff: the lifetime "
            "spectrum algebra it used to duplicate now lives in that package's "
            "FRETSpectrumNode/PhotophysicsAnisotropySpectrumNode producer nodes"
        ) from error
    for required in ("PhotophysicsLifetimeSpectrumNode", "FRETSpectrumNode", "PhotophysicsAnisotropySpectrumNode"):
        if not hasattr(bff, required):                # pragma: no cover
            raise ImportError(
                "IMP.bff is present but has no %s; rebuild the extensions "
                "(`pixi run build-extensions`)" % required
            )
    return bff


def _interleave(amplitudes, values) -> np.ndarray:
    """Pack ``(a₀, x₀, a₁, x₁, …)`` — the wire format every producer port uses.

    Parameters
    ----------
    amplitudes, values : array_like
        Equal-length sequences.

    Returns
    -------
    numpy.ndarray
        Contiguous and ``float64``; the ports read a raw buffer.
    """
    a = np.atleast_1d(np.asarray(amplitudes, dtype=float)).ravel()
    x = np.atleast_1d(np.asarray(values, dtype=float)).ravel()
    if a.size != x.size:
        raise ValueError("an interleaved spectrum needs one value per amplitude")
    out = np.empty(2 * a.size, dtype=float)
    out[0::2] = a
    out[1::2] = x
    return np.ascontiguousarray(out)


def _deinterleave(spectrum) -> tuple[np.ndarray, np.ndarray]:
    """Unpack a producer's interleaved output into amplitudes and time constants.

    Parameters
    ----------
    spectrum : array_like
        Interleaved ``(a, t)`` pairs.

    Returns
    -------
    amplitudes, times : numpy.ndarray
    """
    values = np.asarray(spectrum, dtype=float).ravel()
    return values[0::2].copy(), values[1::2].copy()


def _donor_node(amplitudes, lifetimes):
    """Return a ``LifetimeSpectrumNode`` holding the donor-only spectrum.

    The amplitudes handed in are already the *unpolarised, unquenched* ones, and
    :func:`chisurf.core.fluorescence.fret.lines.donor_lifetime_spectrum` has
    normalised them. So both of the node's rescaling switches are off, for the
    same reason
    :func:`chisurf.core.fitting.minimizer._spectrum_chain` turns them off on the
    decay it feeds (``decay.set_absolute_amplitudes(False)`` /
    ``decay.set_normalize_amplitudes(False)``): normalising again downstream
    divides by a different sum — after a rotation it is ``1 + 2 r₀`` rather than
    one — and silently rescales every pattern built from it.

    Parameters
    ----------
    amplitudes, lifetimes : array_like
        The donor-only lifetime spectrum.

    Returns
    -------
    IMP.bff.PhotophysicsLifetimeSpectrumNode
        Already evaluated; ``get_spectrum()`` is valid.
    """
    bff = _bff()
    a = np.atleast_1d(np.asarray(amplitudes, dtype=float)).ravel()
    t = np.atleast_1d(np.asarray(lifetimes, dtype=float)).ravel()
    node = bff.PhotophysicsLifetimeSpectrumNode("donor")
    node.set_number_of_lifetimes(int(a.size))
    node.add_output_port("donor", bff.Port([0.0], False, True))
    node.set_absolute_amplitudes(False)
    node.set_normalize_amplitudes(False)
    for i in range(a.size):
        node.get_input_port("a%d" % i).set_value(float(a[i]))
        node.get_input_port("t%d" % i).set_value(float(t[i]))
    node.evaluate()
    return node


def _fret_spectrum(donor_amplitudes, donor_lifetimes, weights, distances,
                   optics: Optics) -> tuple[np.ndarray, np.ndarray]:
    """Drive ``IMP.bff.FRETSpectrumNode`` — the donor quenched over a distribution.

    A distance is a transfer rate, rates add, so the quenched spectrum is the
    Cartesian product of the donor's rates and the transfer rates. That is why
    this is a *spectrum* transform and not a curve one, and why it belongs to the
    same node the TCSPC graph uses rather than to a numpy copy of it.

    The node's output is returned verbatim, which means the quenched block
    followed — unconditionally, because the length of a spectrum is observable
    and a node that sometimes returns a shorter one is a second code path —
    by a donor-only block scaled by ``x_donly``. ``x_donly`` is zero here: the
    MFD forward model carries incomplete labelling as its own *species*
    (``has_acceptor``) rather than as a term inside one state. Callers that
    promise a purely quenched spectrum drop that block themselves; see
    :func:`donor_lifetime_spectrum_of_state`.

    Parameters
    ----------
    donor_amplitudes, donor_lifetimes : array_like
        The donor-only lifetime spectrum.
    weights, distances : array_like
        A discretized donor–acceptor distance distribution, Å.
    optics : Optics
        Supplies ``r0`` and ``tau_d0``.

    Returns
    -------
    amplitudes, lifetimes : numpy.ndarray
    """
    bff = _bff()
    donor = _donor_node(donor_amplitudes, donor_lifetimes)
    node = bff.FRETSpectrumNode("fret")
    node.build_ports()
    node.add_output_port("fret", bff.Port([0.0], False, True))
    node.get_input_port("donor_lifetime_spectrum").link = \
        donor.get_output_port("donor")
    node.get_input_port("distance_distribution").set_values_array(
        _interleave(weights, distances)
    )
    node.get_input_port("x_donly").set_value(0.0)
    node.get_input_port("forster_radius").set_value(float(optics.r0))
    node.get_input_port("tau0").set_value(float(optics.tau_d0))
    node.get_input_port("kappa2").set_value(_ISOTROPIC_KAPPA2)
    node.evaluate()
    return _deinterleave(node.get_spectrum())


def _polarized_spectrum(amplitudes, lifetimes, rho: float, optics: Optics,
                        polarization: str) -> tuple[np.ndarray, np.ndarray]:
    """Drive ``IMP.bff.PhotophysicsAnisotropySpectrumNode`` for one detection channel.

    The measured decay is the *product* of the fluorescence decay and
    ``r(t) = r₀ e^{−t/ρ}``, and a product of two sums of exponentials is again a
    sum of exponentials — over the Cartesian product of the two spectra, with the
    harmonic mean of the time constants. So a polarisation is a spectrum
    transform, and this is the node that owns it.

    .. rubric:: Why ``g`` is deliberately not handed to the node

    The node's ``g`` port divides its *ideal* perpendicular spectrum **before**
    the ``l₁``/``l₂`` channel mixing. That ordering makes the mixing terms carry
    a stray factor of ``G``, and the result then disagrees with the Schaffer /
    Eggeling amplitude form that
    :func:`chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh`, tttrlib's
    ``DecayFit23`` and this module's own round-trip tests all use::

        f_VV = f · (1 + (2 − 3 l₁) r),   f_VH = f · (1 − (1 − 3 l₂) r) / G

    At ``G = 1`` the two spellings are *identical* for every ``l₁``, ``l₂``:
    ``(1 − l₁)(1 + 2r) + l₁(1 − r) = 1 + (2 − 3 l₁) r`` and
    ``l₂(1 + 2r) + (1 − l₂)(1 − r) = 1 − (1 − 3 l₂) r``. Away from it they are
    not — at ``G = 2``, ``l₁ = l₂ = 0.1`` the recovered anisotropy differs by a
    factor of two.

    So the node is driven at ``g = 1``, where it *is* the Schaffer form, and
    ``G`` is applied afterwards as what it physically is: a detection
    sensitivity scaling the whole perpendicular channel, after the mixing that
    happens in front of the detector. That is one multiplication of a channel
    gain, not a second copy of the spectrum algebra. The node's own ordering is
    a defect recorded in ``okf/references/known-issues.md``; it is not corrected
    here because ``AnisotropySpectrum`` must stay bit-identical to
    :func:`chisurf.core.fluorescence.anisotropy.decay.calculcate_spectrum`,
    which the fitted TCSPC models are pinned against.

    Parameters
    ----------
    amplitudes, lifetimes : array_like
        The emitting species' lifetime spectrum.
    rho : float
        Rotational correlation time, ns.
    optics : Optics
        Supplies ``l1``, ``l2`` and ``r0_anisotropy``. ``g_factor`` is *not*
        read here — see above.
    polarization : {'vv', 'vh'}
        Which detection channel to build.

    Returns
    -------
    amplitudes, lifetimes : numpy.ndarray
    """
    bff = _bff()
    node = bff.PhotophysicsAnisotropySpectrumNode("anisotropy")
    node.set_number_of_rotations(1)
    node.add_output_port("anisotropy", bff.Port([0.0], False, True))
    # Refuses an unknown name rather than defaulting to magic angle, which would
    # silently be a model with no anisotropy in it.
    node.set_polarization_name(polarization)
    node.get_input_port("lifetime_spectrum").set_values_array(
        _interleave(amplitudes, lifetimes)
    )
    node.get_input_port("r0").set_value(float(optics.r0_anisotropy))
    node.get_input_port("g").set_value(1.0)
    node.get_input_port("l1").set_value(float(optics.l1))
    node.get_input_port("l2").set_value(float(optics.l2))
    node.get_input_port("b0").set_value(1.0)
    # A zero correlation time is a division by zero in the harmonic mean of the
    # product; a dye that fast is unpolarized, which the limit already gives.
    node.get_input_port("rho0").set_value(float(max(rho, 1e-9)))
    node.evaluate()
    return _deinterleave(node.get_spectrum())


def noncentral_chi_distance_distribution(
    mean,
    sigma: float,
    *,
    n_points: int = 81,
    n_sigma: float = 3.5,
    r_min: float = 1.0,
):
    """Discretize the donor–acceptor distance distribution of a flexible label.

    Two dyes at the ends of flexible linkers occupy roughly Gaussian clouds; the
    *distance* between two three-dimensional Gaussian clouds is not Gaussian but
    non-central chi with three degrees of freedom. The difference matters at short
    mean distances, where a Gaussian would put weight at negative or near-zero
    separations that ``(R₀/R)⁶`` turns into unphysical quenching.

    Signature-compatible with
    :func:`chisurf.core.fluorescence.fret.lines.gaussian_distance_distribution`, so
    the two can be exchanged and compared.

    Parameters
    ----------
    mean : float or array_like
        Mean donor–acceptor distance(s), Å. An array yields one distribution per
        entry along a leading axis.
    sigma : float
        Combined linker width ``√(σ_D² + σ_A²)``, Å. ``0`` collapses to a delta.
    n_points : int
        Distance samples per distribution.
    n_sigma : float
        Half-width of the sampled range, in units of *sigma*.
    r_min : float
        Lower clip on the distance, keeping ``(R₀/R)⁶`` finite.

    Returns
    -------
    weights, distances : numpy.ndarray
        Both ``(..., n_points)``; weights normalised along the last axis, so the
        truncation of the sampled range cannot leak probability.
    """
    mean = np.atleast_1d(np.asarray(mean, dtype=float))
    if sigma <= 0:
        return np.ones(mean.shape + (1,)), mean[..., None]

    lo = np.clip(mean - n_sigma * sigma, r_min, None)
    hi = mean + n_sigma * sigma
    fraction = np.linspace(0.0, 1.0, int(n_points))
    r = lo[..., None] + (hi - lo)[..., None] * fraction

    d = mean[..., None]
    s = float(sigma)
    weights = (
        r
        / (d * s * np.sqrt(2.0 * np.pi))
        * (
            np.exp(-((r - d) ** 2) / (2.0 * s * s))
            - np.exp(-((r + d) ** 2) / (2.0 * s * s))
        )
    )
    weights = np.clip(weights, 0.0, None)
    total = np.sum(weights, axis=-1, keepdims=True)
    weights = np.where(total > 0, weights / total, 1.0 / int(n_points))
    return weights, r


@dataclass
class Optics:
    """Instrument constants and correction factors, as plain numbers.

    Kept free of any parameter machinery so the compute layer can be called from a
    test, a script or the server without a fit. The fitting model fills it from the
    shared :class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`
    group rather than declaring its own copies of ``α``/``β``/``γ``/``δ``.

    Attributes
    ----------
    r0 : float
        Förster radius, Å.
    tau_d0 : float
        Donor-only lifetime, ns.
    tau_a : float
        Acceptor lifetime, ns.
    alpha : float
        Donor leakage into the acceptor channel, as a fraction of the donor channel.
    delta : float
        Direct acceptor excitation, as a fraction of the *donor-only* green signal
        (see the module docstring — this convention is not the only one in use).
    gamma : float
        ``(g_A Φ_A) / (g_D Φ_D)``: the detection-efficiency and quantum-yield ratio.
    sigma : float
        Combined linker width ``√(σ_D² + σ_A²)``, Å. Shared across states and given
        an informative prior; it is *not* a free broadening parameter.
    g_factor : float
        Ratio of the perpendicular to the parallel detection sensitivity. A
        *detection* property, so it scales the whole perpendicular channel rather
        than only its depolarization term — see :func:`polarized_patterns`.
    l1, l2 : float
        Polarization mixing of the two detection channels.
    r0_anisotropy : float
        Fundamental anisotropy at time zero, ``r(0)``.
    """

    r0: float = 52.0
    tau_d0: float = 4.0
    tau_a: float = 3.0
    alpha: float = 0.0
    delta: float = 0.0
    gamma: float = 1.0
    sigma: float = 6.0
    g_factor: float = 1.0
    l1: float = 0.0
    l2: float = 0.0
    r0_anisotropy: float = 0.38


@dataclass
class FretState:
    """One conformational state of the molecule.

    Attributes
    ----------
    distance : float
        Mean donor–acceptor distance, Å.
    rho : float
        Rotational correlation time, ns. Unused by the FRET axis; it is what the
        anisotropy axis resolves per state.
    name : str
        Label, for reporting.
    """

    distance: float
    rho: float = 1.0
    name: str = ""


def state_efficiency(state: FretState, optics: Optics, *, n_points: int = 81) -> float:
    """Return the burst-averaged FRET efficiency of a state.

    A burst lasts far longer than the linker samples its accessible volume, so what
    a burst measures is ``∫ p(R) E(R) dR`` — the average of the *efficiency*, not
    the efficiency of the average distance. The two differ by a curvature term that
    grows with the linker width, which is exactly the offset that makes the static
    line bend.

    Parameters
    ----------
    state : FretState
        The conformational state, i.e. its mean donor-acceptor distance.
    optics : Optics
        Förster radius and linker width.
    n_points : int
        Distance samples.

    Returns
    -------
    float
    """
    weights, distances = noncentral_chi_distance_distribution(
        state.distance, optics.sigma, n_points=n_points
    )
    efficiency = 1.0 / (1.0 + (distances / optics.r0) ** 6)
    return float(np.sum(weights * efficiency))


def donor_lifetime_spectrum_of_state(
    state: FretState, optics: Optics, *, donor=None, n_points: int = 81
) -> tuple[np.ndarray, np.ndarray]:
    """Return the donor's FRET-quenched lifetime spectrum for one state.

    The donor-only decay, quenched at every distance the linker distribution
    reaches. Because the linker is static on the nanosecond scale, the result is a
    genuine distribution of lifetimes rather than one averaged lifetime — which is
    what lets the decay shape carry the linker width.

    The algebra is :class:`IMP.bff.FRETSpectrumNode`'s — the same producer the TCSPC
    decay graph quenches its donor with. For a single-exponential donor, which is
    what ``optics.tau_d0`` describes, that reproduces the older closed form
    ``τ(R) = τ_D₀ / (1 + (R₀/R)⁶)`` exactly. For a *multi*-exponential donor it
    does not, and the difference is a correction rather than a regression: the
    transfer rate is fixed by ``R₀`` and the reference lifetime ``τ_D₀`` it was
    determined at, so it is the same for every donor component and the rates add
    (``1/τᵢ + k_T``). Scaling each component's lifetime by one common quench
    factor instead — the previous behaviour — gives each component its own
    ``R₀``, which is not what a Förster radius is.

    The node's trailing donor-only block is dropped here. This function promises
    a *quenched* spectrum, and every invariant a caller can state about one
    ("no lifetime exceeds ``τ_D₀``") would be false of a zero-amplitude
    passenger sitting at ``τ_D₀``. Incomplete labelling reaches the MFD forward
    model as its own species, never through this return value.

    Parameters
    ----------
    state : FretState
        The conformational state.
    optics : Optics
        Förster radius, donor-only lifetime and linker width.
    donor : float or array_like, optional
        Donor-only decay specification (a lifetime, several lifetimes, or
        ``(amplitude, lifetime)`` pairs). Defaults to ``optics.tau_d0``.
    n_points : int
        Distance samples.

    Returns
    -------
    amplitudes, lifetimes : numpy.ndarray
        Flattened over (distance, donor component); amplitudes sum to one.
    """
    donor_x, donor_tau = donor_lifetime_spectrum(
        optics.tau_d0 if donor is None else donor
    )
    weights, distances = noncentral_chi_distance_distribution(
        state.distance, optics.sigma, n_points=n_points
    )
    amplitudes, lifetimes = _fret_spectrum(
        donor_x, donor_tau, weights[0], distances[0], optics
    )
    quenched = weights.shape[-1] * donor_x.size
    amplitudes, lifetimes = amplitudes[:quenched], lifetimes[:quenched]
    total = float(np.sum(amplitudes))
    return (amplitudes / total if total else amplitudes), lifetimes


def acceptor_lifetime_spectrum(
    donor_amplitudes: np.ndarray,
    donor_lifetimes: np.ndarray,
    optics: Optics,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the sensitized acceptor's lifetime spectrum.

    The acceptor is populated by transfer from the donor and decays with its own
    lifetime, so its emission *rises* with the donor's quenched lifetime and falls
    with the acceptor's. Solving ``dA/dt = Σᵢ aᵢ k_T,ᵢ e^{−t/τᵢ} − A/τ_A`` gives, per
    donor component, a pair of terms with equal and opposite amplitude::

        +cᵢ at τ_A  and  −cᵢ at τᵢ,     cᵢ = aᵢ k_T,ᵢ τ_A τᵢ / (τ_A − τᵢ)

    The negative amplitude is physical — it is the rise — and it is why the acceptor
    pattern must be built as a decay and then measured, rather than treated as a
    mixture with weights.

    .. warning::

       **This is the one transform on this module's surface with no producer
       node behind it, and it is therefore the one that can drift.** The decay
       graph's producers cover the donor
       (:class:`IMP.bff.FRETSpectrumNode`) and the polarisation
       (:class:`IMP.bff.PhotophysicsAnisotropySpectrumNode`); nothing in ``IMP.bff`` emits the
       *sensitized acceptor's* spectrum, because no fitted TCSPC model in the
       graph has needed the acceptor rise yet. The transform is a genuine
       addition to the engine — an ``AcceptorSpectrum`` node taking the quenched
       donor spectrum plus ``tau_a`` and ``tau0`` — and it belongs *in* the
       engine rather than beside it. Until that node exists this stays a second
       implementation, stated loudly here rather than hidden behind a fallback
       that reads as if a producer were in use. Recorded in
       ``okf/references/known-issues.md``.

    Parameters
    ----------
    donor_amplitudes, donor_lifetimes : numpy.ndarray
        The FRET-quenched donor spectrum, from
        :func:`donor_lifetime_spectrum_of_state`.
    optics : Optics
        Supplies the acceptor and donor-only lifetimes.

    Returns
    -------
    amplitudes, lifetimes : numpy.ndarray
        Twice as long as the donor spectrum.
    """
    a = np.asarray(donor_amplitudes, dtype=float)
    tau = np.asarray(donor_lifetimes, dtype=float)
    tau_a = float(optics.tau_a)

    # A donor component whose quenched lifetime equals the acceptor's makes the
    # amplitude removable but not evaluable; nudge rather than divide by zero.
    degenerate = np.abs(tau - tau_a) < _DEGENERACY_EPS * max(tau_a, 1.0)
    tau = np.where(degenerate, tau * (1.0 - _DEGENERACY_EPS), tau)

    transfer_rate = np.clip(1.0 / tau - 1.0 / float(optics.tau_d0), 0.0, None)
    c = a * transfer_rate * tau_a * tau / (tau_a - tau)
    return (
        np.concatenate([c, -c]),
        np.concatenate([np.full_like(tau, tau_a), tau]),
    )


def red_probability(efficiency, optics: Optics):
    """Return the probability that a signal photon is detected in the acceptor channel.

    The FRET axis of the histogram is this number, blurred by the shot noise of the
    burst's own signal. Writing the two channels in "green-equivalent" units, where
    ``u`` is what a donor-only molecule would put in the green channel::

        green = u (1 − E)
        red   = u [ γ E + α (1 − E) + δ ]

    so the acceptor-channel probability is their ratio. Every correction lives here,
    in the *model*, and none of them touches the data histogram — which is what lets
    ``γ`` be a free parameter without the fit's own target moving underneath it.

    Parameters
    ----------
    efficiency : array_like
        FRET efficiency, already averaged over the linker distribution.
    optics : Optics
        Supplies gamma, the donor leakage and the direct excitation.

    Returns
    -------
    numpy.ndarray
        Values in ``[0, 1]``.
    """
    e = np.asarray(efficiency, dtype=float)
    green = 1.0 - e
    red = optics.gamma * e + optics.alpha * green + optics.delta
    total = green + red
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.clip(np.where(total > 0, red / total, 0.0), 0.0, 1.0)


@dataclass
class ChannelResponse:
    """One detection channel's instrument response, and the patterns it produces.

    Holds the response over exactly one laser period and turns a lifetime spectrum
    into the micro-time pattern that would be *recorded* in this channel — the
    circular convolution of the response with the periodic decay, because the TAC
    window is the period and a photon whose tail runs past its end reappears at the
    start.

    Doing the convolution once on the *summed* decay rather than once per lifetime
    component is what keeps this affordable: a distance distribution with 81 samples
    costs the same single transform as a single exponential.

    Attributes
    ----------
    irf : numpy.ndarray
        Instrument response over one period, normalised to unit sum.
    dt : float
        Micro-time channel width, ns.
    background_rate : float
        Uncorrelated background count rate in this channel, s⁻¹. Used with each
        burst's observation span to get the expected number of background photons.
    scatter_fraction : float
        Fraction of this channel's *signal* photons that are scattered excitation
        light, whose pattern is the response itself.
    background_pattern : numpy.ndarray, optional
        Measured micro-time distribution of the background photons. ``None`` falls
        back to flat, which is right for dark counts and wrong for the sub-threshold
        fluorescence that dominates the non-burst photons of a real measurement; see
        :meth:`background_moments`.
    """

    irf: np.ndarray
    dt: float
    background_rate: float = 0.0
    scatter_fraction: float = 0.0
    background_pattern: np.ndarray | None = None
    _spectrum: np.ndarray = field(default=None, repr=False, init=False)

    def __post_init__(self):
        """Normalise the response and cache its transform."""
        response = np.asarray(self.irf, dtype=float).ravel()
        if response.size == 0:
            raise ValueError("the instrument response must not be empty")
        total = response.sum()
        if total <= 0.0:
            raise ValueError("the instrument response has no counts")
        self.irf = response / total
        self._spectrum = np.fft.rfft(self.irf)

    @property
    def n_channels(self) -> int:
        """Return the number of micro-time channels in one period."""
        return int(self.irf.size)

    @property
    def period(self) -> float:
        """Return the laser period, ns."""
        return self.n_channels * float(self.dt)

    def _unnormalized_decay(self, amplitudes, lifetimes) -> np.ndarray:
        """Return the periodic decay of a lifetime spectrum, keeping its scale.

        :meth:`decay` normalises, which is right for a pattern and wrong for a
        *branching*: the fraction of a species' photons that lands in the
        parallel channel is the ratio of two channel decays, and normalising each
        first would make that ratio one half by construction. So the sum is kept
        here and divided out one level up.

        Parameters
        ----------
        amplitudes, lifetimes : array_like
            A lifetime spectrum.

        Returns
        -------
        numpy.ndarray
            ``(n_channels,)``, clipped at zero, in units of ``Σ aᵢ τᵢ``.
        """
        a = np.atleast_1d(np.asarray(amplitudes, dtype=float))
        tau = np.atleast_1d(np.asarray(lifetimes, dtype=float))
        if a.shape != tau.shape:
            raise ValueError("amplitudes and lifetimes must have the same shape")
        out = np.zeros(self.n_channels, dtype=float)
        for weight, t in zip(a * tau, tau):
            if weight == 0.0:
                continue
            out += weight * wrapped_exponential_pattern(
                float(t), self.n_channels, self.dt
            )
        return np.clip(out, 0.0, None)

    def decay(self, amplitudes, lifetimes) -> np.ndarray:
        """Return the periodic decay of a lifetime spectrum, before the response.

        Under repeated excitation the recorded decay of component ``i`` is the
        exponential folded onto the period, and every emitted photon lands
        somewhere in the window — so the component's *share* of the photons is
        ``aᵢ τᵢ``, not ``aᵢ``. Getting that wrong reweights a distance distribution
        towards its short-lifetime (high-FRET) tail.

        Parameters
        ----------
        amplitudes, lifetimes : array_like
            A lifetime spectrum. Amplitudes may be negative (a sensitized acceptor's
            rise is exactly that).

        Returns
        -------
        numpy.ndarray
            ``(n_channels,)``, summing to one.
        """
        out = self._unnormalized_decay(amplitudes, lifetimes)
        total = out.sum()
        if total <= 0.0:
            raise ValueError("the lifetime spectrum produces no emission")
        return out / total

    def _record(self, decay: np.ndarray) -> np.ndarray:
        """Convolve a periodic decay with the response and normalise it.

        Parameters
        ----------
        decay : numpy.ndarray
            ``(n_channels,)`` periodic decay.

        Returns
        -------
        numpy.ndarray
            ``(n_channels,)``, summing to one where there is any signal at all.
        """
        pattern = np.real(
            np.fft.irfft(
                self._spectrum * np.fft.rfft(decay), n=self.n_channels
            )
        )
        pattern = np.clip(pattern, 0.0, None)
        total = pattern.sum()
        return pattern / total if total > 0 else pattern

    def pattern(self, amplitudes, lifetimes) -> np.ndarray:
        """Return the recorded micro-time pattern of a lifetime spectrum.

        Parameters
        ----------
        amplitudes, lifetimes : array_like
            A lifetime spectrum.

        Returns
        -------
        numpy.ndarray
            ``(n_channels,)``, summing to one.
        """
        return self._record(self.decay(amplitudes, lifetimes))

    def signal_moments(self, amplitudes, lifetimes) -> tuple[float, float]:
        """Return the mean and variance of this channel's *signal* micro times.

        Signal means fluorescence plus scattered excitation light — everything but
        the uncorrelated background, whose weight depends on the burst and therefore
        cannot be folded in here.

        Parameters
        ----------
        amplitudes, lifetimes : array_like
            A lifetime spectrum.

        Returns
        -------
        mean, variance : float
            In nanoseconds and nanoseconds squared.
        """
        fluorescence = pattern_moments(self.pattern(amplitudes, lifetimes), self.dt)
        if self.scatter_fraction <= 0.0:
            return fluorescence
        scatter = pattern_moments(self.irf, self.dt)
        mean, variance = mixture_moments(
            [1.0 - self.scatter_fraction, self.scatter_fraction],
            [fluorescence[0], scatter[0]],
            [fluorescence[1], scatter[1]],
        )
        return float(mean), float(variance)

    def background_moments(self) -> tuple[float, float]:
        """Return the moments of the uncorrelated background in this channel.

        Flat over the window *only when nothing better is known*: dark counts and
        after-pulses carry no timing information at all.

        When ``background_pattern`` is supplied it is used instead, and it usually
        should be. The photons this rate is estimated from are the non-burst
        photons, and in a single-molecule measurement those are dominated by
        **fluorescence from molecules too dim to make the burst threshold** — not by
        dark counts. Their micro times are therefore an ordinary decay, not flat,
        and assuming flat puts the background's mean delay at half the laser period
        instead of near the IRF. That error lands squarely on the lifetime axis: it
        drags the predicted mean micro time of every burst upward in proportion to
        the background's share of its photons, and on a measurement with a
        realistic non-burst rate it is worth *several nanoseconds* — far larger
        than the differences the axis exists to resolve.

        Returns
        -------
        mean, variance : float
        """
        if self.background_pattern is None:
            return background_moments(self.n_channels, self.dt)
        pattern = np.asarray(self.background_pattern, dtype=float)
        total = pattern.sum()
        if total <= 0.0:
            return background_moments(self.n_channels, self.dt)
        times = np.arange(pattern.size) * float(self.dt)
        weights = pattern / total
        mean = float(weights @ times)
        return mean, float(weights @ (times * times) - mean * mean)


def perrin_anisotropy(lifetime, rho: float, r0_anisotropy: float):
    """Return the steady-state anisotropy the Perrin relation predicts.

    ``r_ss = r₀ / (1 + τ/ρ)`` — the time-integrated anisotropy of a decay of
    lifetime ``τ`` depolarizing with rotational correlation time ``ρ``.

    This is here as a **prediction, not an input.** The forward model builds the
    parallel and perpendicular patterns from ``r(t)`` and integrates them; that the
    result satisfies Perrin is then a check on the machinery rather than something
    imposed on it. A model that took ``r_ss`` as a parameter would agree with Perrin
    by construction and could not be wrong.

    Parameters
    ----------
    lifetime : array_like or float
        Fluorescence lifetime, ns.
    rho : float
        Rotational correlation time, ns.
    r0_anisotropy : float
        Fundamental anisotropy.

    Returns
    -------
    numpy.ndarray or float
    """
    tau = np.asarray(lifetime, dtype=float)
    if rho <= 0.0:
        return np.zeros_like(tau)
    return r0_anisotropy / (1.0 + tau / float(rho))


def polarized_patterns(
    response: ChannelResponse,
    amplitudes,
    lifetimes,
    rho: float,
    optics: Optics,
):
    """Split a decay into the parallel and perpendicular patterns actually recorded.

    A polarisation is a **spectrum** transform, not a curve one: the measured decay
    is the product of the fluorescence decay and ``r(t)``, and a product of two sums
    of exponentials is a sum of exponentials. So the split is
    :class:`IMP.bff.PhotophysicsAnisotropySpectrumNode`'s — the producer the TCSPC decay graph
    polarises with — and this function only folds the two spectra onto the laser
    period and convolves them with the response::

        f_VV = f · (1 + (2 − 3 l₁) r),   f_VH = f · (1 − (1 − 3 l₂) r) / G

    ``G`` is a *detection sensitivity*, so it divides the whole perpendicular
    channel rather than only its depolarization term, and it is applied here rather
    than through the node's ``g`` port — :func:`_polarized_spectrum` says why, and
    says what goes wrong if it is not.

    .. rubric:: Folding the product, not the folded decay

    The anisotropy multiplies the emission at a photon's *true* age, and under
    repeated excitation a photon detected at micro time ``t`` may be ``t``,
    ``t + T``, ``t + 2T`` … old. Folding the fluorescence decay first and then
    multiplying by ``r(t)`` — which is what building the pair from a time-domain VM
    decay does — gives the wrapped photons the anisotropy of a *younger* photon
    than they are, so it over-polarises the wrapped tail. Building the product as a
    spectrum and folding each of its components carries every photon's own age,
    which is the arrangement the fitted models use. The two agree to the extent
    that nothing wraps.

    Parameters
    ----------
    response : ChannelResponse
        Supplies the instrument response, the channel width and the period.
    amplitudes, lifetimes : array_like
        The emitting species' lifetime spectrum.
    rho : float
        Rotational correlation time, ns.
    optics : Optics
        Supplies ``g_factor``, ``l1``, ``l2`` and ``r0_anisotropy``.

    Returns
    -------
    parallel, perpendicular : numpy.ndarray
        Recorded patterns, each normalised to unit sum.
    p_parallel : float
        Fraction of this species' photons recorded in the parallel channel — the
        branching the anisotropy axis needs, exactly as the acceptor probability is
        the branching the FRET axis needs.
    """
    vv = response._unnormalized_decay(
        *_polarized_spectrum(amplitudes, lifetimes, rho, optics, "vv")
    )
    # The perpendicular detector is 1/G as sensitive, and that applies to
    # everything it collects -- including the parallel light l2 mixed into it.
    vh = response._unnormalized_decay(
        *_polarized_spectrum(amplitudes, lifetimes, rho, optics, "vh")
    ) / float(optics.g_factor)

    total = vv.sum() + vh.sum()
    p_parallel = float(vv.sum() / total) if total > 0 else 0.5
    return response._record(vv), response._record(vh), p_parallel
