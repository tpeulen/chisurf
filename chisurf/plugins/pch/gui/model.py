"""Qt-free state and actions of the PCH tool.

The emtk app (:mod:`.app`) draws this model; the photon counting itself and the
model fit stay in the plugin's backend services, reached through
:class:`~.client.PCHClient` exactly as the Qt tool reached them.  Every action
that does real work (``load_path``, ``compute_now``, ``fit_now``) is a plain
method, so it runs headless and inside :class:`chisurf.emtk.jobs.SnapshotJob`.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..api.models import FitResult, PchResult

logger = logging.getLogger(__name__)

#: Photon-stream files this tool opens (lower-case, with the dot).
TTTR_SUFFIXES = (".ptu", ".ht3", ".t2r", ".t3r", ".pto", ".spc")

#: Qt-style file-dialog filter built from :data:`TTTR_SUFFIXES`.
TTTR_FILE_FILTER = (
    "TTTR (" + " ".join(f"*{s}" for s in TTTR_SUFFIXES) + ");;All files (*)"
)

#: Points kept per plotted trace; a trace of a million bins is reduced to the
#: minimum and maximum of each chunk so a spike survives.
TRACE_DISPLAY_POINTS = 4000


class SpeciesRows(list):
    """The species table's rows; ``revision`` tells the table to re-read them."""

    revision = 0


