"""Coupled per-detector fluorescence decays for smFRET labeling states.

In a multi-detector smFRET / ALEX / PIE experiment a single species does *not*
share one decay across channels — each detection channel sees a different,
physically-coupled decay:

- **green**  (donor emission, donor excitation): the donor decay, FRET-quenched
  in a donor+acceptor (DA) species, unquenched in a donor-only species.
- **red**    (acceptor emission, donor excitation): the FRET-*sensitized*
  acceptor — its rise is governed by the donor decay (see
  :func:`chisurf.core.fluorescence.fret.acceptor.da_a0_to_ad`) — plus spectral
  donor leakage (``alpha``) and directly-excited acceptor (``delta``).
- **yellow** (acceptor emission, acceptor excitation): the acceptor's own decay.

The mixing between channels is set by the Hellenkamp correction factors
(``alpha`` leakage, ``beta`` excitation-flux, ``gamma`` detection/QY, ``delta``
direct excitation), which callers usually seed from an instrument calibration
and may override per species.

This module builds those coupled channel decays for the three common labeling
states — donor-only (``d_only``), FRET pair (``da``), acceptor-only
(``a_only``) — optionally split into parallel/perpendicular sub-channels with a
per-chromophore anisotropy ``r(t) = (r0 - r_inf)·exp(-t/rho) + r_inf``.

Fractions of the labeling states are **not** modeled here — each state is one
filter component; fFCS unmixing recovers their populations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.core.fluorescence.fret.acceptor import da_a0_to_ad
from chisurf.core.fluorescence.general import (
    calculate_fluorescence_decay,
    distance_to_fret_rate_constant,
)
from chisurf.core.fluorescence.tcspc.convolve import convolve_decay_nb, periodic_shift

STATES = ("d_only", "da", "a_only")
_ROLES = ("parallel", "perpendicular")


@dataclass
class CrosstalkFactors:
    """Hellenkamp channel-mixing factors (all dimensionless).

    These stay the user-facing knobs (what people are used to), but the amplitude
    mixing is applied through the full **excitation** and **emission** matrices
    they induce, so the relative amplitudes of the coupled channel decays are
    correct rather than approximated.

    - ``excitation[laser, chromophore]`` — lasers ``(donor, acceptor)`` × chromophores
      ``(donor, acceptor)``: ``[[1, δ], [0, β]]`` (donor laser excites the donor and,
      by ``δ``, the acceptor directly; the acceptor laser excites the acceptor by ``β``).
    - ``emission[chromophore, detector]`` — chromophores ``(donor, acceptor)`` × detectors
      ``(green, red)``: ``[[1, α], [0, γ]]`` (donor detected in green and, by ``α`` leakage,
      in red; acceptor detected in red by ``γ``).
    """

    alpha: float = 0.0   # donor leakage into the acceptor (red) channel
    beta: float = 1.0    # excitation-flux ratio (acceptor vs donor excitation)
    gamma: float = 1.0   # detection/quantum-yield ratio (acceptor vs donor)
    delta: float = 0.0   # direct acceptor excitation by the donor-excitation laser

    def excitation_matrix(self) -> np.ndarray:
        """``[laser, chromophore]`` excitation matrix (donor/acceptor × donor/acceptor)."""
        return np.array([[1.0, float(self.delta)], [0.0, float(self.beta)]])

    def emission_matrix(self) -> np.ndarray:
        """``[chromophore, detector]`` emission matrix (donor/acceptor × green/red)."""
        return np.array([[1.0, float(self.alpha)], [0.0, float(self.gamma)]])


@dataclass
class Anisotropy:
    """Per-chromophore time-resolved anisotropy and the detection G-factor.

    Each chromophore's anisotropy is a **spectrum** —
    ``r(t) = Σ_i b_i·exp(-t/ρ_i) + r∞`` — given as a list of
    ``{"amplitude": b_i, "rho": ρ_i}`` components (multi-exponential rotation:
    fast local wobble + slower global tumbling, etc.). The single-exponential
    ``donor_r0``/``donor_rho`` (and acceptor) fields are a convenience default
    used only when the corresponding spectrum list is empty.
    """

    donor_r0: float = 0.38
    donor_rho: float = 1.0        # donor rotational correlation time (ns)
    acceptor_r0: float = 0.38
    acceptor_rho: float = 1.0     # acceptor rotational correlation time (ns)
    r_inf: float = 0.0            # residual (hindered) anisotropy
    g_factor: float = 1.0         # perpendicular-channel detection correction
    donor_spectrum: Any = None    # [{amplitude, rho}] — overrides donor_r0/rho
    acceptor_spectrum: Any = None  # [{amplitude, rho}] — overrides acceptor_r0/rho

    def _rows(self, chromophore: str) -> list[dict]:
        spectrum = self.donor_spectrum if chromophore == "donor" else self.acceptor_spectrum
        if spectrum:
            return list(spectrum)
        r0 = self.donor_r0 if chromophore == "donor" else self.acceptor_r0
        rho = self.donor_rho if chromophore == "donor" else self.acceptor_rho
        return [{"amplitude": float(r0), "rho": float(rho)}]

    def r_of_t(self, chromophore: str, time_ns: np.ndarray) -> np.ndarray:
        r = np.full_like(time_ns, float(self.r_inf), dtype=float)
        for row in self._rows(chromophore):
            b = float(row.get("amplitude", 0.0))
            rho = max(float(row.get("rho", 1.0)), 1e-6)
            r = r + b * np.exp(-time_ns / rho)
        return r


@dataclass
class FretSpecies:
    """One labeling state and its photophysics (no populations)."""

    state: str = "da"
    donor_spectrum: Any = field(default_factory=lambda: [1.0, 4.0])
    acceptor_spectrum: Any = field(default_factory=lambda: [1.0, 2.0])
    # FRET input — either a transfer efficiency, or a (distributed) distance.
    fret_mode: str = "efficiency"           # "efficiency" | "distance"
    transfer_efficiency: float = 0.5
    # Distance distribution: Gaussian components (mean Å, sigma Å, fraction),
    # matching the TCSPC FRET fits' distance model. Empty → single ``distance``.
    distance_rows: Any = field(default_factory=lambda: [{"mean": 50.0, "sigma": 6.0, "amplitude": 1.0}])
    distance: float = 50.0                  # single-distance fallback (Å)
    distance_distribution: str = "gaussian"  # "gaussian" | "gaussian_3d"
    distance_samples: int = 81
    forster_radius: float = 52.0            # R0 (Å)
    kappa2: float = 2.0 / 3.0
    x_donly: float = 0.0                    # donor-only fraction within the DA population
    crosstalk: CrosstalkFactors = field(default_factory=CrosstalkFactors)
    anisotropy: Anisotropy = field(default_factory=Anisotropy)
    # Optional explicit matrices override the ones induced by ``crosstalk``.
    excitation: Any = None
    emission: Any = None

    def excitation_matrix(self) -> np.ndarray:
        if self.excitation is not None:
            return np.asarray(self.excitation, dtype=float)
        return self.crosstalk.excitation_matrix()

    def emission_matrix(self) -> np.ndarray:
        if self.emission is not None:
            return np.asarray(self.emission, dtype=float)
        return self.crosstalk.emission_matrix()


def _spectrum_pairs(spectrum: Any) -> np.ndarray:
    values = np.asarray(spectrum, dtype=float).ravel()
    if values.size < 2 or values.size % 2:
        raise ValueError("a lifetime spectrum needs (amplitude, lifetime) pairs")
    return values


def _ideal_decay(spectrum: np.ndarray, time_ns: np.ndarray) -> np.ndarray:
    _, decay = calculate_fluorescence_decay(spectrum, time_ns, normalize=False)
    return np.maximum(np.asarray(decay, dtype=float), 0.0)


def _amp_weighted_lifetime(spectrum: np.ndarray) -> float:
    amps = spectrum[0::2]
    taus = spectrum[1::2]
    total = amps.sum()
    return float((amps * taus).sum() / total) if total > 0 else float(taus.mean())


def _distance_components(species: FretSpecies) -> list[tuple[float, float, float]]:
    """Return the distance distribution as ``(amplitude, mean, sigma)`` Gaussians."""
    comps: list[tuple[float, float, float]] = []
    for row in (species.distance_rows or []):
        mean = float(row.get("mean", row.get("distance", 0.0)))
        sigma = float(row.get("sigma", 0.0))
        amp = float(row.get("amplitude", 1.0))
        if mean > 0.0 and amp != 0.0:
            comps.append((amp, mean, sigma))
    if not comps:
        comps = [(1.0, float(species.distance), 0.0)]
    return comps


def _fret_active_donor_spectrum(species: FretSpecies, donor: np.ndarray, tau0: float) -> np.ndarray:
    """Donor spectrum quenched by a *distributed* FRET rate (reuses the fit machinery).

    Combines every donor lifetime with every sampled distance of the Gaussian
    distance distribution, using the same ``distance_to_fret_rate_constant`` and
    distance grid as the TCSPC FRET fits.
    """
    from chisurf.core.fluorescence.decay import _distance_grid

    r0 = float(species.forster_radius)
    kappa2 = float(species.kappa2)
    n_samples = int(getattr(species, "distance_samples", 81))
    kind = str(getattr(species, "distance_distribution", "gaussian"))
    amps: list[float] = []
    taus: list[float] = []
    for amp_c, mean, sigma in _distance_components(species):
        distances, weights = _distance_grid(mean, sigma, n_samples, kind)
        k_fret = distance_to_fret_rate_constant(distances, r0, tau0, kappa2)
        for a_j, tau_j in zip(donor[0::2], donor[1::2]):
            rate0 = 1.0 / float(tau_j)
            for w_k, k_k in zip(weights, k_fret):
                amps.append(float(a_j) * amp_c * float(w_k))
                taus.append(1.0 / (rate0 + float(k_k)))
    spectrum = np.empty(len(amps) * 2, dtype=float)
    spectrum[0::2] = amps
    spectrum[1::2] = taus
    return spectrum


def _resolve_fret(species: FretSpecies, donor: np.ndarray) -> tuple[np.ndarray, float]:
    """Return the FRET-active (quenched) donor spectrum and the transfer efficiency."""
    tau_d0 = _amp_weighted_lifetime(donor)
    if species.fret_mode == "distance":
        quenched = _fret_active_donor_spectrum(species, donor, tau_d0)
        tau_da = _amp_weighted_lifetime(quenched)
        efficiency = 1.0 - tau_da / tau_d0 if tau_d0 > 0 else 0.5
        return quenched, float(np.clip(efficiency, 1e-6, 1.0 - 1e-6))
    # Efficiency mode: shorten every donor lifetime by (1 - E).
    efficiency = float(np.clip(species.transfer_efficiency, 1e-6, 1.0 - 1e-6))
    quenched = donor.copy()
    quenched[1::2] = quenched[1::2] * (1.0 - efficiency)
    return quenched, efficiency


# Channels are (detector, laser) pairs; detectors (green=0, red=1), lasers (donor=0, acceptor=1).
_CHANNELS = {"green": (0, 0), "red": (1, 0), "yellow": (1, 1)}


def _channel_contributions(
    species: FretSpecies, time_ns: np.ndarray
) -> dict[str, list[tuple[np.ndarray, str]]]:
    """Ideal (pre-IRF) per-channel decays as ``[(decay, chromophore), ...]``.

    Amplitudes come from the full excitation/emission matrices, so the relative
    weights of donor / sensitized-acceptor / directly-excited-acceptor across the
    green/red/yellow channels are physically consistent.
    """
    donor = _spectrum_pairs(species.donor_spectrum)
    acceptor = _spectrum_pairs(species.acceptor_spectrum)
    state = species.state
    if state not in STATES:
        raise ValueError(f"unknown labeling state {state!r}; use one of {STATES}")
    donor_present = state in ("d_only", "da")
    acceptor_present = state in ("a_only", "da")
    is_fret = state == "da"

    exc = species.excitation_matrix()   # [laser, chromophore]
    em = species.emission_matrix()      # [chromophore, detector]
    zero = np.zeros_like(time_ns)

    # Emission time-courses (shapes) per chromophore.
    if is_fret:
        quenched, efficiency = _resolve_fret(species, donor)
        donor_da_active = _ideal_decay(quenched, time_ns)
        donor_dd = _ideal_decay(donor, time_ns)
        x = float(np.clip(species.x_donly, 0.0, 1.0))
        donor_shape = (1.0 - x) * donor_da_active + x * donor_dd
        sensitized = (1.0 - x) * np.maximum(
            da_a0_to_ad(time_ns, donor_da_active, acceptor, efficiency), 0.0
        )
    else:
        donor_shape = _ideal_decay(donor, time_ns) if donor_present else zero
        sensitized = zero
    acceptor_a0 = _ideal_decay(acceptor, time_ns) if acceptor_present else zero

    out: dict[str, list[tuple[np.ndarray, str]]] = {}
    for channel, (det, laser) in _CHANNELS.items():
        terms: list[tuple[np.ndarray, str]] = []
        if donor_present:
            amp = float(em[0, det] * exc[laser, 0])
            if amp:
                terms.append((amp * donor_shape, "donor"))
        if acceptor_present:
            # Sensitized emission is driven by donor excitation of that laser.
            amp_sens = float(em[1, det] * exc[laser, 0])
            if is_fret and amp_sens:
                terms.append((amp_sens * sensitized, "acceptor"))
            amp_direct = float(em[1, det] * exc[laser, 1])
            if amp_direct:
                terms.append((amp_direct * acceptor_a0, "acceptor"))
        out[channel] = terms
    return out


def normalize_irf(irf: Any, n_bins: int) -> np.ndarray | None:
    """Return the IRF cropped/zero-padded to ``n_bins`` and **normalized to unit sum**."""
    if irf is None:
        return None
    response = np.asarray(irf, dtype=float).ravel()
    if response.size != int(n_bins):
        resized = np.zeros(int(n_bins), dtype=float)
        take = min(response.size, int(n_bins))
        resized[:take] = response[:take]
        response = resized
    total = response.sum()
    return response / total if total > 0 else response


def _apply_irf(decay: np.ndarray, irf, dt: float, time_shift: float,
               period: float | None = None) -> np.ndarray:
    if irf is None:
        return decay
    response = normalize_irf(irf, decay.size)
    if time_shift:
        response = periodic_shift(response, float(time_shift) / float(dt))
    if period is not None and float(period) > 0.0:
        # Periodic (laser-repetition) convolution over the window: circular
        # convolution so the unrelaxed decay of earlier pulses wraps in.
        conv = np.real(np.fft.ifft(np.fft.fft(decay) * np.fft.fft(response))) * float(dt)
        return np.maximum(conv, 0.0)
    out = convolve_decay_nb(decay, response, 0, decay.size, float(dt))
    return np.maximum(np.asarray(out, dtype=float), 0.0)


def fret_species_patterns(
    n_bins: int,
    species: FretSpecies,
    *,
    dt: float = 0.05,
    irf: Any | None = None,
    time_shift: float = 0.0,
    polarized: bool = False,
    normalize: bool = True,
) -> dict[str, np.ndarray]:
    """Return the coupled green/red/yellow decays for one labeling state.

    Parameters
    ----------
    n_bins, dt : int, float
        Micro-time histogram size and bin width (ns).
    species : FretSpecies
        The labeling state, donor/acceptor spectra, FRET input, crosstalk and
        anisotropy.
    irf : array-like or dict, optional
        Instrument response convolved into the channels (always normalized to unit
        sum). A single array applies to every channel; a ``{channel: irf}`` mapping
        gives each detector its own independent IRF. ``None`` returns ideal decays
        (the FRET/decay-calc path leaves IRF to the per-detector detector settings).
    time_shift : float
        Sub-bin periodic IRF colour shift (ns).
    polarized : bool
        When true, each channel is split into ``*_parallel`` / ``*_perpendicular``
        using the per-chromophore anisotropy; otherwise intensity channels
        ``green`` / ``red`` / ``yellow`` are returned.
    normalize : bool
        Scale the whole set by one factor so the summed integral is 1 — preserves
        the physically-meaningful ratios *between* channels.

    Returns
    -------
    dict[str, numpy.ndarray]
        Channel name → decay histogram (length ``n_bins``).
    """
    n = int(n_bins)
    if n <= 0:
        raise ValueError("n_bins must be positive")
    if dt <= 0:
        raise ValueError("dt must be positive")
    time_ns = np.arange(n, dtype=float) * float(dt)
    contributions = _channel_contributions(species, time_ns)
    aniso = species.anisotropy

    def channel_irf(channel: str):
        return irf.get(channel) if isinstance(irf, dict) else irf

    patterns: dict[str, np.ndarray] = {}
    for channel, terms in contributions.items():
        ch_irf = channel_irf(channel)
        if polarized:
            par = np.zeros(n, dtype=float)
            perp = np.zeros(n, dtype=float)
            for decay, chromophore in terms:
                r = aniso.r_of_t(chromophore, time_ns)
                par += decay * (1.0 + 2.0 * r) / 3.0
                perp += decay * (1.0 - r) / 3.0 * float(aniso.g_factor)
            patterns[f"{channel}_parallel"] = _apply_irf(par, ch_irf, dt, time_shift)
            patterns[f"{channel}_perpendicular"] = _apply_irf(perp, ch_irf, dt, time_shift)
        else:
            intensity = np.zeros(n, dtype=float)
            for decay, _ in terms:
                intensity += decay
            patterns[channel] = _apply_irf(intensity, ch_irf, dt, time_shift)

    if normalize:
        total = sum(float(p.sum()) for p in patterns.values())
        if total > 0:
            for key in patterns:
                patterns[key] = patterns[key] / total
    return patterns


def _component_irf(component: dict, n_bins: int, dt: float):
    """Build the IRF for a persisted component (experimental file or Gaussian)."""
    import pathlib

    path = str(component.get("irf_path") or "")
    if path and pathlib.Path(path).is_file():
        p = pathlib.Path(path)
        return np.load(p) if p.suffix.lower() == ".npy" else np.loadtxt(p)
    fwhm = float(component.get("irf_fwhm_ns", 0.0) or 0.0)
    if fwhm > 0.0:
        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        time = np.arange(int(n_bins), dtype=float) * float(dt)
        return synthetic_irf(time, 2.0 * fwhm, fwhm, shape=float(component.get("irf_skew", 0.0)))
    return None


def _channel_for_detector(name: str) -> str:
    """Map a detector name to its FRET colour channel (green / red / yellow)."""
    lowered = str(name).lower()
    for channel in ("green", "red", "yellow"):
        if channel in lowered:
            return channel
    return "green"


def fret_species_detector_patterns(
    component: dict,
    detector_names: list[str],
    n_bins: int,
    irf_for_detector=None,
) -> dict[str, np.ndarray]:
    """Expand a ``fret_species`` component into per-detector decay patterns.

    Each detector name is mapped to its colour channel (green/red/yellow) and
    assigned the corresponding coupled decay. The decay is generated *ideal*
    (no IRF); each detector then gets its **own** IRF via ``irf_for_detector`` —
    a ``name -> irf array`` callable, normally the FCS detector settings — which
    is normalized to unit sum before convolution. A ``__default__`` alias is added.
    """
    species = fret_species_from_dict(component)
    dt = float(component.get("bin_width", 0.05))
    time_shift = float(component.get("time_shift_ns", 0.0))
    period = float(component.get("period_ns", 0.0)) or None
    channels = fret_species_patterns(
        int(n_bins), species, dt=dt, irf=None, polarized=False, normalize=True,
    )
    patterns: dict[str, np.ndarray] = {}
    for name in detector_names:
        decay = np.asarray(channels[_channel_for_detector(name)], dtype=float)
        if irf_for_detector is not None:
            irf = normalize_irf(irf_for_detector(name), int(n_bins))
            if irf is not None:
                decay = _apply_irf(decay, irf, dt, time_shift, period=period)
        patterns[name] = decay
    if patterns:
        patterns.setdefault("__default__", next(iter(patterns.values())))
    else:
        patterns = {"__default__": np.asarray(channels["green"], dtype=float)}
    return patterns


def fret_species_from_dict(component: dict) -> FretSpecies:
    """Build a :class:`FretSpecies` from a persisted ``fret_species`` source dict."""
    ct = component.get("crosstalk", {}) or {}
    an = component.get("anisotropy", {}) or {}
    return FretSpecies(
        state=str(component.get("state", "da")),
        donor_spectrum=component.get("donor_spectrum", [1.0, 4.0]),
        acceptor_spectrum=component.get("acceptor_spectrum", [1.0, 2.0]),
        fret_mode=str(component.get("fret_mode", "efficiency")),
        transfer_efficiency=float(component.get("transfer_efficiency", 0.5)),
        distance_rows=component.get("distance_rows") or [{"mean": float(component.get("distance", 50.0)),
                                                          "sigma": 0.0, "amplitude": 1.0}],
        distance=float(component.get("distance", 50.0)),
        distance_distribution=str(component.get("distance_distribution", "gaussian")),
        distance_samples=int(component.get("distance_samples", 81)),
        forster_radius=float(component.get("forster_radius", 52.0)),
        kappa2=float(component.get("kappa2", 2.0 / 3.0)),
        x_donly=float(component.get("x_donly", 0.0)),
        crosstalk=CrosstalkFactors(
            alpha=float(ct.get("alpha", 0.0)), beta=float(ct.get("beta", 1.0)),
            gamma=float(ct.get("gamma", 1.0)), delta=float(ct.get("delta", 0.0)),
        ),
        anisotropy=Anisotropy(
            donor_r0=float(an.get("donor_r0", 0.38)), donor_rho=float(an.get("donor_rho", 1.0)),
            acceptor_r0=float(an.get("acceptor_r0", 0.38)),
            acceptor_rho=float(an.get("acceptor_rho", 1.0)),
            r_inf=float(an.get("r_inf", 0.0)), g_factor=float(an.get("g_factor", 1.0)),
            donor_spectrum=an.get("donor_spectrum") or None,
            acceptor_spectrum=an.get("acceptor_spectrum") or None,
        ),
    )
