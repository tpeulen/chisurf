"""A guided, general burst workflow for non-programmers.

This module wraps burst selection, BVA, and H2MM together with the MMFDB
client into a small facade. The aim is that a bench scientist can run a
complete single-molecule FRET analysis without touching settings dataclasses,
object UUIDs, or TTTR bookkeeping::

    from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow

    wf = BurstWorkflow.demo()                  # or .connect("http://mmfdb.mylab.org")
    dataset = wf.register("m000.spc")          # store a measurement, get a handle
    bursts = wf.select_bursts(dataset)         # find single-molecule bursts
    bursts.bva().plot()                        # burst variance analysis
    print(bursts.h2mm().summary())             # photon-by-photon HMM states
    wf.close()

Generality is provided by a declarable :class:`Setup` — an ordered list of
named :class:`Detector` s, each a set of routing (detection) channels plus
optional micro-time windows. This mirrors the multiparameter-fluorescence
detector model used throughout ChiSurf (``{name: {chs, micro_time_ranges}}``)
and places no limit on the number of colours::

    setup = Setup.from_channels(green=(0, 8), red=(1, 9), yellow=(2, 10))

FRET is not baked into the setup: analyses that need a donor/acceptor pair take
the two detector names as arguments (defaulting to the first two), so the same
setup serves two-, three-, or n-colour experiments, single-pair or multi-pair.
Arbitrary channels, micro-time gating (PIE/ALEX), several TTTR file types,
multiple datasets, and different burst-search methods are all supported, yet
every parameter has a sensible default so the simple case stays a single line.
"""

from __future__ import annotations

import base64
import socket
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Sequence
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import numpy as np

from chisurf.core.datastore import (
    column_names,
    numeric_column,
    row_count,
    take_where,
)
import pandas as pd

# Full micro-time acceptance when a stream declares no window (SPC is 12-bit).
_FULL_MICROTIME = (0, 4095)

# Burst-search method name -> (BurstFilterMode value, filter_active).
_SEARCH_METHODS = {
    "burst": ("burst", True),          # Seidel sliding-window search (honours min_photons)
    "count_rate": ("count_rate", True),  # count-rate threshold
    "cusum": ("cusum", True),
    "bocpd": ("bocpd", True),
    "kalman": ("kalman", True),
}


class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Thread-per-request server so the demo never stalls a notebook."""

    daemon_threads = True


class _QuietRequestHandler(WSGIRequestHandler):
    """WSGI request handler that does not print an access log line."""

    def log_message(self, *args: object) -> None:
        """Suppress the per-request stderr access log."""
        return


def _free_port() -> int:
    """Return a currently-free TCP port on the loopback interface."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@dataclass(frozen=True)
class Detector:
    """One named detection channel: a group of routing channels.

    Attributes
    ----------
    name : str
        Spectral/physical name chosen by the user, e.g. ``"green"``, ``"red"``,
        ``"yellow"``. Purely a label — no FRET role is implied.
    routing_channels : tuple of int
        TCSPC routing (detection) channels assigned to this detector.
    microtime_ranges : tuple of (int, int)
        Optional inclusive micro-time windows (for PIE/ALEX gating). Empty
        means the whole micro-time axis.
    """

    name: str
    routing_channels: tuple[int, ...]
    microtime_ranges: tuple[tuple[int, int], ...] = ()

    def bva_ranges(self) -> tuple[tuple[int, int], ...]:
        """Return micro-time ranges to use for BVA (full axis if unset)."""
        return self.microtime_ranges or (_FULL_MICROTIME,)


@dataclass
class Setup:
    """A detector setup: the named detection channels of an experiment.

    Build one from keyword channels via :meth:`from_channels`, or construct
    :class:`Detector` objects directly for micro-time gating. Any number of
    detectors is allowed; FRET donor/acceptor roles are chosen per analysis,
    not stored here.

    Attributes
    ----------
    detectors : list of Detector
        Ordered detection channels.
    file_type : str, optional
        TTTR file type of the measurements (e.g. ``"SPC-130"``, ``"PTU"``).
        ``None`` lets the reader infer it from each file.
    """

    detectors: list[Detector]
    file_type: str | None = None

    def __post_init__(self) -> None:
        """Validate that at least two distinctly named detectors are present."""
        names = [d.name for d in self.detectors]
        if len(names) < 2:
            raise ValueError("a Setup needs at least two detectors")
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate detector names in {names}")

    @classmethod
    def from_channels(
        cls, *, file_type: str | None = None, **channels: Sequence[int]
    ) -> "Setup":
        """Build a setup from ``name=routing_channels`` keyword arguments.

        Example::

            Setup.from_channels(green=(0, 8), red=(1, 9), yellow=(2, 10))
        """
        detectors = [Detector(name, tuple(chs)) for name, chs in channels.items()]
        return cls(detectors=detectors, file_type=file_type)

    # -- helpers --------------------------------------------------------

    def names(self) -> list[str]:
        """Return the detector names in declaration order."""
        return [d.name for d in self.detectors]

    def detector(self, name: str) -> Detector:
        """Return the detector with the given name."""
        for candidate in self.detectors:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    def all_routing_channels(self) -> list[int]:
        """Return every routing channel referenced by any detector, sorted."""
        return sorted({ch for d in self.detectors for ch in d.routing_channels})

    def stream_defs(self) -> list[Any]:
        """Return H2MM :class:`StreamDef` objects for every detector."""
        from chisurf.core.fluorescence.burst.photons import StreamDef

        return [
            StreamDef(
                d.name, list(d.routing_channels), [tuple(r) for r in d.microtime_ranges]
            )
            for d in self.detectors
        ]

    def _pair(self, donor: str | None, acceptor: str | None) -> tuple[str, str]:
        """Resolve a FRET (donor, acceptor) name pair, defaulting to first two."""
        names = self.names()
        donor = donor if donor is not None else names[0]
        acceptor = acceptor if acceptor is not None else names[1]
        for role, value in (("donor", donor), ("acceptor", acceptor)):
            if value not in names:
                raise ValueError(f"{role} detector {value!r} not in {names}")
        return donor, acceptor