def decimate_minmax(x: Any, y: Any, n_points: int = TRACE_DISPLAY_POINTS) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a trace to about *n_points* points keeping each chunk's extremes.

    Parameters
    ----------
    x, y : array-like
        The full trace.
    n_points : int
        Approximate number of points to keep.

    Returns
    -------
    tuple of numpy.ndarray
        The reduced ``(x, y)``; a trace shorter than *n_points* is returned as is.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n <= n_points or n < 4:
        return x, y
    chunks = max(1, n_points // 2)
    size = n // chunks
    used = size * chunks
    ys = y[:used].reshape(chunks, size)
    xs = x[:used].reshape(chunks, size)
    lo = ys.argmin(axis=1)
    hi = ys.argmax(axis=1)
    rows = np.arange(chunks)
    first = np.minimum(lo, hi)
    second = np.maximum(lo, hi)
    out_x = np.empty(2 * chunks)
    out_y = np.empty(2 * chunks)
    out_x[0::2], out_y[0::2] = xs[rows, first], ys[rows, first]
    out_x[1::2], out_y[1::2] = xs[rows, second], ys[rows, second]
    return out_x, out_y


class PchModel:
    """State and actions of the photon-counting-histogram tool.

    Parameters
    ----------
    client : PCHClient, optional
        Backend client; a local in-process one is created on first use.
    """

    def __init__(self, client: Any = None) -> None:
        self._client = client
        self._observers: list[Callable[[Any], None]] = []
        #: ``callable(method_name)`` that runs a model method off the draw
        #: thread (the app installs its job); ``None`` runs it directly.
        self.runner: Callable[[str], Any] | None = None
        self.busy = False
        #: ``"open"`` / ``"save"`` while the app should show a file dialog.
        self.dialog = ""
        self.folder = ""
        self.pending_path = ""
        # -- data settings ------------------------------------------------
        self.filename = ""
        self.channels = "0,2"
        self.bin_time_us = 100.0
        self.micro_time_min = 0
        self.micro_time_max = 65535
        # -- model fit ----------------------------------------------------
        self.n_components = 1
        self.species = SpeciesRows()
        self._rebuild_species(1, [], [])
        # -- results ------------------------------------------------------
        self.result: PchResult | None = None
        self.fit_result: FitResult | None = None
        self.fit_low = 0.0
        self.fit_high = 1.0
        self.trace_x = np.zeros(0)
        self.trace_y = np.zeros(0)
        self.results_text = ""
        self.status_text = "Ready. Load a TTTR file to begin."
        self.error_text = ""

    # ── observers (SnapshotJob) ────────────────────────────────────────
    def add_observer(self, callback: Callable[[Any], None]) -> None:
        """Register ``callback(event)`` for :meth:`notify`."""
        self._observers.append(callback)

    def notify(self, event: Any = "updated") -> None:
        """Tell every observer that *event* happened."""
        for callback in list(self._observers):
            callback(event)

    # ── the backend client ─────────────────────────────────────────────
    @property
    def client(self) -> Any:
        """The backend client, created on first use."""
        if self._client is None:
            from .client import PCHClient

            self._client = PCHClient()
        return self._client

    # ── messages ───────────────────────────────────────────────────────
    def status_line(self) -> str:
        """The condition to show: an error while there is one, else the status."""
        return self.error_text or self.status_text

    def _fail(self, text: str) -> None:
        """Report *text* as the standing error."""
        self.error_text = text

    def _run(self, method: str) -> bool:
        """Run *method* through the app's job, or directly when there is none."""
        if self.runner is not None:
            return bool(self.runner(method))
        getattr(self, method)()
        return True

    # ── what the form asks ─────────────────────────────────────────────
    def enabled(self, name: str) -> bool:
        """Whether the action *name* may be used now."""
        if self.busy:
            return False
        if name == "compute":
            return bool(self.filename)
        if name in ("fit", "save"):
            return self.result is not None
        return True

    # ── species rows ───────────────────────────────────────────────────
    def _rebuild_species(self, count: int, old_eps: list[float], old_ns: list[float]) -> None:
        rows = SpeciesRows(
            {
                "component": i + 1,
                "epsilon": old_eps[i] if i < len(old_eps) else 2.0,
                "n_mean": old_ns[i] if i < len(old_ns) else 3.0,
            }
            for i in range(count)
        )
        rows.revision = getattr(self.species, "revision", 0) + 1
        self.species = rows

    def set_n_components(self, count: Any = None) -> None:
        """Resize the species table to ``n_components``, keeping the values typed so far."""
        count = int(self.n_components if count is None else count)
        count = max(1, min(10, count))
        self.n_components = count
        self._rebuild_species(
            count,
            [float(r["epsilon"]) for r in self.species],
            [float(r["n_mean"]) for r in self.species],
        )

    def edit_species(self, record: dict, key: str, value: Any) -> None:
        """A table cell was typed: keep the number non-negative, as the Qt spin box did."""
        try:
            record[key] = min(max(float(value), 0.0), 1e6)
        except (TypeError, ValueError):
            pass

    @property
    def initial_epsilons(self) -> list[float]:
        """Starting brightness of every species."""
        return [float(r["epsilon"]) for r in self.species]

    @property
    def initial_ns(self) -> list[float]:
        """Starting mean occupancy of every species."""
        return [float(r["n_mean"]) for r in self.species]

    # ── actions (buttons) ──────────────────────────────────────────────
    def load(self) -> None:
        """Ask the app to show the open-file dialog."""
        self.dialog = "open"

    def compute(self) -> None:
        """Bin the loaded file into the histogram (off the draw thread when the app has a job)."""
        if not self.filename:
            self._fail("Load a TTTR file first.")
            return
        self.error_text = ""
        self._run("compute_now")

    def fit(self) -> None:
        """Fit the species model to the histogram (off the draw thread when the app has a job)."""
        if self.result is None:
            self._fail("Compute the histogram first.")
            return
        self.error_text = ""
        self._run("fit_now")

    def save(self) -> None:
        """Ask the app to show the save dialog."""
        if self.result is None:
            self._fail("Compute the histogram first.")
            return
        self.error_text = ""
        self.dialog = "save"

    # ── work ───────────────────────────────────────────────────────────
    def load_path(self, path: str) -> bool:
        """Open *path* through the backend and arm the compute step."""
        try:
            info = self.client.load_tttr(str(path))
        except Exception as exc:
            # A standing error must be paired with a state that matches it:
            # leaving the previous file's name and results in place would let
            # Compute quietly re-analyse the old data under a load error.
            self.filename = ""
            self.result = None
            self.fit_result = None
            self.results_text = ""
            self._fail(f"Cannot load the file: {exc}")
            return False
        self.filename = str(path)
        self.folder = str(Path(path).parent)
        self.result = None
        self.fit_result = None
        self.results_text = ""
        self.trace_x = self.trace_y = np.zeros(0)
        self.error_text = ""
        self.status_text = f"Loaded: {path} ({info.get('n_photons', 0):,} photons)"
        return True

    def open_file(self, path: Any) -> bool:
        """Load *path* (off the draw thread when the app has a job)."""
        self.pending_path = str(path)
        return self._run("load_pending")

    def load_pending(self) -> None:
        """Worker: load the file :meth:`open_file` was asked for."""
        self.load_path(self.pending_path)

    def on_paths_dropped(self, paths: list[Any]) -> bool:
        """Load the first dropped photon-stream file; say so when none is one."""
        for path in paths:
            if Path(str(path)).suffix.lower() in TTTR_SUFFIXES:
                return self.open_file(path)
        if paths:
            self.error_text = "Drop a photon-stream file (" + ", ".join(TTTR_SUFFIXES) + ")."
        return False

    def parse_channels(self) -> list[int] | None:
        """The channel list typed in the form; ``None`` when it is empty."""
        text = self.channels.strip()
        return list(map(int, text.split(","))) if text else None

    def compute_now(self) -> None:
        """Worker: call the backend and keep its histogram."""
        try:
            channels = self.parse_channels()
        except ValueError as exc:
            self._fail(f"Computing the histogram failed: channel list {self.channels.strip()!r}: {exc}")
            return
        self.status_text = "Binning photons…"
        self.notify("progress")
        try:
            result = PchResult.from_dict(
                self.client.compute(
                    filename=self.filename,
                    channels=channels,
                    bin_time_us=float(self.bin_time_us),
                    micro_time_min=int(self.micro_time_min),
                    micro_time_max=int(self.micro_time_max),
                )
            )
        except Exception as exc:
            self._fail(f"Computing the histogram failed: {exc}")
            return
        self.result = result
        self.fit_result = None
        self.results_text = ""
        self.trace_x, self.trace_y = decimate_minmax(result.trace_t, result.trace_counts)
        self.fit_low = 0.0
        self.fit_high = float(max(result.k_vals))
        self.error_text = ""
        self.status_text = (
            f"Computed PCH: {result.total_bins:,} bins, {len(result.k_vals)} k-values"
        )

    def fit_now(self) -> None:
        """Worker: fit the species model over the selected k range."""
        if self.result is None:
            self._fail("Compute the histogram first.")
            return
        n_comp = int(self.n_components)
        self.status_text = "Fitting…"
        self.notify("progress")
        try:
            raw = self.client.fit(
                k_vals=self.result.k_vals,
                p_exp=self.result.p_exp,
                hist_counts=self.result.hist_counts,
                total_bins=self.result.total_bins,
                n_components=n_comp,
                initial_epsilons=self.initial_epsilons,
                initial_Ns=self.initial_ns,
                fit_low=int(self.fit_low),
                fit_high=int(self.fit_high),
            )
            fit_result = FitResult.from_dict(raw)
            rows = SpeciesRows(
                {
                    "component": i + 1,
                    "epsilon": fit_result.epsilons[i],
                    "n_mean": fit_result.avg_Ns[i],
                }
                for i in range(n_comp)
            )
        except Exception as exc:
            self._fail(f"The fit failed: {exc}")
            return
        rows.revision = getattr(self.species, "revision", 0) + 1
        self.species = rows
        self.fit_result = fit_result
        self.update_results_text()
        self.error_text = ""
        self.status_text = (
            f"Fit complete: χ²={fit_result.chi2:.2f}, red. χ²={fit_result.reduced_chi2:.3f}"
        )

    def set_region(self, low: float, high: float) -> None:
        """The fit range on the histogram moved; recompute the χ² of the fit over it."""
        self.fit_low, self.fit_high = float(min(low, high)), float(max(low, high))
        if self.fit_result is not None and self.result is not None:
            self.update_results_text()

    # ── results text ───────────────────────────────────────────────────
    def update_results_text(self) -> None:
        """Rebuild the fit-results text over the current k range."""
        if self.result is None or self.fit_result is None:
            return
        fr = self.fit_result
        fit_low, fit_high = int(self.fit_low), int(self.fit_high)

        k_arr = np.array(self.result.k_vals)
        p_fit = np.array(fr.p_fit)
        exp_cnt = p_fit * self.result.total_bins
        obs_cnt = np.array(self.result.hist_counts)
        mask = (k_arr >= fit_low) & (k_arr <= fit_high) & (exp_cnt > 0)
        chi2 = float(np.sum((obs_cnt[mask] - exp_cnt[mask]) ** 2 / exp_cnt[mask]))
        dof = int(mask.sum()) - (fr.n_components * 2)
        red_chi2 = chi2 / dof if dof > 0 else float("nan")

        lines = [
            "ε: molecular brightness  ⟨N⟩: molecules in volume",
            "",
            f"Region: {fit_low}–{fit_high}",
        ]
        for i in range(fr.n_components):
            lines.append(
                f"Comp{i + 1}: ε={fr.epsilons[i]:.4f}  "
                f"⟨N⟩={fr.avg_Ns[i]:.4f}  "
                f"x={fr.fractions[i]:.1f}%"
            )
        lines += [
            "",
            f"χ² = {chi2:.2f}   red. χ² = {red_chi2:.3f}   dof = {dof}",
        ]
        self.results_text = "\n".join(lines)

    # ── plots ──────────────────────────────────────────────────────────
    def histogram_points(self) -> tuple[np.ndarray, np.ndarray]:
        """``(k, P(k))`` of the measured histogram, without the empty bins a log axis cannot show."""
        if self.result is None:
            return np.zeros(0), np.zeros(0)
        k = np.asarray(self.result.k_vals, dtype=float)
        p = np.asarray(self.result.p_exp, dtype=float)
        keep = p > 0
        return k[keep], p[keep]

    def fit_curve(self) -> tuple[np.ndarray, np.ndarray]:
        """``(k, P_fit(k))`` over the fitted k range."""
        if self.result is None or self.fit_result is None:
            return np.zeros(0), np.zeros(0)
        k = np.asarray(self.result.k_vals, dtype=float)
        p = np.asarray(self.fit_result.p_fit, dtype=float)
        keep = (k >= self.fit_result.fit_low) & (k <= self.fit_result.fit_high) & (p > 0)
        return k[keep], p[keep]

    # ── file output ────────────────────────────────────────────────────
    def save_outputs(self, base: str) -> None:
        """Write ``<base>.npz`` / ``.csv`` / ``.txt`` (the data outputs of the Qt tool)."""
        if self.result is None:
            raise RuntimeError("Compute the histogram first.")
        p_fit_arr = (
            np.array(self.fit_result.p_fit) if self.fit_result is not None else np.array([])
        )
        np.savez(
            f"{base}.npz",
            t_centers=self.result.trace_t,
            trace_counts=self.result.trace_counts,
            k_vals=self.result.k_vals,
            p_exp=self.result.p_exp,
            p_fit=p_fit_arr,
            fit_results=self.results_text.splitlines(),
        )
        with open(f"{base}.csv", "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["k", "P_exp", "P_fit"])
            for i, k in enumerate(self.result.k_vals):
                fitv = p_fit_arr[i] if len(p_fit_arr) > i else 0.0
                writer.writerow([int(k), self.result.p_exp[i], fitv])
        with open(f"{base}.txt", "w", encoding="utf-8") as ftxt:
            ftxt.write(self.results_text)

    def save_to(self, base: str) -> bool:
        """Save under *base*; report the outcome as the status or the error."""
        try:
            self.save_outputs(base)
        except Exception as exc:
            self._fail(f"Saving failed: {exc}")
            return False
        self.folder = str(Path(base).parent)
        self.error_text = ""
        self.status_text = f"Saved {base}.npz / .csv / .txt"
        return True

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict[str, Any]:
        """What is remembered between sessions."""
        return {
            "folder": self.folder,
            "channels": self.channels,
            "bin_time_us": self.bin_time_us,
            "micro_time_min": self.micro_time_min,
            "micro_time_max": self.micro_time_max,
            "n_components": self.n_components,
            "epsilons": self.initial_epsilons,
            "ns": self.initial_ns,
        }

    def restore_settings(self, state: dict[str, Any]) -> None:
        """Take back what :meth:`export_settings` wrote; unknown or bad keys are ignored."""
        state = dict(state or {})
        self.folder = str(state.get("folder", self.folder))
        self.channels = str(state.get("channels", self.channels))
        for key, cast in (
            ("bin_time_us", float),
            ("micro_time_min", int),
            ("micro_time_max", int),
        ):
            try:
                setattr(self, key, cast(state[key]))
            except (KeyError, TypeError, ValueError):
                pass
        try:
            count = max(1, min(10, int(state["n_components"])))
        except (KeyError, TypeError, ValueError):
            count = self.n_components
        eps = [float(v) for v in state.get("epsilons", []) if _is_number(v)]
        ns = [float(v) for v in state.get("ns", []) if _is_number(v)]
        self.n_components = count
        self._rebuild_species(count, eps, ns)


def _is_number(value: Any) -> bool:
    """Whether *value* reads as a float."""
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
