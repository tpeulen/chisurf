"""Qt-free view-model backing the Burst Background Estimation (AutoForm) tool.

:class:`BackgroundViewModel` holds the loaded TTTR files and the per-file,
per-detector background diagnostics from
:func:`chisurf.core.fluorescence.burst.background_diagnostics_from_bursts` (the
inter-photon-time histogram, the fitted background-tail model, and the resulting
rate in kHz). The detector channel definition comes from the (Qt)
``DetectorWizardPage`` via an injected ``channels_provider`` callable, keeping
this model Qt-free. The GUI (``gui/tool`` host + ``gui/sections``) owns Qt
concerns. Mirrors :class:`~...burst_irf_bg.gui.view_model.IrfBackgroundViewModel`.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "gui" / "background.view.json"

# Stable per-detector colours for the diagnostics traces / bars.
_COLORS = {
    "green": (44, 160, 44),
    "red": (214, 39, 40),
    "yellow": (188, 189, 34),
    "blue": (31, 119, 180),
}
_FALLBACK = [(148, 103, 189), (255, 127, 14), (23, 190, 207), (140, 86, 75)]


def det_color(name: str) -> tuple[int, int, int]:
    """Return an RGB colour for detector *name* (named palette, else a hash)."""
    key = str(name).lower()
    if key in _COLORS:
        return _COLORS[key]
    return _FALLBACK[hash(key) % len(_FALLBACK)]


class BackgroundViewModel:
    """State + logic for the Burst Background Estimation tool (no Qt)."""

    def __init__(self, show_channel_definition: bool = True) -> None:
        self.show_channel_definition = bool(show_channel_definition)
        self.files: list[str] = []
        #: Callable returning the DetectorWizardPage detectors map (set by the GUI).
        self.channels_provider: Callable[[], dict] | None = None
        #: The Qt DetectorWizardPage, exposed so the shell can push channels in.
        self.detector_wizard_page = None

        # Results.
        self.backgrounds: dict[str, dict[str, float]] = {}
        self.diagnostics: dict[str, dict] = {}
        self.status: str = "Load files, define detectors, then estimate."

        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve the view spec, dropping the channels dock when hidden."""
        from chisurf.core.dataspec import load_view_spec

        spec = load_view_spec(_VIEW_JSON)
        if self.show_channel_definition:
            return spec
        # Remove the "Channel Definition" dock (the shell supplies channels).
        root = spec.sections[0]
        kept = tuple(s for s in root.sections if s.title != "Channel Definition")
        import dataclasses

        new_root = dataclasses.replace(root, sections=kept)
        return dataclasses.replace(spec, sections=(new_root,))

    # ── observers ──────────────────────────────────────────────────────
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("background observer failed", exc_info=True)

    def update(self) -> None:
        """AutoForm hook: the ``path_list`` section wrote ``files`` — refresh."""
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
        self.backgrounds.clear()
        self.diagnostics.clear()
        self.notify("files")

    # ── estimate ───────────────────────────────────────────────────────
    def _channels(self) -> dict:
        try:
            return self.channels_provider() if callable(self.channels_provider) else {}
        except Exception:
            logger.warning("background: channels_provider failed", exc_info=True)
            return {}

    def can_estimate(self) -> str | None:
        """Return ``None`` when an estimate can run, else a reason string."""
        if not self.files:
            return "Please load TTTR files first."
        if not self._channels():
            return "Please define at least one detector in the channel definition tab."
        return None

    def estimate(self) -> None:
        """Estimate per-file, per-detector background from every loaded file."""
        reason = self.can_estimate()
        if reason is not None:
            raise ValueError(reason)

        import tttrlib

        import chisurf.core.fluorescence.burst as _burst

        detectors = self._channels()
        self.backgrounds.clear()
        self.diagnostics.clear()
        for path in self.files:
            try:
                tttr = tttrlib.TTTR(path)
            except Exception as exc:
                logger.warning("background: could not read %s: %s", path, exc)
                continue
            diags = _burst.background_diagnostics_from_bursts(tttr, detectors)
            self.diagnostics[path] = diags
            self.backgrounds[path] = {n: float(d.rate_khz) for n, d in diags.items()}
        self.status = (
            f"{len(self.diagnostics)} file(s), "
            f"{len({n for b in self.backgrounds.values() for n in b})} detector(s) estimated."
        )
        self.notify("computed")

    def has_results(self) -> bool:
        """Whether an estimate has produced results."""
        return bool(self.backgrounds)

    # ── AutoForm accessors ─────────────────────────────────────────────
    def results_rows(self) -> list[dict]:
        """Per-(file, detector) background-rate rows for the results table."""
        rows = []
        for path, bg in self.backgrounds.items():
            fname = os.path.basename(path)
            for det, rate in bg.items():
                rows.append({"file": fname, "detector": str(det), "rate_khz": f"{float(rate):.3f}"})
        return rows

    def iht_series(self) -> list[dict]:
        """Inter-photon-time histogram points + fitted-tail lines, per detector."""
        series: list[dict] = []
        multi = len(self.diagnostics) > 1
        for path, det_diags in self.diagnostics.items():
            stem = os.path.basename(path)
            for det, diag in det_diags.items():
                centers = np.asarray(diag.centers, dtype=float)
                counts = np.asarray(diag.counts, dtype=float)
                if centers.size == 0:
                    continue
                color = "#{:02x}{:02x}{:02x}".format(*det_color(det))
                label = det if not multi else f"{det} · {stem}"
                nz = counts > 0
                series.append(
                    {
                        "x": centers[nz],
                        "y": counts[nz],
                        "name": label,
                        "color": color,
                        "style": "none",
                        "symbol": "o",
                    }
                )
                model = np.asarray(diag.model, dtype=float)
                m = model > 0
                if m.any():
                    series.append({"x": centers[m], "y": model[m], "color": color, "width": 2})
        return series

    def rate_rows(self) -> list[dict]:
        """Mean per-detector background rate (kHz) across files, for the bar plot."""
        agg: dict[str, list] = {}
        for det_diags in self.diagnostics.values():
            for det, diag in det_diags.items():
                agg.setdefault(det, []).append(float(diag.rate_khz))
        return [
            {"detector": det, "rate": float(np.mean(rates)), "color": det_color(det)}
            for det, rates in agg.items()
        ]


__all__ = ["BackgroundViewModel", "det_color"]
