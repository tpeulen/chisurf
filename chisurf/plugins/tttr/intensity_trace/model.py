"""The intensity-trace tool's state and computation, Qt-free: what the Qt widget and the native app both use.

A TTTR file binned per detector (or per routing channel) into counts per time window; the count histograms; a hidden
Markov model of the binned trace (the shared HMM core: dimmest state first); the BIC of 1..N states; dwell times per
state with a single-exponential fit; FRET efficiency (first channel over the sum) per state; and the structured export
the Qt tool writes beside the file (``<stem>_HMM#<n>_<ms>ms/{bst,traces,hist}``).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: The Qt widget's ranges.
WINDOW_MS = (0.1, 999.0)
BINS = (10, 500)
COUNTS = (0.0, 10000.0)
STATES = (1, 15)


def save_burst_ids(hmm_states, time_axis, time_window_s, tttr_obj, output_dir=".", file_path=None):
    """One ``.bst`` file per state: each run of consecutive bins in that state as first/last photon index (inclusive)."""
    burst_ids = {}
    for state in np.unique(hmm_states):
        indices = np.where(hmm_states == state)[0]
        if len(indices) == 0:
            continue
        bursts = []
        start_idx = indices[0]
        for i in range(1, len(indices)):
            if indices[i] != indices[i - 1] + 1:
                bursts.append((start_idx, indices[i - 1]))
                start_idx = indices[i]
        bursts.append((start_idx, indices[-1]))
        burst_ids[state] = bursts
        name = f"{pathlib.Path(file_path).stem}_state_{state}.bst" if file_path else f"burst_ids_state_{state}.bst"
        resolution = tttr_obj.header.macro_time_resolution
        with open(pathlib.Path(output_dir) / name, "w") as f:
            for start_bin, stop_bin in bursts:
                start = np.searchsorted(tttr_obj.macro_times, time_axis[start_bin] / resolution)
                stop = np.searchsorted(tttr_obj.macro_times, (time_axis[stop_bin] + time_window_s) / resolution)
                # .bst rows are first/last photon, both inclusive; searchsorted's stop is the first photon after the run
                if stop > start:
                    f.write(f"{start}\t{stop - 1}\n")
    return burst_ids


def compute_bic_curve(data, max_states=10):
    """``(n_states, bic)`` for HMMs of 1..max_states states (``nan`` where a fit failed): its elbow is the state count."""
    from chisurf.plugins.core.hmm.core import scan_state_counts

    scan = scan_state_counts(data, min_states=1, max_states=max_states)
    return list(zip(scan.n_states, scan.bic))


def compute_dwell_times(state_sequence, time_step=1.0):
    """State index to the list of its dwell times (in the units of *time_step*)."""
    from chisurf.plugins.core.hmm.core import dwell_times

    return dwell_times(state_sequence, time_step)


def dwell_histograms(dwell: dict, lo_ms: float, hi_ms: float, n_bins: int, normalize: bool = False) -> dict:
    """Per state ``(centres_ms, counts, (A, tau_ms) or None)``: the histogram and its single-exponential fit."""
    from scipy.optimize import curve_fit

    out = {}
    if hi_ms <= lo_ms:
        return out
    edges = np.linspace(lo_ms, hi_ms, int(n_bins) + 1)
    for state, times in dwell.items():
        if len(times) == 0:
            continue
        y, x = np.histogram(np.asarray(times) * 1e3, bins=edges)
        y = y.astype(float)
        if normalize and y.sum() > 0:
            y = y / y.sum()
        centres = 0.5 * (x[:-1] + x[1:])
        fit = None
        mask = y > 0
        if mask.sum() >= 2:
            try:
                popt, _ = curve_fit(lambda t, a, tau: a * np.exp(-t / tau), centres[mask], y[mask],
                                    p0=(y.max(), (centres * y).sum() / y.sum()))
                fit = (float(popt[0]), float(popt[1]))
            except Exception:  # noqa: BLE001 - a histogram the exponential does not fit has no fit
                fit = None
        out[state] = (centres, y, fit)
    return out


def histogram(values, n_bins: int, lo: float | None, hi: float | None):
    """Counts of the non-zero values in [lo, hi] (the Qt histogram's rule); ``(centres, counts)`` or ``None``."""
    data = np.asarray(values, float)
    data = data[data > 0]
    if lo is not None and hi is not None and hi > lo:
        data = data[(data >= lo) & (data <= hi)]
    if data.size == 0:
        return None
    counts, edges = np.histogram(data, bins=int(n_bins))
    return 0.5 * (edges[:-1] + edges[1:]), counts


@dataclass
class IntensityTraceModel:
    """Settings, the binned trace and the HMM result."""

    window_ms: float = 10.0
    n_bins: int = 41
    hist_min: float = 0.0
    hist_max: float = 1000.0
    n_states: int = 3
    path: str = ""
    #: The detector setup: ``{"detectors": {name: {"chs", "micro_time_ranges"}}}``; ``None`` bins routing channels.
    setup: dict | None = None
    #: Ticked detectors (or ``"routing_<n>"`` without a setup); empty = all.
    selected: list[str] = field(default_factory=list)
    time_axis: np.ndarray = field(default_factory=lambda: np.zeros(0))
    counts: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    labels: list[str] = field(default_factory=list)
    states: np.ndarray | None = None
    transmat: np.ndarray | None = None
    message: str = ""
    #: Routing channels the loaded file uses (``routing_<n>``): what the selection offers without a setup.
    available: list[str] = field(default_factory=list)

    # ── loading ───────────────────────────────────────────────────────────

    def choices(self, used_channels: list[int] | None = None) -> list[str]:
        """What the detector selection lists: the setup's detectors, else routing channels."""
        detectors = (self.setup or {}).get("detectors") or {}
        if detectors:
            return [str(name) for name in detectors]
        if used_channels is None and self.available:
            return list(self.available)
        # before a file is read: the Qt widget's routing channels 0-7
        return [f"routing_{c}" for c in (used_channels if used_channels is not None else range(8))]

    def load(self, path: str | pathlib.Path) -> bool:
        """Bin *path* with the current window, setup and selection; the HMM result is dropped (it was of the old trace)."""
        from chisurf.plugins.tttr.trace_browser.core.binning import bin_trace

        path = pathlib.Path(str(path))
        if not path.is_file():
            self.message = f"No such file: {path}"
            return False
        import tttrlib

        window_s = float(self.window_ms) / 1000.0
        detectors = (self.setup or {}).get("detectors") or {}
        try:
            tttr = tttrlib.TTTR(str(path))  # read once: the channels it uses and the binning
            if detectors:
                selected = [s for s in self.selected if s in detectors] or None
                t, counts, labels = bin_trace(tttr, window_s, detectors=detectors, selected=selected)
            else:
                channels = [int(s.split("_", 1)[1]) for s in self.selected if s.startswith("routing_")] or None
                t, counts, labels = bin_trace(tttr, window_s, channels=channels)
        except Exception as exc:  # noqa: BLE001 - shown in the status line
            self.message = f"Could not read {path.name}: {exc}"
            return False
        if self.path != str(path) and not detectors:
            # a new file: offer the channels it uses (Qt offered 0-7, so channels 8+ could not be chosen)
            self.available = [f"routing_{int(c)}" for c in sorted(tttr.get_used_routing_channels())]
        self.path = str(path)
        self.time_axis, self.counts, self.labels = np.asarray(t), np.asarray(counts, float), list(labels)
        self.states = self.transmat = None
        n = self.counts.shape[0]
        self.message = (f"{path.name}: {n} bins of {self.window_ms:g} ms, {', '.join(self.labels)}"
                        if n else f"{path.name}: no photons in the selected detectors")
        return n > 0

    def reload(self) -> bool:
        return self.load(self.path) if self.path else False

    # ── derived ───────────────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        return self.counts.size > 0

    @property
    def total(self) -> np.ndarray:
        return self.counts.sum(axis=1) if self.loaded else np.zeros(0)

    @property
    def fret(self) -> np.ndarray | None:
        """FRET efficiency per bin (first channel over the sum), with at least two channels."""
        if not self.loaded or self.counts.shape[1] < 2:
            return None
        return self.counts[:, 0] / np.clip(self.total, 1e-12, None)

    def fret_by_state(self) -> dict:
        fret = self.fret
        if fret is None or self.states is None:
            return {}
        return {int(s): fret[self.states == s] for s in range(int(np.max(self.states)) + 1)}

    def histograms(self) -> list[tuple[str, Any]]:
        """``(label, (centres, counts) or None)`` per channel, then the sum."""
        rows = [(label, histogram(self.counts[:, i], self.n_bins, self.hist_min, self.hist_max))
                for i, label in enumerate(self.labels)]
        rows.append(("Sum", histogram(self.total, self.n_bins, self.hist_min, self.hist_max)))
        return rows

    # ── HMM ───────────────────────────────────────────────────────────────

    def run_hmm(self) -> str:
        """Fit an HMM of :attr:`n_states` states to the trace (dimmest state first)."""
        if not self.loaded:
            return "Load a TTTR file first."
        from chisurf.plugins.core.hmm.api import HmmSettings
        from chisurf.plugins.core.hmm.core import fit_traces

        fit = fit_traces(self.counts, HmmSettings(n_states=int(self.n_states), covariance_type="full", n_iter=1000))
        self.states, self.transmat = np.asarray(fit.state_array), np.asarray(fit.transmat)
        occupancy = np.bincount(self.states, minlength=int(self.n_states))
        self.message = f"HMM of {self.n_states} states: " + ", ".join(
            f"state {i} {n} bins" for i, n in enumerate(occupancy))
        return self.message

    def dwell_times(self) -> dict:
        return compute_dwell_times(self.states, float(self.window_ms) / 1000.0) if self.states is not None else {}

    def bic_curve(self, max_states: int = STATES[1]):
        return compute_bic_curve(self.counts, max_states=max_states) if self.loaded else []

    # ── files ─────────────────────────────────────────────────────────────

    def trace_table(self) -> tuple[np.ndarray, str, list[str]]:
        """``(data, header, formats)`` of the traces CSV: time, one column per channel, the state if there is one."""
        labels = list(self.labels) if len(self.labels) == self.counts.shape[1] else [
            f"ch{i}" for i in range(self.counts.shape[1])]
        with_states = self.states is not None and len(self.states) == len(self.time_axis)
        cols = [self.time_axis, *(self.counts[:, i] for i in range(self.counts.shape[1]))]
        if with_states:
            cols.append(np.asarray(self.states, dtype=int))
        header = ",".join(["time_s", *labels, *(["HMM_State"] if with_states else [])])
        return np.column_stack(cols), header, ["%.6f"] * (1 + self.counts.shape[1]) + (["%d"] if with_states else [])

    def save_traces(self, path) -> pathlib.Path:
        data, header, fmts = self.trace_table()
        np.savetxt(str(path), data, delimiter=",", header=header, comments="", fmt=fmts)
        return pathlib.Path(path)

    def export(self) -> pathlib.Path:
        """The HMM outputs beside the file, as the Qt tool writes them after Compute HMM:
        ``<stem>_HMM#<n>_<ms>ms/`` with ``bst/`` (burst IDs per state), ``traces/`` (traces, state and FRET
        trajectories) and ``hist/`` (per-channel, sum and FRET histograms)."""
        import tttrlib

        src = pathlib.Path(self.path).resolve()
        stem = src.stem
        base = src.parent / f"{stem}_HMM#{int(self.n_states)}_{int(round(self.window_ms))}ms"
        bst, traces, hists = base / "bst", base / "traces", base / "hist"
        for d in (base, bst, traces, hists):
            d.mkdir(parents=True, exist_ok=True)
        save_burst_ids(self.states, self.time_axis, self.window_ms / 1000.0, tttrlib.TTTR(str(src)),
                       output_dir=str(bst), file_path=self.path)
        self.save_traces(traces / f"{stem}_traces.csv")
        if self.states is not None:
            np.savetxt(str(traces / f"{stem}_state_traj.csv"),
                       np.column_stack([self.time_axis, np.asarray(self.states, int)]), delimiter=",",
                       header="time_s,HMM_State", comments="", fmt=["%.6f", "%d"])
        fret = self.fret
        if fret is not None:
            np.savetxt(str(traces / f"{stem}_fret_traj.csv"), np.column_stack([self.time_axis, fret]), delimiter=",",
                       header="time_s,FRET_efficiency", comments="", fmt=["%.6f", "%.6f"])
        for label, hist in self.histograms():
            if hist is not None:
                name = "sum" if label == "Sum" else label
                np.savetxt(str(hists / f"{stem}_hist_{name}.csv"), np.column_stack(hist), delimiter=",",
                           header="bin_center,counts", comments="", fmt=["%.6f", "%d"])
        if fret is not None:
            h, edges = np.histogram(fret[np.isfinite(fret)], bins=np.linspace(0.0, 1.0, 51), density=True)
            np.savetxt(str(hists / f"{stem}_fret_hist.csv"), np.column_stack([0.5 * (edges[:-1] + edges[1:]), h]),
                       delimiter=",", header="fret_bin_center,density", comments="", fmt=["%.6f", "%.6f"])
        return base
