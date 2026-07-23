"""Qt-free-ish view-model backing the ① Compute LUT AutoForm panel.

Holds the compute state (loaded micro-times, histogram, current LUT table) and
the AutoForm-bound parameters, and delegates all math to the pure ``..api``
layer. The interactive plots live in a custom AutoForm section
(:mod:`.sections`) that drives this model; parameter fields live declaratively in
``lut_compute.view.json``. Mirrors
:class:`chisurf.plugins.tttr.ptu_alex_creator.gui.view_model.AlexViewModel`.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable

import numpy as np

from ..api import compute as _compute
from ..api import io as _io
from ..api import lut as _lut

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "lut_compute.view.json"


class LutComputeViewModel:
    """State + view wiring for the ① Compute LUT panel (math lives in ``api``)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from ``lut_compute.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        # ── AutoForm-bound parameters ───────────────────────────────────
        self.linear_start = 1000
        self.linear_stop = 2000
        self.ntac_required = 4096
        self.noffset = 500
        self.preview_photons = 500000
        self.seed = 12345
        self.normalize = False
        self.mitigate_wrap = False
        self.eps = 1e-6
        self.threshold = 0.2

        # ── loaded data / result state ──────────────────────────────────
        self.files: list[str] = []
        self._loaded_files: list[str] = []
        self.micro: np.ndarray | None = None
        self.counts: np.ndarray | None = None
        self.n_bins: int | None = None
        self.current_table: dict | None = None
        self._observers: list[Callable[[str], None]] = []

    # ── observer hook ──────────────────────────────────────────────────
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb*, called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:  # pragma: no cover
                logger.debug("lut compute observer failed", exc_info=True)

    def update(self) -> None:
        """AutoForm hook after a bound field changes.

        The ``path_list`` file section and every parameter field route here. If
        the file list changed we (re)load the data; otherwise we just recompute.
        """
        if list(self.files) != self._loaded_files:
            if self.files:
                self._reload()
            else:
                self.clear()
            return
        self.compute()
        self.notify("plot")

    # ── file loading ────────────────────────────────────────────────────
    def _reload(self) -> None:
        """Load the current ``files``, build the histogram, seed the region."""
        paths = [str(p) for p in self.files]
        self.micro = _io.load_microtimes(paths)
        self._loaded_files = list(paths)
        self.n_bins = _lut.infer_n_bins(self.micro, None)
        self.counts = _lut.histogram_micro(self.micro, self.n_bins)
        try:
            self.linear_start, self.linear_stop = _lut.autodetect_linear_region(self.counts)
        except Exception:
            self.linear_start, self.linear_stop = self._fallback_region()
        self.ntac_required = int(self.n_bins)
        self.compute()
        self.notify("loaded")

    def load_files(self, paths: list[str]) -> None:
        """Load TTTR files (programmatic entry point)."""
        self.files = [str(p) for p in paths]
        self._reload()

    def clear(self) -> None:
        """Reset all loaded data and the current LUT."""
        self.files = []
        self._loaded_files = []
        self.micro = None
        self.counts = None
        self.n_bins = None
        self.current_table = None
        self.notify("loaded")

    def autodetect(self) -> None:
        """Auto-detect the linear region from the current histogram."""
        if self.counts is None:
            return
        try:
            self.linear_start, self.linear_stop = _lut.autodetect_linear_region(self.counts)
            self.compute()
            self.notify("plot")
        except Exception as exc:  # pragma: no cover - user feedback path
            logger.info("autodetect failed: %s", exc)

    def _fallback_region(self) -> tuple[int, int]:
        n = len(self.counts) if self.counts is not None else 4096
        nonzero = np.where(self.counts > 0)[0] if self.counts is not None else np.array([])
        if nonzero.size < 4:
            start = max(0, n // 4)
            return start, min(n, start + max(32, n // 10))
        first, last = nonzero[0], nonzero[-1] + 1
        width = max(32, (last - first) // 5)
        start = first + (last - first - width) // 2
        return int(start), int(start + width)

    # ── computation ─────────────────────────────────────────────────────
    def counts_effective(self) -> np.ndarray | None:
        """Return counts after thresholding (the histogram used for the LUT)."""
        if self.counts is None:
            return None
        counts = self.counts.copy().astype(float)
        start, stop = int(self.linear_start), int(self.linear_stop)
        if self.normalize:
            region = counts[start:stop]
            mean = float(region.mean()) if region.size else 1.0
            display = counts / (mean if mean > 0 else 1.0)
        else:
            display = counts
        counts[display < float(self.threshold)] = 0
        return counts

    def compute(self) -> None:
        """Build the current LUT table from the effective histogram."""
        counts = self.counts_effective()
        if counts is None:
            self.current_table = None
            return
        try:
            self.current_table = _lut.build_linearization_table(
                counts, int(self.linear_start), int(self.linear_stop),
                int(self.ntac_required), int(self.noffset),
            )
        except Exception:
            self.current_table = None

    def corrected_after_hist(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Return ``(x, counts)`` of the corrected micro-time preview histogram."""
        if self.current_table is None or self.micro is None:
            return None
        corrected = _lut.stochastic_rebin_ntac(
            self.micro, self.current_table["NTAC_fract"], self.current_table["noffset"],
            seed=int(self.seed), max_photons=int(self.preview_photons),
            rounding="floor" if self.mitigate_wrap else "ceil",
            eps=float(self.eps) if self.mitigate_wrap else 0.0,
        )
        ntac = int(self.ntac_required)
        hist, _ = np.histogram((corrected % ntac).astype(int), bins=ntac, range=(0, ntac))
        return np.arange(ntac), hist

    def info_text(self) -> str:
        """One-line summary of the current LUT for the status label."""
        t = self.current_table
        if not t:
            return "No LUT — load a uniform-illumination file and pick the linear region."
        return (f"Range [{t['linear_start']}, {t['linear_stop']}) | "
                f"width={t['linear_stop'] - t['linear_start']} | "
                f"f={t['f']:.6f} | n_mean={t['n_mean']:.2f}")

    # ── export ──────────────────────────────────────────────────────────
    def save_lut(self, path: str) -> str:
        """Save the current LUT table (delegates to the api)."""
        if self.current_table is None:
            raise ValueError("Compute a LUT first.")
        return _io.save_lut(path, self.current_table)

    def export_corrected(self, path: str) -> str:
        """Export the corrected micro-times of all photons."""
        if self.current_table is None or self.micro is None:
            raise ValueError("Compute a LUT first.")
        corrected = _lut.stochastic_rebin_ntac(
            self.micro, self.current_table["NTAC_fract"], self.current_table["noffset"],
            seed=int(self.seed), rounding="floor" if self.mitigate_wrap else "ceil",
            eps=float(self.eps) if self.mitigate_wrap else 0.0,
        )
        ext = os.path.splitext(path)[1].lower()
        if ext == ".npz":
            np.savez_compressed(path, corrected_ntac=corrected)
        elif ext == ".csv":
            np.savetxt(path, corrected, fmt="%d", delimiter=",")
        elif ext == ".txt":
            np.savetxt(path, corrected, fmt="%d")
        else:
            np.save(path, corrected)
        return path

    # kept for symmetry / future rpc use
    compute_lut_from_files = staticmethod(_compute.compute_lut_from_files)
