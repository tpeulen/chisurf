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

    def __init__(
        self,
        show_channel_definition: bool = True,
        show_files: bool = True,
    ) -> None:
        self.show_channel_definition = bool(show_channel_definition)
        #: Whether the tool picks its own files. A workflow that has already
        #: chosen the measurements hides the dock and pushes them in.
        self.show_files = bool(show_files)
        self.files: list[str] = []

        # ── the fit, and what it is fitted to ──────────────────────────
        #: Where the background tail starts, as a fraction of the longest
        #: inter-photon time. This is *the* judgement call in a background
        #: estimate — too small and bursts are fitted as background, too large
        #: and there is nothing left to fit — and it was a hidden default.
        self.tail_fraction: float = 0.8
        #: The fit window in **milliseconds**, which is what the fit actually
        #: uses once a measurement has been read. :attr:`tail_fraction` only
        #: seeds it (``fit_from = fraction × longest inter-photon time``); after
        #: that the window is the state, because it is what the user drags on
        #: the plot and what has a physical meaning independent of how long the
        #: longest gap in this particular file happened to be.
        #:
        #: The *upper* edge is the half the fraction rule never had. The far
        #: tail is bins holding one count each: it stretches the fit over a
        #: decade that carries almost no information, and on a short
        #: measurement it visibly pulls the line off the points.
        self.fit_from_ms: float = 0.0
        self.fit_to_ms: float = 0.0
        #: Longest inter-photon time in the loaded files, in ms. The scale the
        #: window is seeded and clamped against.
        self.max_dt_ms: float = 0.0
        #: Inter-photon-time histogram bin width.
        self.binsize_ms: float = 0.1
        #: Bins below this count are ignored by the tail fit.
        self.min_counts: int = 1
        #: ``{path: {detector: dt_ms}}`` from the last read, so moving the
        #: slider re-fits instead of re-reading the measurement — a 45 MB file
        #: per tick would make the slider unusable.
        self._interphoton: dict[str, dict[str, np.ndarray]] = {}
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
        hidden = set()
        if not self.show_channel_definition:
            hidden.add("Channel Definition")  # the shell supplies the channels
        if not self.show_files:
            hidden.add("Files")               # the shell supplies the files
        if not hidden:
            return spec
        import dataclasses

        root = spec.sections[0]
        kept = tuple(s for s in root.sections if s.title not in hidden)
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
        self._interphoton.clear()
        for path in self.files:
            try:
                tttr = tttrlib.TTTR(path)
            except Exception as exc:
                logger.warning("background: could not read %s: %s", path, exc)
                continue
            scale = float(
                getattr(tttr.header, "macro_time_resolution", 1.0)) * 1000.0
            self._interphoton[path] = {
                name: _burst.background._detector_interphoton_times(
                    tttr, info, scale)
                for name, info in detectors.items()
            }
        self._seed_fit_window()
        self.refit()
        self._write_containers()
        self.notify("computed")

    def _seed_fit_window(self) -> None:
        """Seed the fit window from the data, the first time only.

        Re-estimating with more files must not silently move a window the user
        placed by hand — that would change the rates without anything having
        been touched — so an existing window is kept and only re-clamped to the
        new scale.
        """
        spans = [
            float(np.max(dt)) for per_detector in self._interphoton.values()
            for dt in per_detector.values()
            if np.asarray(dt).size and np.isfinite(np.max(dt))
        ]
        if not spans:
            return
        self.max_dt_ms = max(spans)
        if self.fit_from_ms <= 0.0 or self.fit_to_ms <= self.fit_from_ms:
            self.fit_from_ms = float(self.tail_fraction) * self.max_dt_ms
            self.fit_to_ms = self.max_dt_ms
        else:
            self.fit_to_ms = min(self.fit_to_ms, self.max_dt_ms)

    def fit_range(self) -> tuple[float, float] | None:
        """The fit window in ms, or ``None`` while the fraction rule still holds.

        ``None`` before the first estimate, so a headless caller that never
        touches the window gets exactly the behaviour it had before.
        """
        low, high = float(self.fit_from_ms), float(self.fit_to_ms)
        if low <= 0.0 or high <= low:
            return None
        return low, high

    def refit(self) -> None:
        """Re-fit the cached inter-photon times with the current settings.

        Separate from :meth:`estimate` because reading the photons is what costs
        — seconds per measurement — while the fit is a histogram and a line.
        Moving the tail slider therefore re-fits at once instead of re-reading,
        which is the only way a slider over this parameter is usable at all.
        """
        from chisurf.core.fluorescence.burst.background import (
            interphoton_time_diagnostics,
        )

        self.backgrounds.clear()
        self.diagnostics.clear()
        for path, per_detector in self._interphoton.items():
            diags = {
                name: interphoton_time_diagnostics(
                    dt_ms,
                    binsize_ms=float(self.binsize_ms),
                    tail_fraction=float(self.tail_fraction),
                    min_counts=int(self.min_counts),
                    tail_range_ms=self.fit_range(),
                )
                for name, dt_ms in per_detector.items()
            }
            self.diagnostics[path] = diags
            self.backgrounds[path] = {n: float(d.rate_khz) for n, d in diags.items()}
        window = self.fit_range()
        where = (
            f"tail from {self.tail_fraction:.0%}" if window is None else
            f"fit window {window[0]:.3g}\u2013{window[1]:.3g} ms"
        )
        self.status = (
            f"{len(self.diagnostics)} file(s), "
            f"{len({n for b in self.backgrounds.values() for n in b})} detector(s) "
            f"estimated; {where}."
        )

    def update(self) -> None:
        """AutoForm hook: a bound field changed.

        A fit setting re-fits immediately when there is something to re-fit; the
        file list only notifies.
        """
        if self._interphoton:
            self.refit()
            self.notify("computed")
        else:
            self.notify("files")

    def _write_containers(self) -> None:
        """Record each file's background rates beside its photons.

        A background rate is a property *of a measurement*, and until now it
        lived only in this window: every later step that needs one — an MLE
        fit, a burst search, an accurate-FRET correction — takes it as a number
        the user types in again, with nothing recording that the two came from
        the same estimate.

        One row per detector, at `channel` grain, plus the inter-photon-time
        histogram the rate was fitted from, so the estimate can be checked
        rather than believed.

        A failure here must not lose the estimate on screen.
        """
        from chisurf.core.datastore import store_from_arrays
        from chisurf.core.fio.fluorescence.burst_container import (
            write_burst_artifact,
        )

        for path, diags in self.diagnostics.items():
            if not diags:
                continue
            names = list(diags)
            try:
                write_burst_artifact(
                    path,
                    store_from_arrays({
                        "Detector": np.array(names, dtype=object),
                        "Rate": np.array(
                            [float(diags[n].rate_khz) for n in names], dtype=float
                        ),
                        "Amplitude": np.array(
                            [float(diags[n].amplitude) for n in names], dtype=float
                        ),
                    }),
                    name="background",
                    artifact_kind="background_data",
                    operation_type="background_correction",
                    row_grain="channel",
                    parameters=self._channels(),
                    derived_from=(),
                    units={"Rate": "kilohertz", "Amplitude": "counts"},
                )
                for name in names:
                    diag = diags[name]
                    if not len(diag.centers):
                        continue
                    write_burst_artifact(
                        path,
                        store_from_arrays({
                            "Interphoton Time": np.asarray(diag.centers, dtype=float),
                            "Counts": np.asarray(diag.counts, dtype=float),
                            "Model": np.asarray(diag.model, dtype=float),
                            "In Tail": np.asarray(diag.tail_mask, dtype=bool),
                        }),
                        name=f"background histogram {name}",
                        artifact_kind="background_data",
                        operation_type="background_correction",
                        row_grain="curve_point",
                        parameters=self._channels(),
                        derived_from="background",
                        units={
                            "Interphoton Time": "milliseconds",
                            "Counts": "counts", "Model": "counts",
                        },
                    )
            except Exception:
                logger.debug("could not write the container for %s", path,
                             exc_info=True)

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
                # Only where the model predicts something observable. It is an
                # exponential drawn over the whole range, so a steep fit reaches
                # 1e-15 counts at the far end -- and a log y axis then autoscales
                # over twenty decades, squashing the data into the top eighth of
                # the plot. Half a count is the floor: nothing below it can be
                # seen in a histogram of counts.
                m = model >= 0.5
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