@dataclass
class Bva:
    """Result of a Burst Variance Analysis.

    Attributes
    ----------
    table : tttrlib.DataStore
        Per-burst table with ``Proximity Ratio Mean`` / ``Proximity Ratio Std``.
    photons_per_slice : int
        Photons per sub-burst slice used for the shot-noise static line.
    """

    table: Any
    photons_per_slice: int

    @property
    def mean_proximity_ratio(self) -> float:
        """Average proximity ratio (apparent FRET) across all bursts."""
        return float(np.nanmean(self.table["Proximity Ratio Mean"]))

    @property
    def dynamic_fraction(self) -> float:
        """Fraction of bursts above the shot-noise static line (dynamics)."""
        from chisurf.plugins.burst.burst_bva.core.computation import (
            compute_static_bva_line,
        )

        grid = np.linspace(0.001, 0.999, 200)
        _, static_std = compute_static_bva_line(grid, self.photons_per_slice)
        means = numeric_column(self.table, "Proximity Ratio Mean")
        stds = numeric_column(self.table, "Proximity Ratio Std")
        expected = np.interp(means, grid, static_std)
        valid = ~np.isnan(means) & ~np.isnan(stds)
        if not valid.any():
            return 0.0
        return float(np.mean(stds[valid] > expected[valid]))

    def plot(self, ax: Any = None) -> Any:
        """Draw the BVA scatter with the shot-noise static line."""
        import matplotlib.pyplot as plt

        from chisurf.plugins.burst.burst_bva.core.computation import (
            compute_static_bva_line,
        )

        if ax is None:
            _, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(
            self.table["Proximity Ratio Mean"],
            self.table["Proximity Ratio Std"],
            s=8, alpha=0.25, color="#1f77b4", label="bursts",
        )
        grid = np.linspace(0.01, 0.99, 100)
        static_mean, static_std = compute_static_bva_line(grid, self.photons_per_slice)
        ax.plot(static_mean, static_std, color="crimson", lw=2, label="shot-noise limit")
        ax.set_xlabel("Proximity ratio (apparent FRET)")
        ax.set_ylabel("Proximity ratio (std)")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 0.6)
        ax.set_title("Burst Variance Analysis")
        ax.legend()
        return ax


@dataclass
class TwoCde:
    """Result of a 2CDE (FRET-2CDE / ALEX-2CDE) burst-feature analysis.

    Attributes
    ----------
    table : tttrlib.DataStore
        Per-burst table with a ``FRET-2CDE`` or ``ALEX-2CDE`` column.
    variant : str
        ``"fret"`` or ``"alex"``.
    """

    table: Any
    variant: str = "fret"

    @property
    def column(self) -> str:
        """Name of the 2CDE feature column in :attr:`table`."""
        return "ALEX-2CDE" if self.variant == "alex" else "FRET-2CDE"

    @property
    def mean_2cde(self) -> float:
        """Mean 2CDE value across all bursts (finite entries only)."""
        return float(np.nanmean(numeric_column(self.table, self.column)))

    def dynamic_fraction(self, threshold: float = 12.0) -> float:
        """Fraction of bursts whose FRET-2CDE exceeds ``threshold``.

        FRET-2CDE is ~10 for static bursts and larger under ms dynamics, so a
        threshold slightly above 10 separates the dynamic sub-population.
        """
        vals = numeric_column(self.table, self.column)
        finite = vals[np.isfinite(vals)]
        if finite.size == 0:
            return 0.0
        return float(np.mean(finite > threshold))

    def plot(self, ax: Any = None) -> Any:
        """Draw the 2CDE histogram (and E-vs-2CDE scatter when E is available)."""
        import matplotlib.pyplot as plt

        vals = numeric_column(self.table, self.column)
        finite = np.isfinite(vals)
        e_col = next((c for c in ("Proximity Ratio Mean", "E", "Efficiency")
                      if c in self.table), None)
        if ax is None:
            _, ax = plt.subplots(figsize=(6, 5))
        if e_col is not None:
            e = numeric_column(self.table, e_col)
            m = finite & np.isfinite(e)
            ax.scatter(e[m], vals[m], s=8, alpha=0.25, color="#1f77b4")
            ax.set_xlabel("Proximity ratio (apparent FRET)")
            ax.set_ylabel(self.column)
            ax.set_xlim(0, 1)
        else:
            ax.hist(vals[finite], bins=40, color="#1f77b4", alpha=0.8)
            ax.set_xlabel(self.column)
            ax.set_ylabel("bursts")
        ax.set_title(self.column)
        return ax


