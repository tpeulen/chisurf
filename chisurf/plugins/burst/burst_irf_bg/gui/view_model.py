"""Qt-free view-model backing the Burst IRF & Background tool.

:class:`IrfBackgroundViewModel` holds the dropped TTTR file list, the burst-search
and baseline parameters, and the per-detector IRF/background results computed from
the **non-burst** photons via
:func:`chisurf.core.fluorescence.burst.extract_irf_background` (display) and
:func:`chisurf.core.fluorescence.burst.extract_mle_irf_background` (the vv_vh-
stacked patterns the burst MLE consumes). Non-burst photons of several files are
pooled per detector. The channel definition comes from the (Qt)
``DetectorWizardPage`` via an injected ``channels_provider`` callable, keeping
this model Qt-free and headlessly testable. The GUI (``gui.tool`` +
``gui.sections``) owns Qt concerns.

Mirrors :class:`chisurf.plugins.tttr.tttr_count_rate_analysis.gui.view_model.CountRateViewModel`.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable

import numpy as np
import tttrlib

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "irf_bg.view.json"

# Distinct colours for the per-detector IRF traces.
_COLORS = ["#2ca02c", "#d62728", "#1f77b4", "#9467bd", "#ff7f0e", "#17becf"]


class IrfBackgroundViewModel:
    """State + logic for the Burst IRF & Background tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``irf_bg.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.files: list[str] = []
        #: Callable returning the DetectorWizardPage detectors map (set by the GUI).
        self.channels_provider: Callable[[], dict] | None = None

        # Parameters (bound to AutoForm ``value`` sections).
        self.min_photons: int = 60
        self.photon_window: int = 10
        self.time_window_ms: float = 1.0
        self.baseline_quantile: float = 0.2
        self.micro_time_binning: int = 1

        # Results (populated by :meth:`compute`).
        self._display: dict[str, dict] = {}
        self._mle: dict[str, dict[str, np.ndarray]] = {}

        self._observers: list[Callable[[str], None]] = []

    # ── observer hook ──────────────────────────────────────────────────
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("irf-bg observer failed", exc_info=True)

    def update(self) -> None:
        """AutoForm hook: the ``path_list`` section wrote ``files`` — refresh views."""
        self.notify("files")

    # ── file list ──────────────────────────────────────────────────────
    def add_files(self, paths: list[str]) -> None:
        """Add unique TTTR files, sorted lexically by basename."""
        added = False
        for p in paths:
            if p and p not in self.files:
                self.files.append(p)
                added = True
        if added:
            self.files.sort(key=lambda p: os.path.basename(p).lower())
            self.notify("files")

    def clear(self) -> None:
        """Drop all files and results."""
        self.files = []
        self._display = {}
        self._mle = {}
        self.notify("files")

    # ── compute ────────────────────────────────────────────────────────
    def can_compute(self) -> str | None:
        """Return ``None`` when a computation can run, else a reason string."""
        if not self.files:
            return "Please load TTTR files first."
        if not self._channels():
            return "Please define detectors in the channel-definition tab."
        return None

    def _channels(self) -> dict:
        try:
            return self.channels_provider() if callable(self.channels_provider) else {}
        except Exception:
            logger.warning("irf-bg: channels_provider failed", exc_info=True)
            return {}

    def compute(self) -> None:
        """Extract pooled per-detector IRF/background from every loaded file."""
        reason = self.can_compute()
        if reason is not None:
            raise ValueError(reason)

        from chisurf.core.fluorescence.burst import (
            extract_irf_background,
            extract_mle_irf_background,
            non_burst_mask,
        )
        from chisurf.core.fluorescence.tcspc.irf import detect_rising_edge

        channels = self._channels()
        time_window_s = float(self.time_window_ms) / 1000.0
        q = float(np.clip(self.baseline_quantile, 0.0, 1.0))

        display: dict[str, dict] = {}
        mle: dict[str, dict[str, np.ndarray]] = {}
        for path in self.files:
            tttr = tttrlib.TTTR(path)
            keep = non_burst_mask(
                tttr,
                min_photons=int(self.min_photons),
                photon_window=int(self.photon_window),
                time_window=time_window_s,
            )
            per = extract_irf_background(tttr, channels, mask=keep, baseline_quantile=q)
            perm = extract_mle_irf_background(
                tttr,
                channels,
                micro_time_binning=int(self.micro_time_binning),
                mask=keep,
                baseline_quantile=q,
            )
            for name, det in per.items():
                slot = display.setdefault(
                    name,
                    {
                        "irf_raw": np.zeros_like(det.irf_raw),
                        "time_ns": det.time_ns,
                        "bg_sum": 0.0,
                        "bg_n": 0,
                        "n_bg": 0,
                        "n_burst": 0,
                    },
                )
                slot["irf_raw"] = slot["irf_raw"] + det.irf_raw
                slot["bg_sum"] += det.background_khz
                slot["bg_n"] += 1
                slot["n_bg"] += det.n_background_photons
                slot["n_burst"] += det.n_burst_photons
            for name, pat in perm.items():
                mslot = mle.setdefault(
                    name,
                    {"irf": np.zeros_like(pat["irf"]), "bg": np.zeros_like(pat["bg"])},
                )
                mslot["irf"] = mslot["irf"] + pat["irf"]
                mslot["bg"] = mslot["bg"] + pat["bg"]

        # Finalise the pooled display IRF (floor-subtract + normalise) and prompt.
        for slot in display.values():
            raw = slot["irf_raw"]
            if raw.sum() > 0:
                irf = np.clip(raw - float(np.quantile(raw, q)), 0.0, None)
                total = irf.sum()
                slot["irf"] = irf / total if total > 0 else irf
                slot["prompt_ns"] = float(slot["time_ns"][detect_rising_edge(raw, smooth=5)])
            else:
                slot["irf"] = np.zeros_like(raw)
                slot["prompt_ns"] = 0.0
            slot["background_khz"] = slot["bg_sum"] / slot["bg_n"] if slot["bg_n"] else 0.0

        self._display = display
        self._mle = mle
        self.notify("computed")

    # ── MLE handoff ────────────────────────────────────────────────────
    def mle_patterns(self) -> dict[str, dict[str, np.ndarray]]:
        """Return the vv_vh-stacked ``{detector: {"irf", "bg"}}`` patterns for the MLE."""
        return self._mle

    def has_results(self) -> bool:
        """Whether a computation has produced results."""
        return bool(self._display)

    # ── AutoForm accessors ─────────────────────────────────────────────
    def results_rows(self) -> list[dict]:
        """Per-detector summary rows (background kHz, prompt, photon counts)."""
        rows = []
        for name, slot in self._display.items():
            rows.append(
                {
                    "detector": name,
                    "background_khz": float(slot.get("background_khz", 0.0)),
                    "prompt_ns": float(slot.get("prompt_ns", 0.0)),
                    "n_bg": int(slot.get("n_bg", 0)),
                    "n_burst": int(slot.get("n_burst", 0)),
                }
            )
        return rows

    def irf_series(self) -> list[dict]:
        """Per-detector normalised-IRF vs micro-time (ns) series for the plot."""
        series = []
        for i, (name, slot) in enumerate(self._display.items()):
            irf = np.asarray(slot.get("irf", []), dtype=float)
            if irf.sum() <= 0:
                continue
            series.append(
                {
                    "x": np.asarray(slot["time_ns"], dtype=float),
                    "y": irf,
                    "name": name,
                    "color": _COLORS[i % len(_COLORS)],
                    "width": 2,
                }
            )
        return series


__all__ = ["IrfBackgroundViewModel"]
