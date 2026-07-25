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
decay per species, so acceptor photons of a FRET species inherit the donor decay.
No analysis here reads them, but do not use those micro-times.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from chisurf.core.fluorescence.fret.lines import (
    distance_for_efficiency,
    fret_lifetime_spectrum,
    lifetime_averages,
)

__all__ = ["SmfretParameters", "SimulatedSmfret", "simulate_smfret"]

#: Routing channel per (laser, detector) pair — the four ALEX photon streams.
STREAMS = {"i_dd": 0, "i_da": 1, "i_ad": 2, "i_aa": 3}


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
            out.append({
                "name": f"FRET E={e:g}",
                "efficiency": e,
                "i_dd": i_dd,
                "i_da": self.gamma * e * b + self.alpha * i_dd + self.delta * i_aa,
                "i_aa": i_aa,
            })
        if self.donor_only > 0:
            out.append({"name": "donor-only", "efficiency": None,
                        "i_dd": b, "i_da": self.alpha * b, "i_aa": 0.0})
        if self.acceptor_only > 0:
            out.append({"name": "acceptor-only", "efficiency": None,
                        "i_dd": 0.0, "i_da": self.delta * i_aa, "i_aa": i_aa})
        return out

    def population_sizes(self) -> list[float]:
        """Mean number of molecules in the box, one per species."""
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

    def donor_decays(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Donor lifetime spectrum of every species (amplitudes, lifetimes in ns).

        A FRET population gets the multi-exponential decay of its
        Gaussian-broadened distance, so its mean micro-time is the ⟨τ⟩_F that the
        static FRET line predicts for its efficiency.
        """
        decays = []
        for efficiency in self.efficiencies:
            distance = float(distance_for_efficiency(
                float(efficiency), donor=self.tau_d0, r0=self.r0, sigma=self.linker_sigma
            ))
            decays.append(fret_lifetime_spectrum(
                distance, donor=self.tau_d0, r0=self.r0, sigma=self.linker_sigma
            ))
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

    def config(self) -> dict:
        """Build the tttrlib ``SimEngine`` configuration this parameter set describes."""
        species = []
        for entry, (amplitudes, lifetimes) in zip(self.stream_brightness(), self.donor_decays()):
            species.append({
                "D": float(self.diffusion),
                # scalar q is the fallback for a single-laser build; q_alex is what
                # a two-laser (ALEX) run uses: one brightness row per laser.
                "q": [entry["i_dd"], entry["i_da"]],
                "q_alex": [[entry["i_dd"], entry["i_da"]], [0.0, entry["i_aa"]]],
                "decay": {
                    "amplitudes": [float(a) for a in amplitudes],
                    "lifetimes": [float(t) for t in lifetimes],
                    "n_bins": int(self.n_microtime_channels),
                    "dt": float(self.microtime_resolution),
                },
            })
        n_species = len(species)
        focus = {"type": "gaussian3d", "w0": float(self.w0), "z0": float(self.z0),
                 "extent_xy": float(self.box), "extent_z": 2.0 * float(self.box),
                 "spacing": 0.1, "amplitude": 1.0}
        return {
            "settings": {
                "dt": float(self.dt),
                "n_ph_max": int(self.n_photons),
                "n_channels": 2,
                "laser_period": float(self.laser_period),
                "n_microtime_channels": int(self.n_microtime_channels),
                "microtime_resolution": float(self.microtime_resolution),
                "alex_period": float(self.alex_period),
                "seed_diffusion": int(self.seed),
                "seed_emission": int(self.seed) + 1,
                "fast_grid_bbox": True,
                "active_margin": 1.0,
            },
            "box": {"xy": float(self.box), "z": 2.0 * float(self.box)},
            "species": species,
            # no photophysical exchange between species: the populations are static
            "k_rad": [0.0] * (n_species * n_species),
            "k_nrad": [0.0] * (n_species * n_species),
            "background": [float(self.background), float(self.background)],
            "population": self.population_sizes(),
            "excitation": [focus, focus],
        }


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
    """

    tttr: object
    parameters: SmfretParameters
    stream: np.ndarray
    species: np.ndarray
    meta: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Measurement duration in seconds."""
        macro = np.asarray(self.tttr.macro_times, dtype=float)
        resolution = float(self.tttr.header.macro_time_resolution)
        return float((macro[-1] - macro[0]) * resolution) if macro.size else 0.0

    def photon_counts(self) -> dict:
        """Total photons per stream, keyed ``i_dd``/``i_da``/``i_ad``/``i_aa``."""
        return {name: int(np.count_nonzero(self.stream == index))
                for name, index in STREAMS.items()}

    def burst_table(self, *, algorithm: str = "sliding_window",
                    parameters: dict | None = None, min_photons: int = 40) -> dict:
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
        bounds = np.atleast_2d(
            tttrlib_search.search(self.tttr, algorithm, search_parameters)
        )
        macro = np.asarray(self.tttr.macro_times, dtype=float)
        micro = np.asarray(self.tttr.micro_times, dtype=float)
        macro_resolution = float(self.tttr.header.macro_time_resolution) * 1e3  # ms
        micro_resolution = float(self.parameters.microtime_resolution)          # ns

        rows: dict[str, list] = {k: [] for k in
                                 ("i_dd", "i_da", "i_ad", "i_aa", "tau_f", "n_photons",
                                  "duration", "start", "stop", "species")}
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
                float(np.mean(micro[sl][donor]) * micro_resolution) if np.any(donor)
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


def simulate_smfret(parameters: SmfretParameters | None = None,
                    **overrides) -> SimulatedSmfret:
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
    engine.run()

    channel = np.asarray(engine.channel(), dtype=int)
    micro = np.asarray(engine.micro_time(), dtype=int)
    window = np.asarray(engine.macro_window(), dtype=np.int64)
    species = np.asarray(engine.emitting_species(), dtype=int)

    # Which laser was on: the engine alternates in whole windows with exact
    # integer arithmetic, so the same integer rule recovers it per photon.
    laser = (window // params.windows_per_laser()) % 2
    stream = (laser * 2 + channel).astype(np.int8)

    tttr = engine.to_tttr(dt=params.dt, n_channels=2, laser_period=params.laser_period)
    if not (np.array_equal(np.asarray(tttr.routing_channels, dtype=int), channel)
            and np.array_equal(np.asarray(tttr.micro_times, dtype=int), micro)):
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
    return SimulatedSmfret(
        tttr=out, parameters=params, stream=stream, species=species,
        meta={"n_photons": int(stream.size),
              "expected_lifetimes": params.expected_lifetimes(),
              "streams": dict(STREAMS)},
    )