@dataclass
class Recurrence:
    """Recurrence Analysis of Single Particles (RASP) on a burst set.

    Returned by :meth:`Bursts.recurrence`. Holds the per-burst arrival times and
    FRET efficiencies and exposes the same-molecule probability and recurrence
    FRET histograms (Hoffmann et al., PCCP 2011).

    Attributes
    ----------
    times_s : numpy.ndarray
        Per-burst arrival times in seconds.
    efficiency : numpy.ndarray
        Per-burst FRET efficiency / proximity ratio.
    """

    times_s: np.ndarray
    efficiency: np.ndarray

    def same_molecule_probability(
        self, tau_min_s: float = 1e-3, tau_max_s: float = 1.0, n_bins: int = 50,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(tau, P_same)`` — the same-molecule probability vs lag."""
        from chisurf.core.fluorescence.burst.recurrence import same_molecule_probability

        tau, p_same, _ = same_molecule_probability(
            self.times_s, tau_min_s, tau_max_s, n_bins)
        return tau, p_same

    def recurrence_time(self, threshold: float = 0.5, **kwargs) -> float:
        """Largest lag (s) at which ``P_same`` still exceeds ``threshold``.

        A practical upper bound for the recurrence-time window: beyond it a
        recurring burst is more likely a different molecule than the same one.
        """
        tau, p_same = self.same_molecule_probability(**kwargs)
        ok = tau[p_same >= threshold]
        return float(ok.max()) if ok.size else float("nan")

    def efficiencies(
        self, e_range: tuple[float, float], dt_range_s: tuple[float, float],
    ) -> np.ndarray:
        """Efficiencies of bursts recurring after the ``e_range`` sub-population."""
        from chisurf.core.fluorescence.burst.recurrence import recurrence_efficiencies

        return recurrence_efficiencies(self.times_s, self.efficiency, e_range, dt_range_s)

    def histogram(
        self, e_range: tuple[float, float], dt_range_s: tuple[float, float],
        bins: int = 50,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(centers, recurrence_hist, overall_hist)`` (unit area)."""
        from chisurf.core.fluorescence.burst.recurrence import recurrence_histogram

        return recurrence_histogram(
            self.times_s, self.efficiency, e_range, dt_range_s, bins)

    def plot(
        self, e_range: tuple[float, float] = (0.0, 0.4),
        dt_range_s: tuple[float, float] = (1e-3, 0.1), ax: Any = None,
    ) -> Any:
        """Overlay the recurrence FRET histogram on the overall histogram."""
        import matplotlib.pyplot as plt

        centers, rec, overall = self.histogram(e_range, dt_range_s)
        if ax is None:
            _, ax = plt.subplots(figsize=(6, 5))
        w = centers[1] - centers[0] if centers.size > 1 else 0.02
        ax.bar(centers, overall, width=w, color="0.8", label="all bursts")
        ax.bar(centers, rec, width=w, color="#1f77b4", alpha=0.7,
               label=f"recurrence E∈[{e_range[0]:g}, {e_range[1]:g}]")
        ax.axvspan(e_range[0], e_range[1], color="crimson", alpha=0.08)
        ax.set_xlabel("FRET efficiency (proximity ratio)")
        ax.set_ylabel("probability density")
        ax.set_title("Recurrence analysis (RASP)")
        ax.legend()
        return ax


@dataclass
class H2mm:
    """Result of a photon-by-photon H2MM analysis.

    Attributes
    ----------
    fret : numpy.ndarray
        Apparent FRET efficiency per state.
    populations : numpy.ndarray
        Photon fraction per state.
    n_states : int
        Number of states in the selected model.
    engine, criterion : str
        Compute engine and model-selection criterion used.
    analysis : object
        The full underlying :class:`H2mmAnalysis` for advanced use.
    """

    fret: np.ndarray
    populations: np.ndarray
    n_states: int
    engine: str
    criterion: str
    analysis: Any

    @property
    def scan(self):
        """Return the model-selection scan (state count, log-lik, BIC, ICL)."""
        return pd.DataFrame(
            [
                {"n_states": f.n_states, "loglik": f.loglik, "bic": f.bic, "icl": f.icl}
                for f in self.analysis.scan
            ]
        )

    def summary(self) -> str:
        """Return a human-readable one-line-per-state summary."""
        order = np.argsort(self.fret)
        lines = [
            f"Best model: {self.n_states} state(s) "
            f"(engine={self.engine}, criterion={self.criterion})"
        ]
        for rank, i in enumerate(order):
            lines.append(
                f"  state {rank}: FRET E = {self.fret[i]:.2f}, "
                f"population = {self.populations[i]:.0%}"
            )
        return "\n".join(lines)

    def plot_states(self, ax: Any = None) -> Any:
        """Draw per-state FRET efficiency, labelled with photon populations."""
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=(5, 4))
        order = np.argsort(self.fret)
        bars = ax.bar(range(len(order)), self.fret[order], color="#2ca02c", width=0.6)
        for rect, pop in zip(bars, self.populations[order]):
            ax.text(
                rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.02,
                f"{pop:.0%}", ha="center", va="bottom",
            )
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([f"state {i}" for i in range(len(order))])
        ax.set_ylabel("Apparent FRET efficiency E")
        ax.set_ylim(0, 1)
        ax.set_title("FRET states")
        return ax

    def plot_model_selection(self, ax: Any = None) -> Any:
        """Draw BIC and ICL versus the number of states (model selection)."""
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=(5, 4))
        scan = self.scan.sort_values("n_states")
        ax.plot(scan["n_states"], scan["bic"], "o-", label="BIC", color="#1f77b4")
        ax.plot(scan["n_states"], scan["icl"], "s--", label="ICL", color="#ff7f0e")
        ax.axvline(self.n_states, color="grey", ls=":", label=f"chosen ({self.n_states})")
        ax.set_xlabel("number of states")
        ax.set_ylabel("information criterion")
        ax.set_title("Model selection")
        ax.set_xticks(scan["n_states"].tolist())
        ax.legend()
        return ax

    def plot_transitions(self, ax: Any = None) -> Any:
        """Draw the state-to-state transition-rate matrix (1/s)."""
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=(5, 4))
        order = np.argsort(self.fret)
        rates = self.analysis.trans_rates[np.ix_(order, order)]
        im = ax.imshow(rates, cmap="magma", origin="upper")
        labels = [f"E={self.fret[i]:.2f}" for i in order]
        ax.set_xticks(range(len(order)))
        ax.set_yticks(range(len(order)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_yticklabels(labels)
        ax.set_xlabel("to state")
        ax.set_ylabel("from state")
        ax.set_title("Transition rates (1/s)")
        for r in range(len(order)):
            for c in range(len(order)):
                if r != c:
                    ax.text(c, r, f"{rates[r, c]:.0f}", ha="center", va="center",
                            color="white", fontsize=8)
        ax.figure.colorbar(im, ax=ax, fraction=0.046)
        return ax

    def plot_dwell_times(self, ax: Any = None) -> Any:
        """Draw per-state dwell-time distributions (milliseconds)."""
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=(5, 4))
        base_ms = self.analysis.base_time_s * 1e3
        order = np.argsort(self.fret)
        colors = plt.cm.viridis(np.linspace(0, 0.85, len(order)))
        for color, i in zip(colors, order):
            durations = np.asarray(self.analysis.dwell_times.get(i, [])) * base_ms
            durations = durations[durations > 0]
            if durations.size:
                ax.hist(durations, bins=25, histtype="step", color=color,
                        label=f"E={self.fret[i]:.2f}")
        ax.set_xlabel("dwell time (ms)")
        ax.set_ylabel("count")
        ax.set_title("Dwell-time distributions")
        ax.legend()
        return ax

    def plot(self, axes: Any = None) -> Any:
        """Draw a 2x2 H2MM dashboard: states, selection, transitions, dwells."""
        import matplotlib.pyplot as plt

        if axes is None:
            _, axes = plt.subplots(2, 2, figsize=(11, 8))
        flat = np.asarray(axes).ravel()
        self.plot_states(flat[0])
        self.plot_model_selection(flat[1])
        self.plot_transitions(flat[2])
        self.plot_dwell_times(flat[3])
        flat[0].figure.tight_layout()
        return axes


@dataclass
class IrfBackground:
    """Per-detector IRF and background estimated from non-burst photons.

    Returned by :meth:`Bursts.irf_background` and
    :meth:`BurstWorkflow.estimate_irf_background`. The non-burst photons of a
    single-molecule measurement (everything the burst search rejects) are the
    built-in scatter/background: their micro-time histogram gives the IRF and
    their interphoton-time tail gives the background rate.

    Attributes
    ----------
    per_detector : dict of str -> DetectorIrfBackground
        The full estimate for each detector (IRF array, background rate, counts).
    setup : Setup
        Detector setup used.
    """

    per_detector: dict[str, Any]
    setup: Setup

    @property
    def background_khz(self) -> dict[str, float]:
        """Background count rate (kHz) per detector name."""
        return {name: d.background_khz for name, d in self.per_detector.items()}

    @property
    def table(self):
        """One row per detector: background rate and non-burst/burst photon counts."""
        return pd.DataFrame(
            [
                {
                    "Detector": d.name,
                    "Background (kHz)": d.background_khz,
                    "Prompt (ns)": d.prompt_ns,
                    "Non-burst photons": d.n_background_photons,
                    "Burst photons": d.n_burst_photons,
                }
                for d in self.per_detector.values()
            ]
        )

    def irf(self, detector: str | None = None) -> np.ndarray:
        """Return the scatter-derived IRF (unit sum) for a detector (default first)."""
        name = detector if detector is not None else self.setup.names()[0]
        return self.per_detector[name].irf

    def plot(self, ax: Any = None) -> Any:
        """Draw the scatter-derived IRF of every detector on a shared time axis."""
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=(6, 4))
        for d in self.per_detector.values():
            if d.irf.sum() > 0:
                ax.plot(d.time_ns, d.irf, lw=1.5,
                        label=f"{d.name} (bg {d.background_khz:.2f} kHz)")
        ax.set_xlabel("Micro time (ns)")
        ax.set_ylabel("IRF (normalised)")
        ax.set_title("Non-burst IRF & background")
        ax.legend()
        return ax


