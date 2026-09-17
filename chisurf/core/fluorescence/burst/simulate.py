"""Simulate an ALEX smFRET experiment with defined parameters (tttrlib photons).

Testing an analysis against numbers it was fed is worth little; testing it
against a *photon stream* generated from known physics is worth a lot. This
module builds that stream with tttrlib's confocal simulator: molecules diffuse
through a focus, two alternating lasers excite them, and every photon carries a
detector, a macro time and a micro time drawn from the right decay.

Everything the accurate-FRET correction is supposed to recover is a declared
input here — the FRET efficiencies of the populations, the detection factor
``gamma``, the leakage ``alpha``, the direct excitation ``delta``, the
excitation-flux ratio ``beta``, the donor lifetime and the linker width, the
backgrounds, and the fractions of donor-only and acceptor-only molecules. The
result is a real :class:`tttrlib.TTTR` object that can be burst-searched,
exported, and pushed through the same pipeline as a measurement.

Photon streams. Each photon is labelled by *which laser excited it* and *which
detector saw it*, and that pair is encoded in the routing channel, exactly as an
ALEX/PIE analysis defines its detection windows:

===========  =======================================  ==========
routing      meaning                                  alias
===========  =======================================  ==========
``0``        donor excitation → donor detector        ``I_DD``
``1``        donor excitation → acceptor detector     ``I_DA``
``2``        acceptor excitation → donor detector     (leakage)
``3``        acceptor excitation → acceptor detector  ``I_AA``
===========  =======================================  ==========

The brightness of each species in each stream *is* the definition of the
correction factors, so recovering them is a closed test:

    I_DD = (1−E)·B,  I_DA = γ·E·B + α·I_DD + δ·I_AA,  I_AA = β·γ·B

which places a 1:1 labelled species at ``S = 0.5``.

Micro-times. A FRET population's donor decay is the multi-exponential decay of a
Gaussian-broadened distance (:func:`~chisurf.core.fluorescence.fret.lines.fret_lifetime_spectrum`),
so the mean micro-time of its donor photons is the fluorescence-averaged
lifetime ⟨τ⟩_F — the x-axis of the static FRET line. The simulated populations
therefore lie *on* that line by construction, which is what makes the
lifetime-assisted calibration testable. One simplification: tttrlib carries one
decay per species, so acceptor photons of a FRET species inherit the donor decay
unless ``tau_a`` is given a *sensitised* spectrum via ``acceptor_decay=True``.

MFD mode. Set ``alex=False`` for the classic single-laser, polarization-resolved
measurement that 2D-MFD analysis reads: one excitation, green and red detectors
each split into parallel and perpendicular, on the routing channels the burst
pipeline expects.

===========  ==========================  ==========
routing      meaning                     alias
===========  ==========================  ==========
``0``        green, parallel             ``G_par``
``8``        green, perpendicular        ``G_perp``
``1``        red, parallel               ``R_par``
``9``        red, perpendicular          ``R_perp``
===========  ==========================  ==========

Dynamics. ``rate_matrix`` (``K[target, source]``, Hz) makes the FRET populations
*interconvert during a burst*: a molecule diffusing through the focus switches
conformation on the simulated clock, so a burst caught mid-exchange carries
photons from both states. The engine evolves the continuous-time Markov chain
itself and logs every transition, so the occupation times are ground truth rather
than a reconstruction. Singly labelled species never exchange.

Polarization is a **state**, not a post-processing step. Each labelling species
is simulated as two species — a parallel and a perpendicular emission mode —
each emitting into its own detectors and carrying its own polarized decay
spectrum, with the modes interconverting through the *excitation-scaled* rate
matrix so that successive photons are independent. That reproduces the joint
distribution over (channel, micro time) exactly, including the depolarization of
the anisotropy over the fluorescence lifetime.

The engine's own ``r0``/``D_rot`` parameters are deliberately unused: they are
described in its source as reviving a legacy rotational-diffusion model, and they
route parallel/perpendicular into channels 0/1 *instead of* by colour, whereas
MFD needs colour × polarization. The general encoding — a species is any emitting
state, carrying its own per-channel brightness and micro-time pattern — is
written up in ``okf/references/simengine-species-encoding.md``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field, replace

import numpy as np

from chisurf.core.fluorescence.fret.lines import (
    distance_for_efficiency,
    fret_lifetime_spectrum,
    lifetime_averages,
)

__all__ = [
    "SmfretParameters",
    "SimulatedSmfret",
    "simulate_smfret",
    "MFD_STREAMS",
    "REGIMES",
    "rate_matrix_for",
]

#: Routing channel per (laser, detector) pair — the four ALEX photon streams.
STREAMS = {"i_dd": 0, "i_da": 1, "i_ad": 2, "i_aa": 3}

#: Routing channel per (colour, polarization) pair — the MFD detector convention.
#: The burst pipeline discovers ``green`` as ``[0, 8]`` and ``red`` as ``[1, 9]``.
MFD_STREAMS = {"g_par": 0, "g_perp": 8, "r_par": 1, "r_perp": 9}

#: Engine detection channel per (colour, polarization), before the remap above.
_ENGINE_TO_MFD = np.array(
    [
        MFD_STREAMS["g_par"],
        MFD_STREAMS["g_perp"],
        MFD_STREAMS["r_par"],
        MFD_STREAMS["r_perp"],
    ],
    dtype=np.int8,
)

#: Mode switches per emitted photon. Photoselection is redrawn for every emission,
#: so the two modes must interconvert much faster than the molecule emits; the
#: rate is excitation-scaled, so this ratio holds everywhere in the focus.
_PHOTOSELECTION_SPEED = 200.0


#: Exchange regimes, named in **transitions per burst** rather than in Hz. A rate
#: only means something relative to how long a molecule is watched: the same
#: 1 kHz is static in a 0.1 ms burst and fully averaged in a 20 ms one, and it is
#: the product that decides whether a fit can see the exchange at all.
REGIMES: dict[str, float] = {
    "static": 0.0,
    "slow": 0.05,
    "intermediate": 1.5,
    "fast": 60.0,
}


def rate_matrix_for(regime, *, mean_duration: float, populations=(0.5, 0.5)):
    """Return the two-state rate matrix giving a regime at a burst duration.

    Exchange is only meaningful relative to the observation window, so a regime is
    named in transitions per burst and converted here. The two rates are then fixed
    by that total together with the equilibrium populations, which is the only way
    to move the timescale without also moving the populations — vary one rate alone
    and the fit sees a different mixture rather than a different speed.

    Parameters
    ----------
    regime : str or float
        A key of :data:`REGIMES`, or a number of transitions per burst.
    mean_duration : float
        Mean burst duration, seconds.
    populations : sequence of float
        Equilibrium populations of the two states.

    Returns
    -------
    numpy.ndarray or None
        ``K[target, source]`` in Hz, or ``None`` for a static mixture.
    """
    per_burst = REGIMES[regime] if isinstance(regime, str) else float(regime)
    if per_burst <= 0.0:
        return None
    weights = np.clip(np.asarray(populations, dtype=float), 1e-9, None)
    weights = weights / weights.sum()
    # Transitions per burst counts *both* directions, and the process spends
    # populations[i] of its time in state i, so at equilibrium the observed
    # transition rate of a two-state system is 2 * p0 * k01.
    total = per_burst / float(mean_duration)
    k01 = total / (2.0 * weights[0])
    k10 = k01 * weights[0] / weights[1]
    return np.array([[0.0, k10], [k01, 0.0]])


@dataclass(frozen=True)
class SmfretParameters:
    """Every declared parameter of a simulated ALEX smFRET experiment.

    Attributes
    ----------
    efficiencies : tuple of float
        True FRET efficiency of each doubly labelled population.
    populations : tuple of float, optional
        Mean number of molecules of each FRET population in the box; defaults to
        an equal split of ``concentration``.
    donor_only, acceptor_only : float
        Mean number of singly labelled molecules in the box (the reference
        populations the calibration finds by itself).
    concentration : float
        Total mean number of doubly labelled molecules in the box.
    gamma, alpha, beta, delta : float
        The correction factors baked into the stream brightnesses: detection /
        quantum-yield ratio, donor leakage, excitation-flux ratio and direct
        acceptor excitation.
    tau_d0, tau_a : float
        Donor-only and acceptor lifetimes (ns).
    linker_sigma, r0 : float
        Width of the linker distance distribution and Förster radius (Å); they
        set the donor decay of each FRET population.
    brightness : float
        Donor brightness ``B`` (detected photons per ms per molecule at the focus
        centre) under donor excitation.
    diffusion : float
        Translational diffusion coefficient (µm²/ms).
    background : float
        Background rate per detection channel (photons per ms).
    n_photons : int
        Photon budget; the simulation stops when it is reached.
    laser_period : float
        TCSPC pulse period (ns).
    alex_period : float
        Full alternation cycle of the two lasers (ms).
    dt : float
        Simulation time step (ms). ``alex_period`` should be an integer multiple.
    microtime_resolution : float
        Width of a micro-time channel (ns).
    n_microtime_channels : int
        Number of micro-time channels.
    box, w0, z0 : float
        Simulation box half-size (µm) and focus waist/height (µm).
    seed : int
        Random seed (diffusion and emission are seeded from it).
    rate_matrix : array_like, optional
        ``(n, n)`` exchange rates between the FRET populations, ``K[target,
        source]`` in Hz — chisurf's convention throughout. ``None`` (the default)
        leaves the populations static. Singly labelled species never exchange, so
        the matrix covers ``efficiencies`` only.
    alex : bool
        Two alternating lasers (the default). ``False`` gives the single-laser,
        polarization-resolved measurement 2D-MFD reads.
    polarized : bool
        Split each colour into parallel and perpendicular detectors, on the
        routing channels of :data:`MFD_STREAMS`. Requires ``alex=False``.
    irf_centre, irf_width : float
        Gaussian instrument response, ns. ``irf_width = 0`` (the default) leaves
        the decay unconvolved, so a mean micro time is a pure ⟨τ⟩_F.
    rho : float
        Rotational correlation time (ns) of the post-hoc polarization split.
    r0_fundamental : float
        Fundamental anisotropy of that split.
    g_factor, l1, l2 : float
        Detection anisotropy of that split: ``G`` *divides* the perpendicular
        channel (Schaffer/Eggeling), ``l1``/``l2`` enter the amplitudes.
    """

    efficiencies: tuple[float, ...] = (0.30, 0.75)
    populations: tuple[float, ...] | None = None
    donor_only: float = 0.05
    acceptor_only: float = 0.05
    concentration: float = 0.20

    gamma: float = 0.65
    alpha: float = 0.08
    beta: float = 1.40
    delta: float = 0.06

    tau_d0: float = 4.0
    tau_a: float = 2.5
    linker_sigma: float = 6.0
    r0: float = 52.0

    brightness: float = 150.0
    diffusion: float = 0.05
    background: float = 0.0

    n_photons: int = 400_000
    laser_period: float = 32.0
    alex_period: float = 0.4
    dt: float = 0.01
    microtime_resolution: float = 0.008
    n_microtime_channels: int = 4096
    box: float = 2.0
    w0: float = 0.3
    z0: float = 2.0
    seed: int = 1

    rate_matrix: tuple[tuple[float, ...], ...] | None = None
    alex: bool = True
    polarized: bool = False
    irf_centre: float = 0.0
    irf_width: float = 0.0
    rho: float = 1.0
    r0_fundamental: float = 0.38
    g_factor: float = 1.0
    l1: float = 0.0
    l2: float = 0.0

    def __post_init__(self):
        """Validate the mode and normalise the rate matrix to nested tuples.

        Nested tuples rather than an array so the frozen dataclass stays hashable
        and :func:`dataclasses.replace` keeps working.
        """
        if self.polarized and self.alex:
            raise ValueError("polarized mode is the single-laser MFD measurement; set alex=False")
        if self.rate_matrix is None:
            return
        matrix = np.asarray(self.rate_matrix, dtype=float)
        n = len(self.efficiencies)
        if matrix.shape != (n, n):
            raise ValueError(
                f"rate_matrix is {matrix.shape} but there are {n} FRET populations; "
                "the singly labelled species do not exchange and are not included"
            )
        object.__setattr__(
            self, "rate_matrix", tuple(tuple(float(v) for v in row) for row in matrix)
        )

    # ── derived quantities ──
    def stream_brightness(self) -> list[dict]:
        """Per-species brightness in each of the four ALEX streams.

        The heart of the simulation: the correction factors are *defined* by
        these numbers, so an analysis that recovers them has recovered the
        factors.

        Returns
        -------
        list of dict
            One entry per species with ``name``, ``i_dd``, ``i_da``, ``i_aa``
            (photons/ms/molecule) and ``efficiency`` (``None`` for the singly
            labelled species).
        """
        b = float(self.brightness)
        i_aa = self.beta * self.gamma * b
        out = []
        for efficiency in self.efficiencies:
            e = float(efficiency)
            i_dd = (1.0 - e) * b
            out.append(
                {
                    "name": f"FRET E={e:g}",
                    "efficiency": e,
                    "i_dd": i_dd,
                    "i_da": self.gamma * e * b + self.alpha * i_dd + self.delta * i_aa,
                    "i_aa": i_aa,
                }
            )
        if self.donor_only > 0:
            out.append(
                {
                    "name": "donor-only",
                    "efficiency": None,
                    "i_dd": b,
                    "i_da": self.alpha * b,
                    "i_aa": 0.0,
                }
            )
        if self.acceptor_only > 0:
            out.append(
                {
                    "name": "acceptor-only",
                    "efficiency": None,
                    "i_dd": 0.0,
                    "i_da": self.delta * i_aa,
                    "i_aa": i_aa,
                }
            )
        return out

    def base_population_sizes(self) -> list[float]:
        """Mean number of molecules in the box, one per *labelling* species."""
        n = len(self.efficiencies)
        if self.populations is not None:
            sizes = [float(p) for p in self.populations]
        else:
            sizes = [float(self.concentration) / max(n, 1)] * n
        if self.donor_only > 0:
            sizes.append(float(self.donor_only))
        if self.acceptor_only > 0:
            sizes.append(float(self.acceptor_only))
        return sizes

    def population_sizes(self) -> list[float]:
        """Mean number of molecules in the box, one per *simulated* species.

        In polarized mode every labelling species is split into a parallel and a
        perpendicular emission mode, so the list is twice as long. The split is
        even; the branching that matters is the stationary distribution of
        :meth:`photoselection_matrix`, not the starting one.
        """
        sizes = self.base_population_sizes()
        if not self.polarized:
            return sizes
        return [half for size in sizes for half in (size / 2.0, size / 2.0)]

    def photoselection_matrix(self) -> list[float]:
        """Return ``k_rad``: excitation-scaled routing between emission modes.

        Zero unless polarized. A photon's polarization is chosen afresh for each
        emission, so the two modes of a labelling species must interconvert much
        faster than that species emits. Putting those rates in ``k_rad`` rather
        than ``k_nrad`` is what makes that affordable and correct: they scale with
        the local excitation intensity, so the number of mode switches *per
        emitted photon* is the same everywhere in the focus and nothing is
        simulated while the molecule is away from it.

        The stationary occupancy of the parallel mode is set to the polarized
        decay's own share, ``∫VV / (∫VV + ∫VH)``, because a mode emits in
        proportion to the time spent in it.

        Returns
        -------
        list of float
            ``n_species²`` row-major source → target rates.
        """
        n_species = len(self.population_sizes())
        matrix = np.zeros((n_species, n_species))
        if not self.polarized:
            return [0.0] * (n_species * n_species)

        for index, (entry, (amplitudes, lifetimes)) in enumerate(
            zip(self.stream_brightness(), self.donor_decays())
        ):
            vv, vh = self.polarized_spectra(amplitudes, lifetimes)
            parallel = float(np.sum(vv[0] * vv[1]))
            perpendicular = float(np.sum(vh[0] * vh[1]))
            total = parallel + perpendicular
            share = 0.5 if total <= 0 else parallel / total

            # Fast against emission, so successive photons are independent; the
            # ratio, not the scale, sets the polarization.
            brightness = float(entry["i_dd"] + entry["i_da"] + entry["i_aa"])
            rate = _PHOTOSELECTION_SPEED * max(brightness, 1.0)
            par, perp = 2 * index, 2 * index + 1
            matrix[par, perp] = rate * (1.0 - share)
            matrix[perp, par] = rate * share
        return [float(v) for v in matrix.ravel()]

    def donor_decays(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Donor lifetime spectrum of every species (amplitudes, lifetimes in ns).

        A FRET population gets the multi-exponential decay of its
        Gaussian-broadened distance, so its mean micro-time is the ⟨τ⟩_F that the
        static FRET line predicts for its efficiency.
        """
        decays = []
        for efficiency in self.efficiencies:
            distance = float(
                distance_for_efficiency(
                    float(efficiency), donor=self.tau_d0, r0=self.r0, sigma=self.linker_sigma
                )
            )
            decays.append(
                fret_lifetime_spectrum(
                    distance, donor=self.tau_d0, r0=self.r0, sigma=self.linker_sigma
                )
            )
        if self.donor_only > 0:
            decays.append((np.array([1.0]), np.array([float(self.tau_d0)])))
        if self.acceptor_only > 0:
            decays.append((np.array([1.0]), np.array([float(self.tau_a)])))
        return decays

    def expected_lifetimes(self) -> list[float]:
        """Fluorescence-averaged lifetime ⟨τ⟩_F of each species' *donor* channel (ns).

        ``NaN`` for the acceptor-only species: it emits no donor photons, so the
        donor-channel lifetime a burst analysis measures is undefined for it (its
        own acceptor decay lives in a channel no lifetime here is taken from).
        """
        out = [float(lifetime_averages(a, t)[1]) for a, t in self.donor_decays()]
        if self.acceptor_only > 0:
            out[-1] = float("nan")
        return out

    def windows_per_laser(self) -> int:
        """Return how many simulation windows each laser is on — the alternation unit."""
        per_cycle = max(2, int(round(self.alex_period / self.dt)))
        return max(1, per_cycle // 2)

    def polarized_spectra(
        self, amplitudes: np.ndarray, lifetimes: np.ndarray
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        """Return the VV and VH lifetime spectra of a depolarizing donor decay.

        Polarization is expressed as a *state* rather than as a split applied to
        photons afterwards, because the joint distribution over (channel, micro
        time) factorizes exactly::

            P(parallel) ∝ ∫VV(t)dt        P(t | parallel) ∝ VV(t)

        and both polarized decays are ordinary multi-exponentials, since
        ``exp(−t/τ)·exp(−t/ρ)`` is another exponential::

            VV(t) = vm(t)·[1 + (2 − 3·l1)·r(t)]
            VH(t) = vm(t)·[1 − (1 − 3·l2)·r(t)] / G          r(t) = r0·exp(−t/ρ)

        So a component ``(a, τ)`` contributes ``a`` at ``τ`` plus a depolarizing
        term at the mixed time ``1/(1/τ + 1/ρ)``, with opposite signs in the two
        channels. The Schaffer/Eggeling convention is used throughout: ``G``
        *divides* the perpendicular channel and ``l1``/``l2`` enter the
        amplitudes, matching
        :func:`~chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh`.

        Parameters
        ----------
        amplitudes, lifetimes : numpy.ndarray
            The unpolarized (magic-angle) donor decay.

        Returns
        -------
        (vv_amplitudes, vv_lifetimes), (vh_amplitudes, vh_lifetimes)
        """
        a = np.asarray(amplitudes, dtype=float)
        t = np.asarray(lifetimes, dtype=float)
        rho = max(float(self.rho), 1e-12)
        mixed = 1.0 / (1.0 / t + 1.0 / rho)
        r0 = float(self.r0_fundamental)

        vv = (np.concatenate([a, a * (2.0 - 3.0 * self.l1) * r0]), np.concatenate([t, mixed]))
        vh = (
            np.concatenate([a, -a * (1.0 - 3.0 * self.l2) * r0]) / max(float(self.g_factor), 1e-12),
            np.concatenate([t, mixed]),
        )
        return vv, vh

    def irf_pattern(self) -> list[float] | None:
        """Return the Gaussian instrument response over micro-time bins, or ``None``.

        ``None`` when ``irf_width`` is zero, which leaves the decay unconvolved so
        a mean micro time is a pure ⟨τ⟩_F — the assumption the accurate-FRET tests
        rely on.
        """
        if self.irf_width <= 0.0:
            return None
        t = np.arange(self.n_microtime_channels) * float(self.microtime_resolution)
        z = (t - float(self.irf_centre)) / float(self.irf_width)
        return [float(v) for v in np.exp(-0.5 * z * z)]

    def exchange_matrix_ms(self) -> list[float] | None:
        """Return ``k_nrad`` for the full species list, or ``None`` when static.

        Two conversions, either of which silently produces a plausible wrong
        answer if skipped:

        * the engine's rate matrices are **row-major source → target**, the
          transpose of chisurf's ``K[target, source]``;
        * its rates are **per macro-time unit**, and this simulation runs on the
          millisecond convention (``D`` in µm²/ms, brightness per ms), so Hz
          becomes ms⁻¹.

        The matrix covers the FRET populations; the singly labelled species pad it
        with zeros, so a donor-only molecule never turns into a FRET one.
        """
        if self.rate_matrix is None:
            return None
        matrix = np.asarray(self.rate_matrix, dtype=float).copy()
        np.fill_diagonal(matrix, 0.0)
        n_total = len(self.population_sizes())
        full = np.zeros((n_total, n_total))
        n = matrix.shape[0]
        if not self.polarized:
            full[:n, :n] = matrix * 1e-3  # Hz -> 1/ms
        else:
            # Polarization doubled the species list, so a conformational rate
            # connects each emission mode to the *same* mode of the target state:
            # changing conformation does not reorient the dipole.
            for source in range(n):
                for target in range(n):
                    for mode in range(2):
                        full[2 * target + mode, 2 * source + mode] = matrix[target, source] * 1e-3
        return [float(v) for v in full.T.ravel()]  # K[target, source] -> source -> target

    def active_margin(self) -> float:
        """Return the open-volume margin (µm), sized for the *slowest* exchange rate.

        The engine may skip molecules far from the focus; the schema requires the
        margin to exceed ``sqrt(2 D / k)`` so a molecule arrives with its state
        distribution equilibrated rather than frozen. A fixed margin is wrong in
        exactly the regime this is used to study — slow exchange needs the
        *largest* margin — so it is derived, and disabled outright when the
        requirement exceeds the box.
        """
        if self.rate_matrix is None:
            return 1.0
        matrix = np.asarray(self.rate_matrix, dtype=float)
        np.fill_diagonal(matrix, 0.0)
        slowest = float(np.min(matrix.sum(axis=0)[matrix.sum(axis=0) > 0.0], initial=np.inf))
        if not np.isfinite(slowest) or slowest <= 0.0:
            return 0.0  # nothing exchanges: no requirement
        needed = float(np.sqrt(2.0 * float(self.diffusion) / (slowest * 1e-3)))
        return 0.0 if needed > float(self.box) else max(1.0, needed)

    def config(self) -> dict:
        """Build the tttrlib ``SimEngine`` configuration this parameter set describes."""
        irf = self.irf_pattern()

        def decay_of(amplitudes, lifetimes) -> dict:
            """Return one species' micro-time decay block."""
            block = {
                "amplitudes": [float(a) for a in amplitudes],
                "lifetimes": [float(t) for t in lifetimes],
                "n_bins": int(self.n_microtime_channels),
                "dt": float(self.microtime_resolution),
            }
            if irf is not None:
                block["irf"] = irf
            return block

        species = []
        for entry, (amplitudes, lifetimes) in zip(self.stream_brightness(), self.donor_decays()):
            if self.polarized:
                # Polarization is a *state*, not a parameter: each emission mode
                # carries its own polarized spectrum and emits only into its own
                # detectors, which reproduces the (channel, micro time) joint
                # exactly. The legacy r0/D_rot path cannot be used here because it
                # routes parallel/perpendicular into channels 0/1 *instead of* by
                # colour. See okf/references/simengine-species-encoding.md.
                vv, vh = self.polarized_spectra(amplitudes, lifetimes)
                species.append(
                    {
                        "D": float(self.diffusion),
                        "q": [entry["i_dd"], 0.0, entry["i_da"], 0.0],
                        "decay": decay_of(*vv),
                    }
                )
                species.append(
                    {
                        "D": float(self.diffusion),
                        "q": [0.0, entry["i_dd"], 0.0, entry["i_da"]],
                        "decay": decay_of(*vh),
                    }
                )
                continue
            # q is the single-laser brightness; q_alex adds one row per excitation
            # grid and must match their number exactly, so it is only for ALEX.
            entry_species = {
                "D": float(self.diffusion),
                "q": [entry["i_dd"], entry["i_da"]],
                "decay": decay_of(amplitudes, lifetimes),
            }
            if self.alex:
                entry_species["q_alex"] = [[entry["i_dd"], entry["i_da"]], [0.0, entry["i_aa"]]]
            species.append(entry_species)
        n_species = len(species)
        focus = {
            "type": "gaussian3d",
            "w0": float(self.w0),
            "z0": float(self.z0),
            "extent_xy": float(self.box),
            "extent_z": 2.0 * float(self.box),
            "spacing": 0.1,
            "amplitude": 1.0,
        }
        n_channels = 4 if self.polarized else 2
        settings = {
            "dt": float(self.dt),
            "n_ph_max": int(self.n_photons),
            "n_channels": n_channels,
            "laser_period": float(self.laser_period),
            "n_microtime_channels": int(self.n_microtime_channels),
            "microtime_resolution": float(self.microtime_resolution),
            "seed_diffusion": int(self.seed),
            "seed_emission": int(self.seed) + 1,
            "fast_grid_bbox": True,
            "active_margin": self.active_margin(),
        }
        if self.alex:
            settings["alex_period"] = float(self.alex_period)
        exchange = self.exchange_matrix_ms()
        config = {
            "settings": settings,
            "box": {"xy": float(self.box), "z": 2.0 * float(self.box)},
            "species": species,
            "k_rad": self.photoselection_matrix(),
            "k_nrad": exchange if exchange is not None else [0.0] * (n_species * n_species),
            "background": [float(self.background)] * n_channels,
            "population": self.population_sizes(),
            "excitation": [focus, focus] if self.alex else [focus],
        }
        if self.background > 0.0:
            # Dark counts are flat in micro time; the model assumes exactly this, so
            # leaving it to default would test the pipeline against its own assumption.
            config["background_decay"] = {
                "pattern": [1.0] * int(self.n_microtime_channels),
                "dt": float(self.microtime_resolution),
            }
        return config


@dataclass
class SimulatedSmfret:
    """A simulated ALEX measurement: the photons, and what they were made from.

    Attributes
    ----------
    tttr : tttrlib.TTTR
        The photon stream, routing channel = ALEX stream (see the module
        docstring).
    parameters : SmfretParameters
        The declared ground truth.
    stream : numpy.ndarray
        Per-photon stream index (same as the routing channel).
    species : numpy.ndarray
        Per-photon index of the emitting species (``-1`` for background) — the
        ground truth a classifier is judged against.
    molecule : numpy.ndarray
        Per-photon index of the emitting molecule, the ground truth a *burst*
        search is judged against: photons of one transit share an index, so a
        burst can be defined by truth instead of found by threshold.
    """

    tttr: object
    parameters: SmfretParameters
    stream: np.ndarray
    species: np.ndarray
    molecule: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    meta: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Measurement duration in seconds."""
        macro = np.asarray(self.tttr.macro_times, dtype=float)
        resolution = float(self.tttr.header.macro_time_resolution)
        return float((macro[-1] - macro[0]) * resolution) if macro.size else 0.0

    def photon_counts(self) -> dict:
        """Total photons per stream, keyed ``i_dd``/``i_da``/``i_ad``/``i_aa``."""
        return {
            name: int(np.count_nonzero(self.stream == index)) for name, index in STREAMS.items()
        }

    def burst_table(
        self,
        *,
        algorithm: str = "sliding_window",
        parameters: dict | None = None,
        min_photons: int = 40,
    ) -> dict:
        """Search bursts and reduce each to the quantities a calibration needs.

        Parameters
        ----------
        algorithm : str, optional
            Burst search from tttrlib's registry (``"sliding_window"``,
            ``"maxtree"``, …).
        parameters : dict, optional
            Overrides for that search; the registry defaults are used otherwise.
        min_photons : int, optional
            Bursts with fewer photons are dropped.

        Returns
        -------
        dict
            Arrays over bursts: ``i_dd``/``i_da``/``i_aa``/``i_ad`` counts,
            ``tau_f`` (mean micro-time of the donor photons, ns; ``NaN`` when the
            burst has none), ``n_photons``, ``duration`` (ms), ``start``/``stop``
            photon indices, and ``species`` (the majority ground-truth species of
            the burst, ``-1`` when it is mostly background).
        """
        from chisurf.core.fluorescence.burst import tttrlib_search

        search_parameters = {"L": 20, "m": 10, "T": 0.0005}
        search_parameters.update(parameters or {})
        bounds = np.atleast_2d(tttrlib_search.search(self.tttr, algorithm, search_parameters))
        macro = np.asarray(self.tttr.macro_times, dtype=float)
        micro = np.asarray(self.tttr.micro_times, dtype=float)
        macro_resolution = float(self.tttr.header.macro_time_resolution) * 1e3  # ms
        micro_resolution = float(self.parameters.microtime_resolution)  # ns

        rows: dict[str, list] = {
            k: []
            for k in (
                "i_dd",
                "i_da",
                "i_ad",
                "i_aa",
                "tau_f",
                "n_photons",
                "duration",
                "start",
                "stop",
                "species",
            )
        }
        for start, stop in bounds:
            start, stop = int(start), int(stop)
            if stop < start:
                continue
            sl = slice(start, stop + 1)
            streams = self.stream[sl]
            n = streams.size
            if n < int(min_photons):
                continue
            donor = streams == STREAMS["i_dd"]
            rows["i_dd"].append(int(np.count_nonzero(donor)))
            rows["i_da"].append(int(np.count_nonzero(streams == STREAMS["i_da"])))
            rows["i_ad"].append(int(np.count_nonzero(streams == STREAMS["i_ad"])))
            rows["i_aa"].append(int(np.count_nonzero(streams == STREAMS["i_aa"])))
            # The mean arrival time of an IRF-free decay is its fluorescence-averaged
            # lifetime, which is exactly the FRET line's x-axis.
            rows["tau_f"].append(
                float(np.mean(micro[sl][donor]) * micro_resolution)
                if np.any(donor)
                else float("nan")
            )
            rows["n_photons"].append(n)
            rows["duration"].append(float((macro[stop] - macro[start]) * macro_resolution))
            rows["start"].append(start)
            rows["stop"].append(stop)
            labels = self.species[sl]
            labels = labels[labels >= 0]
            rows["species"].append(int(np.bincount(labels).argmax()) if labels.size else -1)
        return {k: np.asarray(v) for k, v in rows.items()}

    def with_parameters(self, **changes) -> SmfretParameters:
        """Return the parameter set with ``changes`` applied (for a rerun)."""
        return replace(self.parameters, **changes)

    # ── burst definition ──
    def true_bursts(self, *, min_photons: int = 20, gap_ms: float = 0.5) -> np.ndarray:
        """Return ``(first, last)`` photon indices of each single-molecule transit.

        The burst search a measurement cannot have: photons are grouped by the
        molecule that emitted them, so a burst is a *transit* by definition rather
        than a threshold crossing. Comparing a fit on these against the same fit on
        searched bursts separates what the model gets wrong from what the search
        does — with a real measurement the two are inseparable.

        A molecule crosses the focus many times over a measurement, so its photons
        are split wherever they pause for longer than *gap_ms*. Transits that
        overlap another kept transit are dropped (rare at the default
        concentration): the burst tables are merged column-wise by position, so
        overlapping rows would double-count photons.

        Parameters
        ----------
        min_photons : int
            Discard transits with fewer photons.
        gap_ms : float
            Silence that ends a transit, in milliseconds.

        Returns
        -------
        numpy.ndarray
            ``(n_bursts, 2)`` inclusive photon-index bounds, ordered by start.
        """
        if self.molecule.size == 0:
            raise RuntimeError(
                "no per-photon molecule index; the installed tttrlib did not report "
                "emitting_molecule()"
            )
        macro = np.asarray(self.tttr.macro_times, dtype=float)
        macro = macro * float(self.tttr.header.macro_time_resolution) * 1e3  # ms
        signal = np.flatnonzero(np.asarray(self.species) >= 0)

        spans = []
        molecule = np.asarray(self.molecule)[signal]
        order = np.argsort(molecule, kind="stable")
        grouped, indices = molecule[order], signal[order]
        for part in np.split(indices, np.flatnonzero(np.diff(grouped)) + 1):
            if part.size < min_photons:
                continue
            breaks = np.flatnonzero(np.diff(macro[part]) > float(gap_ms)) + 1
            for transit in np.split(part, breaks):
                if transit.size >= min_photons:
                    spans.append((int(transit[0]), int(transit[-1])))

        spans.sort()
        kept, last_stop = [], -1
        for start, stop in spans:
            if start > last_stop:
                kept.append((start, stop))
                last_stop = stop
        return np.asarray(kept, dtype=np.int64).reshape(-1, 2)

    def searched_bursts(
        self,
        *,
        algorithm: str = "sliding_window",
        parameters: dict | None = None,
        min_photons: int = 20,
    ) -> np.ndarray:
        """Return ``(first, last)`` photon indices from a real burst search.

        The route a measurement actually takes, for comparison against
        :meth:`true_bursts`.

        Parameters
        ----------
        algorithm : str
            Burst search from tttrlib's registry.
        parameters : dict, optional
            Overrides for that search; registry defaults otherwise.
        min_photons : int
            Discard bursts with fewer photons.

        Returns
        -------
        numpy.ndarray
            ``(n_bursts, 2)`` inclusive photon-index bounds.
        """
        from chisurf.core.fluorescence.burst.tttrlib_search import search

        found = np.asarray(search(self.tttr, algorithm, parameters), dtype=np.int64)
        found = found.reshape(-1, 2)
        keep = (found[:, 1] - found[:, 0] + 1) >= int(min_photons)
        return found[keep]

    # ── export ──
    def detectors(self) -> dict:
        """Return the detector definitions matching the routing channels emitted.

        In polarized mode a colour detector must cover *both* polarizations, or
        half its photons vanish from the FRET axis with nothing complaining — the
        per-detector counts would simply be half as large and the proximity ratio
        would still look reasonable. The single-polarization detectors are written
        alongside, so one folder serves both MFD axes.
        """
        if not self.parameters.polarized:
            return {
                "green": {"chs": [STREAMS["i_dd"]], "micro_time_ranges": []},
                "red": {"chs": [STREAMS["i_da"]], "micro_time_ranges": []},
            }
        return {
            "green": {
                "chs": [MFD_STREAMS["g_par"], MFD_STREAMS["g_perp"]],
                "micro_time_ranges": [],
            },
            "red": {"chs": [MFD_STREAMS["r_par"], MFD_STREAMS["r_perp"]], "micro_time_ranges": []},
            "green_par": {"chs": [MFD_STREAMS["g_par"]], "micro_time_ranges": []},
            "green_perp": {"chs": [MFD_STREAMS["g_perp"]], "micro_time_ranges": []},
        }

    def true_responses(self) -> dict:
        """Return the instrument responses and background rates as *declared*.

        Estimating the response from a measurement's own non-burst photons is what
        a real folder has to do, and it is contaminated: molecules too dim to cross
        the burst threshold are not detected, so their fluorescence lands in the
        "non-burst" stream. That is a property of the *experiment* rather than of
        this simulator — the same contamination is on real data — so being able to
        hand a fit the declared response isolates whatever is under test from it,
        and comparing the two *measures* the contamination instead of arguing
        about it.

        Returns
        -------
        dict
            Detector name to
            :class:`~chisurf.core.fluorescence.mfd.patterns.ChannelResponse`, for
            every detector :meth:`detectors` defines.
        """
        from chisurf.core.fluorescence.mfd.patterns import ChannelResponse

        params = self.parameters
        dt = float(params.microtime_resolution)
        pattern = params.irf_pattern()
        if pattern is None:
            # No instrument response was simulated, so the decay is unconvolved
            # and the response is a delta at zero — not at ``irf_centre``, which
            # only means something when there is a pulse to place.
            irf = np.zeros(int(params.n_microtime_channels))
            irf[0] = 1.0
        else:
            irf = np.asarray(pattern, dtype=float)

        # ``background`` is photons per millisecond per *routing channel*, and a
        # response wants counts per second in a *detector* — which covers one or
        # more routing channels. Checked against a molecule-free run rather than
        # derived: the engine's own key is documented per macro-time unit, and it
        # is not.
        per_channel = float(params.background) * 1e3
        return {
            name: ChannelResponse(
                irf=irf.copy(),
                dt=dt,
                background_rate=per_channel * len(definition["chs"]),
            )
            for name, definition in self.detectors().items()
        }

    def write_folder(
        self,
        directory: pathlib.Path | str,
        *,
        stem: str = "sim",
        bursts: str | np.ndarray = "truth",
        **burst_kwargs,
    ) -> pathlib.Path:
        """Write a real burst-analysis folder, readable by the ordinary path.

        Produces the photon file, the ``bi4_bur`` tables and the analysis manifest,
        so a simulated measurement goes through the *same* reader, channel
        verification and response estimation as a measured one.

        Parameters
        ----------
        directory : path-like
            Where to create the folder.
        stem : str
            Base name of the measurement file.
        bursts : {"truth", "search"} or numpy.ndarray
            Which burst definition to write, or explicit ``(first, last)`` pairs.
        **burst_kwargs
            Passed to :meth:`true_bursts` or :meth:`searched_bursts`.

        Returns
        -------
        pathlib.Path
            The analysis folder to hand to the reader.
        """
        from chisurf.core.fluorescence.simulation import write_burst_folder

        if isinstance(bursts, str):
            if bursts == "truth":
                start_stop = self.true_bursts(**burst_kwargs)
            elif bursts == "search":
                start_stop = self.searched_bursts(**burst_kwargs)
            else:
                raise ValueError(f"unknown burst definition {bursts!r}")
        else:
            start_stop = np.asarray(bursts, dtype=np.int64).reshape(-1, 2)
        if start_stop.size == 0:
            raise RuntimeError(f"the {bursts!r} burst definition found no bursts")

        return write_burst_folder(
            self.tttr,
            start_stop,
            self.detectors(),
            directory,
            stem=stem,
            windows={"prompt": (0, int(self.parameters.n_microtime_channels))},
            settings={"burst_definition": bursts if isinstance(bursts, str) else "explicit"},
        )


def simulate_smfret(parameters: SmfretParameters | None = None, **overrides) -> SimulatedSmfret:
    """Simulate an ALEX smFRET measurement with declared parameters.

    Parameters
    ----------
    parameters : SmfretParameters, optional
        The declared ground truth; defaults are used otherwise.
    **overrides
        Individual parameter overrides applied on top.

    Returns
    -------
    SimulatedSmfret
        The photon stream (routing channel = ALEX stream) and the truth.

    Raises
    ------
    RuntimeError
        If the installed tttrlib has no simulator, or if its photon order stops
        matching the engine's own arrays (the assumption that lets the laser be
        recovered per photon).

    Examples
    --------
    >>> sim = simulate_smfret(n_photons=20_000)               # doctest: +SKIP
    >>> bursts = sim.burst_table()                            # doctest: +SKIP
    >>> sorted(bursts)[:3]                                    # doctest: +SKIP
    ['duration', 'i_aa', 'i_ad']
    """
    import tttrlib

    if not hasattr(tttrlib, "SimEngine"):
        raise RuntimeError("the installed tttrlib has no SimEngine simulator")

    params = parameters or SmfretParameters()
    if overrides:
        params = replace(params, **overrides)

    engine = tttrlib.SimEngine.from_dict(params.config())
    if params.rate_matrix is not None and hasattr(engine, "set_state_log"):
        engine.set_state_log(True)
    engine.run()

    channel = np.asarray(engine.channel(), dtype=int)
    micro = np.asarray(engine.micro_time(), dtype=int)
    window = np.asarray(engine.macro_window(), dtype=np.int64)
    species = np.asarray(engine.emitting_species(), dtype=int)

    if params.alex:
        # Which laser was on: the engine alternates in whole windows with exact
        # integer arithmetic, so the same integer rule recovers it per photon.
        laser = (window // params.windows_per_laser()) % 2
        stream = (laser * 2 + channel).astype(np.int8)
    elif params.polarized:
        # The engine already routed each photon by colour *and* polarization,
        # because each emission mode is its own species emitting into its own
        # detectors; only the channel numbering has to become the pipeline's.
        stream = _ENGINE_TO_MFD[np.clip(channel, 0, 3)]
    else:
        stream = channel.astype(np.int8)

    tttr = engine.to_tttr(dt=params.dt, n_channels=2, laser_period=params.laser_period)
    if not (
        np.array_equal(np.asarray(tttr.routing_channels, dtype=int), channel)
        and np.array_equal(np.asarray(tttr.micro_times, dtype=int), micro)
    ):
        raise RuntimeError(
            "tttrlib reordered the photons on export; the per-photon laser can no "
            "longer be matched to the exported stream"
        )

    # Re-emit with the stream (laser × detector) as the routing channel, so the
    # exported photons are self-describing — an ALEX analysis reads its windows
    # from the routing channel like any other measurement.
    out = tttrlib.TTTR()
    out.append_events(
        np.asarray(tttr.macro_times, dtype=np.uint64),
        np.asarray(tttr.micro_times, dtype=np.uint16),
        stream,
        np.zeros(stream.size, dtype=np.int8),
        shift_macro_time=False,
    )
    header = out.header
    header.set_macro_time_resolution(float(tttr.header.macro_time_resolution))
    header.set_micro_time_resolution(float(params.microtime_resolution) * 1e-9)
    header.set_number_of_micro_time_channels(int(params.n_microtime_channels))
    out.set_header(header)

    # Background photons carry no species; the engine marks them beyond the
    # species range.
    n_species = len(params.population_sizes())
    species = np.where(species < n_species, species, -1)
    if params.polarized:
        # Report the *labelling* species, not the emission mode: the two modes of
        # one population are the same molecule, and every consumer of this array
        # asks which population a photon came from.
        species = np.where(species < 0, -1, species // 2)
    streams = dict(MFD_STREAMS) if params.polarized else dict(STREAMS)
    return SimulatedSmfret(
        tttr=out,
        parameters=params,
        stream=stream,
        species=species,
        molecule=np.asarray(engine.emitting_molecule(), dtype=np.int64),
        meta={
            "n_photons": int(stream.size),
            "expected_lifetimes": params.expected_lifetimes(),
            "streams": streams,
            "rate_matrix": params.rate_matrix,
            "active_margin": params.active_margin(),
        },
    )