@dataclass
class Bursts:
    """A selected set of single-molecule bursts, ready for FRET analysis.

    Returned by :meth:`BurstWorkflow.select_bursts`. Call :meth:`bva` or
    :meth:`h2mm`; the detector setup is already attached.

    Attributes
    ----------
    names : list of str
        Source measurement filenames.
    dataset_uuids : list of str
        MMFDB object handles the bursts were selected from.
    table : tttrlib.DataStore
        Combined per-burst summary table.
    setup : Setup
        Detector setup used for selection and analysis.
    """

    names: list[str]
    dataset_uuids: list[str]
    table: Any
    setup: Setup
    _tttrs: dict[str, Any] = field(repr=False, default_factory=dict)
    _search: dict[str, Any] = field(repr=False, default_factory=dict)

    def irf_background(
        self,
        *,
        baseline_quantile: float = 0.2,
        bg_tail_fraction: float = 0.8,
    ) -> IrfBackground:
        """Estimate a per-detector IRF and background from the non-burst photons.

        Reuses the burst-search parameters from :meth:`BurstWorkflow.select_bursts`
        so the same burst definition that produced these bursts also defines what
        counts as background here. Every loaded measurement contributes its
        non-burst photons; the results are pooled per detector.

        Parameters
        ----------
        baseline_quantile : float
            Quantile of the non-burst micro-time histogram taken as the flat
            dark-count floor before normalising the IRF.
        bg_tail_fraction : float
            Tail fraction of the interphoton-time histogram used for the
            background rate fit.
        """
        from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

        detectors = {
            d.name: {
                "chs": list(d.routing_channels),
                "micro_time_ranges": [list(r) for r in d.microtime_ranges],
            }
            for d in self.setup.detectors
        }
        search = self._search or {}
        min_photons = int(search.get("min_photons", 60))
        photon_window = int(search.get("photon_window", 10))
        time_window = float(search.get("time_window", 1e-3))

        pooled: dict[str, Any] = {}
        for tttr in self._tttrs.values():
            per_det = extract_irf_background(
                tttr,
                detectors,
                min_photons=min_photons,
                photon_window=photon_window,
                time_window=time_window,
                baseline_quantile=baseline_quantile,
                bg_tail_fraction=bg_tail_fraction,
            )
            for name, est in per_det.items():
                if name not in pooled:
                    pooled[name] = est
                else:
                    prev = pooled[name]
                    prev.irf_raw = prev.irf_raw + est.irf_raw
                    prev.n_background_photons += est.n_background_photons
                    prev.n_burst_photons += est.n_burst_photons
        # Re-derive the IRF/background from the pooled raw histograms so multiple
        # files combine into one estimate rather than being taken from the last.
        if len(self._tttrs) > 1:
            pooled = self._repool(pooled, baseline_quantile)
        return IrfBackground(per_detector=pooled, setup=self.setup)

    @staticmethod
    def _repool(pooled: dict[str, Any], baseline_quantile: float) -> dict[str, Any]:
        """Recompute IRF and prompt from summed raw histograms (multi-file pooling)."""
        from chisurf.core.fluorescence.tcspc.irf import detect_rising_edge

        q = float(np.clip(baseline_quantile, 0.0, 1.0))
        for est in pooled.values():
            raw = est.irf_raw
            if raw.sum() > 0:
                baseline = float(np.quantile(raw, q))
                irf = np.clip(raw - baseline, 0.0, None)
                total = irf.sum()
                est.irf = irf / total if total > 0 else irf
                est.baseline_per_bin = baseline
                est.prompt_ns = float(est.time_ns[detect_rising_edge(raw, smooth=5)])
        return pooled

    def __len__(self) -> int:
        """Return the number of bursts."""
        return row_count(self.table)

    def __repr__(self) -> str:
        """Return a short human summary."""
        sources = ", ".join(self.names)
        return f"<Bursts: {row_count(self.table)} bursts from {sources}>"

    def bva(
        self,
        donor: str | None = None,
        acceptor: str | None = None,
        *,
        photons_per_slice: int = 5,
    ) -> Bva:
        """Run Burst Variance Analysis on a chosen FRET detector pair.

        Parameters
        ----------
        donor, acceptor : str, optional
            Detector names forming the FRET pair. Default to the first two
            detectors in the setup — pick any pair for multi-colour data.
        photons_per_slice : int
            Photons per sub-burst slice (also sets the shot-noise static line).
        """
        from chisurf.plugins.burst.burst_bva.core.computation import compute_bva

        donor_name, acceptor_name = self.setup._pair(donor, acceptor)
        d = self.setup.detector(donor_name)
        a = self.setup.detector(acceptor_name)
        table = compute_bva(
            self.table.copy(),
            self._tttrs,
            donor_channels=list(d.routing_channels),
            donor_micro_time_ranges=d.bva_ranges(),
            acceptor_channels=list(a.routing_channels),
            acceptor_micro_time_ranges=a.bva_ranges(),
            number_of_photons_per_slice=photons_per_slice,
        )
        return Bva(table=table, photons_per_slice=photons_per_slice)

    def two_cde(
        self,
        donor: str | None = None,
        acceptor: str | None = None,
        *,
        acceptor_excitation: str | None = None,
        tau: float = 100e-6,
        kernel: str = "laplace",
        variant: str = "fret",
    ) -> TwoCde:
        """Compute the 2CDE dynamics feature on a chosen detector pair.

        FRET-2CDE / ALEX-2CDE (Tomov et al., BJ 2012) flag within-burst
        dynamics; downstream code filters bursts on the returned values.

        Parameters
        ----------
        donor, acceptor : str, optional
            Detector names forming the FRET pair (default: first two detectors).
        acceptor_excitation : str, optional
            Detector for the acceptor-excitation stream (``variant="alex"``
            only); defaults to the acceptor detector.
        tau : float
            Kernel time constant in seconds.
        kernel : {"laplace", "gaussian"}
            Density kernel (Laplace is the Tomov original).
        variant : {"fret", "alex"}
            Which 2CDE quantity to compute.
        """
        from chisurf.plugins.burst.burst_2cde.core.computation import compute_2cde

        donor_name, acceptor_name = self.setup._pair(donor, acceptor)
        d = self.setup.detector(donor_name)
        a = self.setup.detector(acceptor_name)
        aex = self.setup.detector(acceptor_excitation) if acceptor_excitation else None
        table = compute_2cde(
            self.table.copy(),
            self._tttrs,
            donor_channels=list(d.routing_channels),
            donor_micro_time_ranges=d.bva_ranges(),
            acceptor_channels=list(a.routing_channels),
            acceptor_micro_time_ranges=a.bva_ranges(),
            acceptor_excitation_channels=list(aex.routing_channels) if aex else None,
            acceptor_excitation_micro_time_ranges=aex.bva_ranges() if aex else None,
            tau=tau, kernel=kernel, variant=variant,
        )
        return TwoCde(table=table, variant=variant)

    def recurrence(
        self,
        donor: str | None = None,
        acceptor: str | None = None,
    ) -> Recurrence:
        """Recurrence Analysis of Single Particles (RASP).

        Resolves each burst's arrival time and FRET efficiency from the burst
        table and returns a :class:`Recurrence` handle exposing the
        same-molecule probability and recurrence FRET histograms (Hoffmann et
        al., PCCP 2011) — slow (ms..s) dynamics between diffusing-molecule
        events, not resolvable within a single burst.

        Parameters
        ----------
        donor, acceptor : str, optional
            Detector names for the proximity ratio when it must be derived from
            per-detector photon counts (default: first two detectors). Ignored
            when the table already carries an efficiency column.
        """
        from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

        e = proximity_ratio(self.table)
        if e is None:
            for col in ("Proximity Ratio Mean", "E", "Efficiency"):
                if col in self.table:
                    e = numeric_column(self.table, col)
                    break
        if e is None:
            raise ValueError(
                "recurrence(): no FRET efficiency / proximity-ratio column in the "
                "burst table (need 'Proximity Ratio' or per-detector photon counts)."
            )

        time_col = next(
            (c for c in ("Mean Macro Time (ms)", "Mean Macro Time (s)") if c in self.table),
            None,
        )
        if time_col is None:
            raise ValueError("recurrence(): burst table has no 'Mean Macro Time' column.")
        times = numeric_column(self.table, time_col)
        if time_col.endswith("(ms)"):
            times = times / 1e3

        return Recurrence(times_s=times, efficiency=np.asarray(e, dtype=float))

    def h2mm(
        self,
        states: Sequence[int] = (1, 2, 3),
        *,
        donor: str | None = None,
        acceptor: str | None = None,
        engine: str = "em",
        criterion: str = "bic",
        min_photons: int = 3,
        seed: int = 0,
    ) -> H2mm:
        """Fit a photon-by-photon hidden Markov model (experimental).

        Uses every detector in the setup as a stream (so three- or four-colour
        data works); apparent FRET is computed from the chosen detector pair.

        Parameters
        ----------
        states : sequence of int
            Candidate state counts to scan; the best is chosen by ``criterion``.
        donor, acceptor : str, optional
            Detector names for the reported apparent FRET; default to the first
            two detectors.
        engine : {"em", "em-float32", "surrogate", "surrogate-refine"}
            Compute engine for the per-state-count fits.
        criterion : {"bic", "icl"}
            Model-selection criterion (minimised).
        min_photons : int
            Minimum stream-assigned photons for a burst to enter the fit.
        seed : int
            Random seed for reproducibility.
        """
        from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
        from chisurf.plugins.burst.burst_h2mm.core.photons import bursts_from_dataframe

        donor_name, acceptor_name = self.setup._pair(donor, acceptor)
        names = self.setup.names()
        # Physical time base: seconds per macro-time tick, for real dwell/rate units.
        first_tttr = next(iter(self._tttrs.values()))
        base_time_s = float(first_tttr.header.macro_time_resolution)
        photons = bursts_from_dataframe(
            self.table, self._tttrs, self.setup.stream_defs(), min_photons=min_photons
        )
        result = analyze(
            photons,
            state_counts=tuple(states),
            criterion=criterion,
            engine=engine,
            base_time_s=base_time_s,
            donor_stream=names.index(donor_name),
            acceptor_stream=names.index(acceptor_name),
            seed=seed,
        )
        return H2mm(
            fret=np.asarray(result.fret),
            populations=np.asarray(result.populations),
            n_states=result.best.n_states,
            engine=engine,
            criterion=criterion,
            analysis=result,
        )


@dataclass
class GroundTruth:
    """The known truth of a simulated dataset, for validating recovery.

    Attributes
    ----------
    fret : numpy.ndarray
        Per-state FRET efficiency that was simulated.
    exchange_rate : float
        Symmetric state-to-state exchange rate (1/s); ``0`` means static.
    n_states : int
        Number of conformational states simulated.
    gamma : float
        Detection/quantum-yield ratio baked into the simulated counts (the
        red-channel brightness is scaled by ``gamma``); ``1.0`` is the default,
        symmetric case. Used to validate calibration recovery.
    """

    fret: np.ndarray
    exchange_rate: float
    n_states: int
    gamma: float = 1.0


@dataclass
class Simulation:
    """A simulated dataset registered in MMFDB, with its ground truth.

    Attributes
    ----------
    handle : str
        MMFDB handle of the stored (simulated) measurement.
    setup : Setup
        Detector setup matching the simulation (green=0, red=1).
    truth : GroundTruth
        The FRET efficiencies and exchange rate that were simulated.
    """

    handle: str
    setup: Setup
    truth: GroundTruth


class BurstWorkflow:
    """Guided MMFDB burst workflow: register → select → BVA / H2MM.

    Create one with :meth:`demo` (a throwaway local server for tutorials) or
    :meth:`connect` (an existing MMFDB deployment), then call :meth:`register`
    and :meth:`select_bursts`. :meth:`simulate` generates a dataset with known
    ground truth so results can be validated.
    """

    def __init__(
        self, client: Any, *, workdir: Path, _server: Any = None, _thread: Any = None
    ):
        self._client = client
        self._workdir = Path(workdir)
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._server = _server
        self._thread = _thread
        self._filenames: dict[str, str] = {}

    # -- construction ---------------------------------------------------

    @classmethod
    def connect(
        cls,
        base_url: str,
        *,
        user: str = "admin",
        password: str = "",
        workdir: str | Path | None = None,
    ) -> "BurstWorkflow":
        """Connect to a running MMFDB server and log in.

        Parameters
        ----------
        base_url : str
            Server URL, e.g. ``"http://mmfdb.mylab.org"``.
        user, password : str
            Login credentials.
        workdir : str or Path, optional
            Local scratch directory for fetched datasets. A temporary
            directory is created if omitted.
        """
        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

        client = MMFDBClient(mode="remote", base_url=base_url)
        result = client.login(user_id=user, password=password)
        if not result.get("ok"):
            raise RuntimeError(f"MMFDB login failed: {result.get('error', result)}")
        work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="burst_wf_"))
        return cls(client, workdir=work)

    @classmethod
    def demo(cls, *, workdir: str | Path | None = None) -> "BurstWorkflow":
        """Start a private, throwaway MMFDB server and connect to it.

        Intended for tutorials and offline exploration. The server runs in a
        background thread against a temporary database and is shut down by
        :meth:`close`.
        """
        from mmfdb.config import configure_runtime
        from mmfdb.repository import MFDatabase
        from mmfdb.security.bootstrap import bootstrap_local_admin
        from mmfdb.webadmin import create_app

        work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="burst_wf_"))
        work.mkdir(parents=True, exist_ok=True)
        password = "Admin123!"
        configure_runtime(database_path=work / "mmfdb.db", settings_dir=work)
        with MFDatabase(work / "mmfdb.db") as db:
            bootstrap_local_admin(db.conn, user_id="admin", password=password, commit=True)

        port = _free_port()
        server = make_server(
            "127.0.0.1",
            port,
            create_app(),
            server_class=_ThreadingWSGIServer,
            handler_class=_QuietRequestHandler,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

        client = MMFDBClient(mode="remote", base_url=f"http://127.0.0.1:{port}")
        client.login(user_id="admin", password=password)
        return cls(client, workdir=work, _server=server, _thread=thread)

    # -- steps ----------------------------------------------------------

    def register(self, path: str | Path) -> str:
        """Store a measurement file in MMFDB and return its dataset handle.

        Parameters
        ----------
        path : str or Path
            TTTR measurement file (e.g. a ``.spc`` / ``.ptu`` / ``.ht3``).

        Returns
        -------
        str
            The MMFDB object handle (UUID) identifying the stored dataset.
        """
        reference = self._client.put_object(
            path=str(path), mime_type="application/octet-stream"
        )
        record = reference.get("object", reference)
        object_uuid = str(record["object_uuid"])
        self._filenames[object_uuid] = Path(path).name
        return object_uuid

    def register_all(self, paths: Sequence[str | Path]) -> list[str]:
        """Register several measurement files and return their handles."""
        return [self.register(path) for path in paths]

    def simulate(
        self,
        fret: Sequence[float] = (0.25, 0.75),
        *,
        exchange_rate: float = 2.0,
        brightness: float = 300.0,
        diffusion: float = 0.05,
        n_photons: int = 200_000,
        background: float = 0.02,
        laser_period: float = 32.0,
        dt: float = 0.01,
        seed: int = 12345,
        name: str = "simulation",
        gamma: float = 1.0,
    ) -> Simulation:
        """Simulate a two-colour smFRET dataset and register it in MMFDB.

        Photons are generated with tttrlib's confocal simulator from a
        ground-truth model: one diffusing species per state, with FRET encoded
        as per-channel brightness ``q = [(1-E)*b, E*b]`` on the green/red
        detectors and conformational exchange via a spontaneous rate matrix.
        The exported measurement is stored in MMFDB like any real file, so the
        rest of the workflow (select → BVA → H2MM) runs on it unchanged and the
        recovered states can be checked against :class:`GroundTruth`.

        Parameters
        ----------
        fret : sequence of float
            Ground-truth FRET efficiency of each state (any number of states).
        exchange_rate : float
            Symmetric state-to-state exchange rate (1/ms); ``0`` is static.
        brightness : float
            Per-molecule brightness in kcps.
        diffusion : float
            Translational diffusion coefficient (um^2/ms).
        n_photons : int
            Photon budget for the simulation.
        background : float
            Per-channel background rate (counts/ms).
        laser_period : float
            Excitation period (ns) setting the macro-time axis.
        dt : float
            Simulation time step (ms).
        seed : int
            Random seed.
        name : str
            Base filename for the stored dataset.
        gamma : float
            Detection/quantum-yield ratio to bake into the counts (scales the
            red-channel brightness). ``1.0`` is symmetric; other values make the
            uncorrected proximity ratio gamma-distorted so calibration recovery
            can be validated against :attr:`GroundTruth.gamma`.

        Returns
        -------
        Simulation
            Its ``handle`` feeds :meth:`select_bursts`; ``truth`` holds the
            simulated FRET/exchange; ``setup`` matches the simulated detectors.
        """
        import tttrlib

        efficiencies = [float(e) for e in fret]
        n_states = len(efficiencies)
        if n_states < 2:
            raise ValueError("simulate needs at least two FRET states")
        # Red-channel brightness is scaled by gamma to bake a known detection/
        # quantum-yield ratio into the counts (the uncorrected proximity ratio is
        # then gamma-distorted and only the calibrated correction recovers E).
        species = [
            {"D": diffusion, "q": [(1.0 - e) * brightness, gamma * e * brightness]}
            for e in efficiencies
        ]
        # Spontaneous exchange: equal off-diagonal rates, zero diagonal.
        k_nrad = [
            0.0 if i == j else exchange_rate
            for i in range(n_states)
            for j in range(n_states)
        ]
        config = {
            "settings": {
                "dt": dt,
                "n_ph_max": int(n_photons),
                "n_channels": 2,
                "laser_period": laser_period,
                "active_margin": 1.0,
                "fast_grid_bbox": True,
                "seed_diffusion": seed,
                "seed_emission": seed + 1,
            },
            "box": {"xy": 2.0, "z": 4.0},
            "species": species,
            "k_rad": [0.0] * (n_states * n_states),
            "k_nrad": k_nrad,
            "background": [background, background],
            "population": [0.18] * n_states,
            "excitation": {
                "type": "gaussian3d", "w0": 0.3, "z0": 2.0,
                "extent_xy": 2.0, "extent_z": 4.0, "spacing": 0.1,
            },
        }
        from chisurf.core.fluorescence.simulation import build_engine

        engine = build_engine(config)
        engine.run()
        tttr = engine.to_tttr(dt=dt, n_channels=2, laser_period=laser_period)
        sim_path = self._workdir / f"{name}.spc"
        tttr.write(str(sim_path))

        handle = self.register(sim_path)
        setup = Setup.from_channels(green=(0,), red=(1,), file_type="SPC-130")
        truth = GroundTruth(
            fret=np.asarray(efficiencies),
            exchange_rate=float(exchange_rate),
            n_states=n_states,
            gamma=float(gamma),
        )
        return Simulation(handle=handle, setup=setup, truth=truth)

    def fetch(self, dataset_uuid: str) -> Path:
        """Download a registered dataset by handle and return its local path.

        A public wrapper over the internal fetch used by :meth:`select_bursts`;
        handy for analyses (FCS, imaging) that read the raw file themselves.
        """
        return self._fetch(dataset_uuid)

    def _fetch(self, dataset_uuid: str) -> Path:
        """Download a registered dataset by handle to the local scratch dir."""
        filename = self._filenames.get(dataset_uuid)
        if not filename:
            info = self._client.get_object_info(dataset_uuid)
            record = info.get("object", info)
            filename = str(record.get("original_filename") or f"{dataset_uuid}.dat")
        payload = self._client.get_object(dataset_uuid)
        local_path = self._workdir / filename
        local_path.write_bytes(base64.b64decode(payload["data"]))
        return local_path

    def select_bursts(
        self,
        datasets: str | Sequence[str],
        *,
        setup: Setup | None = None,
        min_photons: int = 30,
        time_window: float = 1e-3,
        photon_window: int = 10,
        method: str = "burst",
    ) -> Bursts:
        """Fetch registered datasets by handle and find single-molecule bursts.

        Parameters
        ----------
        datasets : str or sequence of str
            One handle from :meth:`register`, or several to analyse together.
        setup : Setup, optional
            Detector setup. Defaults to :meth:`Setup.two_color`.
        min_photons : int
            Minimum photons per burst (used by the ``"burst"`` search).
        time_window : float
            Sliding time window (seconds) for the burst search.
        photon_window : int
            Photons in the sliding window for the ``"burst"`` search.
        method : {"burst", "count_rate", "cusum", "bocpd", "kalman"}
            Burst-search algorithm.

        Returns
        -------
        Bursts
            The selected bursts; call ``.bva()`` or ``.h2mm()`` on the result.
        """
        from chisurf.core.fluorescence.burst.photons import load_bur_dataframe
        from chisurf.plugins.burst.burst_selection.api.io import load_tttr
        from chisurf.plugins.burst.burst_selection.api.models import (
            AnalysisRequest,
            AnalysisSettings,
            BurstDetectionSettings,
            CountRateFilterSettings,
            DeltaMacroTimeFilterSettings,
            PhotonFilterSettings,
        )
        from chisurf.plugins.burst.burst_selection.api.selection import analyze_request

        setup = setup or Setup.from_channels(green=(0, 8), red=(1, 9))
        handles = [datasets] if isinstance(datasets, str) else list(datasets)
        if method not in _SEARCH_METHODS:
            raise ValueError(
                f"method {method!r} not in {sorted(_SEARCH_METHODS)}"
            )
        filter_mode, filter_active = _SEARCH_METHODS[method]

        local_paths = [self._fetch(handle) for handle in handles]

        settings = AnalysisSettings()
        settings.photon_filter = PhotonFilterSettings(
            channels=setup.all_routing_channels(),
            filter_active=filter_active,
            used_filter=filter_mode,
            count_rate_filter=CountRateFilterSettings(
                n_ph_max=min_photons, time_window=time_window
            ),
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0),
        )
        settings.burst_detection = BurstDetectionSettings(
            min_photons=min_photons, photon_window=photon_window, time_window=time_window
        )

        out_dir = self._workdir / f"bursts_{handles[0][:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        request = AnalysisRequest(
            files=[str(p) for p in local_paths],
            filetype=setup.file_type,
            settings=settings,
            output_dir=str(out_dir),
        )
        result = analyze_request(request)
        bur_paths = [
            roles["bur"]
            for roles in result.output_paths_by_file.values()
            if "bur" in roles
        ]

        table = load_bur_dataframe(bur_paths)
        real_names = {p.name for p in local_paths}
        # Keep only real burst rows (drop interleaved zero separators, whose
        # "First File" is the sentinel "0" rather than a measurement).
        table = take_where(
            table,
            [str(v) in real_names for v in np.asarray(table["First File"])],
        )
        tttrs = {p.name: load_tttr(p, filetype=setup.file_type) for p in local_paths}
        return Bursts(
            names=[p.name for p in local_paths],
            dataset_uuids=handles,
            table=table,
            setup=setup,
            _tttrs=tttrs,
            _search={
                "min_photons": min_photons,
                "photon_window": photon_window,
                "time_window": time_window,
                "method": method,
            },
        )

    def estimate_irf_background(
        self,
        datasets: str | Sequence[str],
        *,
        setup: Setup | None = None,
        min_photons: int = 60,
        time_window: float = 1e-3,
        photon_window: int = 10,
        method: str = "burst",
        baseline_quantile: float = 0.2,
        bg_tail_fraction: float = 0.8,
    ) -> IrfBackground:
        """Estimate a per-detector IRF and background from a measurement's non-burst photons.

        A one-line convenience that selects bursts and reads the IRF/background
        off the rejected (non-burst) photons — the scatter and dark counts
        between molecules. Equivalent to
        ``wf.select_bursts(datasets, ...).irf_background(...)``.

        Parameters
        ----------
        datasets : str or sequence of str
            Dataset handle(s) from :meth:`register`.
        setup : Setup, optional
            Detector setup (defaults to green/red on channels 0,8 / 1,9).
        min_photons, time_window, photon_window, method
            Burst-search parameters defining which photons are bursts (and hence
            which are background); see :meth:`select_bursts`.
        baseline_quantile : float
            Dark-count floor quantile subtracted before normalising the IRF.
        bg_tail_fraction : float
            Interphoton-time tail fraction used for the background-rate fit.

        Returns
        -------
        IrfBackground
            Per-detector IRF arrays and background rates; call ``.plot()`` or
            read ``.table`` / ``.background_khz``.
        """
        bursts = self.select_bursts(
            datasets,
            setup=setup,
            min_photons=min_photons,
            time_window=time_window,
            photon_window=photon_window,
            method=method,
        )
        return bursts.irf_background(
            baseline_quantile=baseline_quantile, bg_tail_fraction=bg_tail_fraction
        )

    # -- lifecycle ------------------------------------------------------

    def close(self) -> None:
        """Shut down the demo server (no-op for :meth:`connect`)."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            if self._thread is not None:
                self._thread.join(timeout=5)
                self._thread = None
            from mmfdb.config import reset_runtime_config

            reset_runtime_config()

    def __enter__(self) -> "BurstWorkflow":
        """Enter a context manager that closes the workflow on exit."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the workflow on context-manager exit."""
        self.close()
