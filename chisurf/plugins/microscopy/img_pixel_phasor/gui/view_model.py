"""Qt-free view-model backing the per-pixel phasor-FLIM imaging tool.

Computes phasor (g, s) per pixel for **every** detector window (via tttrlib's
built-in ``get_phasor``, raw + optional IRF reference) and adds them to the
standard imaging HDF5.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

from chisurf.core.roi import RegionCollection
from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

_VIEW_JSON = pathlib.Path(__file__).parent / "phasor.view.json"


class PhasorImgViewModel(ImagingMapViewModel):
    """State + logic for the interactive phasor-FLIM imaging tool (no Qt)."""

    HDF5_ACTION_LABEL = "➕ Add phasor to HDF5"
    WINDOW_KIND = "phasor"
    OPERATION_TYPE = "phasor_analysis"
    #: g and s are the coordinates of a point on the universal circle, so they
    #: are genuinely dimensionless -- a claim, not an absence.
    COLUMN_UNITS = {"g": "dimensionless", "s": "dimensionless",
                    "tau_phi": "nanoseconds", "tau_m": "nanoseconds"}
    #: Phasor-plot extent (data coords). Widened past the universal circle
    #: (g∈[0,1], s∈[0,0.5]) so noisy pixels near the edges are not clipped.
    PHASOR_G_RANGE = (-0.1, 1.1)
    PHASOR_S_RANGE = (-0.05, 0.7)

    def __init__(self) -> None:
        super().__init__(_VIEW_JSON)
        # phasor-specific settings (bound by the view.json `value`s)
        self.n_ph_min: int = 3
        self.frequency: float = -1.0
        self.colormap = "viridis"
        #: Phasor cursors — the shared named region list, on the (g, s) plane.
        #: A cursor is a region like any other: drawn, inverted, combined, saved.
        self.cursors = RegionCollection(combine="or", name="cursor")

    def _extra_signature(self) -> tuple:
        """Phasor settings that change the result (for recompute dedup)."""
        return (int(self.n_ph_min), float(self.frequency))

    def _window_params(self) -> dict:
        """Return phasor worker params (IRF comes per-detector from the IRF & BG step)."""
        return {"frequency": float(self.frequency), "n_ph_min": int(self.n_ph_min)}

    # ── image accessors ──
    def g_map(self):
        """Return the phasor g map of the displayed window."""
        return self._disp("g")

    def s_map(self):
        """Return the phasor s map of the displayed window."""
        return self._disp("s")

    # ── per-frame movie accessors (unstacked phasor) ──
    def _phasor_frames(self):
        """Return per-frame phasor ``g``/``s`` stacks for the window.

        Prefers the stacks produced by the compute **worker process** (stashed on
        ``_by_window`` under ``g_frames``/``s_frames``) so the movie never runs
        ``get_phasor`` on the UI thread; falls back to a lazily-built, memoized
        CLSM call for standalone use with no compute yet.
        """
        if not self.filename or not self._by_window:
            # Gate on a completed compute so a pre-Run refresh never triggers a
            # synchronous CLSM fill / get_phasor on the UI thread (warmed in bg).
            return None
        stashed = self._by_window.get(self.display_window) or {}
        if stashed.get("g_frames") is not None and stashed.get("s_frames") is not None:
            return {"g": stashed["g_frames"], "s": stashed["s_frames"]}
        win = self._windows().get(self.display_window)
        if win is None:
            return None
        irf_files = list(win.get("irf") or [])
        key = (
            self.filename, self.display_window, float(self.frequency),
            int(self.n_ph_min), tuple(irf_files),
        )
        if getattr(self, "_pf_key", None) == key and getattr(self, "_pf_cache", None) is not None:
            return self._pf_cache
        try:
            from chisurf.core.fluorescence.imaging import (
                cached_clsm,
                get_tttr,
                phasor_frames,
            )

            tttr = get_tttr(self.filename)
            clsm = cached_clsm(
                self.filename,
                list(win.get("chs", [0]) or [0]),
                list(win.get("micro_time_ranges") or []),
            )
            tttr_irf = get_tttr(irf_files[0]) if irf_files else None
            result = phasor_frames(
                clsm, tttr, frequency=float(self.frequency),
                tttr_irf=tttr_irf, n_ph_min=int(self.n_ph_min),
            )
        except Exception:
            return None
        self._pf_key, self._pf_cache = key, result
        return result

    def g_frames(self):
        """Return the per-frame phasor-g stack ``(n_frames, y, x)`` (movie source)."""
        frames = self._phasor_frames()
        return None if frames is None else frames["g"]

    def s_frames(self):
        """Return the per-frame phasor-s stack ``(n_frames, y, x)`` (movie source)."""
        frames = self._phasor_frames()
        return None if frames is None else frames["s"]

    def phasor_histogram_frames(self, bins: int = 160) -> Any:
        """Return a per-frame stack of phasor density histograms ``(n_frames, bins, bins)``.

        The movie source for the phasor *plot*: one ``log(1+count)`` density per
        acquisition frame, built from the same unstacked per-frame phasors as
        :meth:`g_frames`. Discriminated pixels come back as ``(0, 0)`` and are
        excluded.

        Axes are ``(frame, s, g)`` — row-major, as the plotting layer draws
        images — so ``g`` runs horizontally and ``s`` vertically.
        """
        win = self._windows().get(self.display_window) or {}
        sig = (
            self.filename, self.display_window, float(self.frequency),
            int(self.n_ph_min), tuple(win.get("irf") or []), int(bins),
        )

        def build():
            frames = self._phasor_frames()
            if frames is None:
                return None
            g_st, s_st = frames["g"], frames["s"]
            n = int(g_st.shape[0])
            out = np.empty((n, bins, bins), dtype=float)
            rng = [list(self.PHASOR_G_RANGE), list(self.PHASOR_S_RANGE)]
            for f in range(n):
                g, s = g_st[f], s_st[f]
                valid = np.isfinite(g) & np.isfinite(s) & ~((g == 0.0) & (s == 0.0))
                hist, _, _ = np.histogram2d(g[valid].ravel(), s[valid].ravel(), bins=bins, range=rng)
                # histogram2d puts g on axis 0; the image is drawn row-major, so
                # the transpose is what puts g on the horizontal axis.
                out[f] = np.log1p(hist.T)
            return out

        return self._cached_stack("phasor_histogram_frames", sig, build)

    def _warm_movie_cache(self) -> None:
        """Warm the raw-frame, per-frame g/s and phasor-plot movie stacks (bg thread)."""
        super()._warm_movie_cache()
        self.g_frames()
        self.s_frames()
        self.phasor_histogram_frames()

    def phasor_histogram_map(self, bins: int = 160) -> Any:
        """Return a 2-D density histogram of the displayed window's (g, s) cloud.

        Axis 0 is ``s`` and axis 1 is ``g`` — row-major, the convention the
        plotting layer draws images in — so ``g`` runs horizontally and ``s``
        vertically. Values are ``log(1+count)``. A 2-D histogram reads far better
        than a scatter for the dense per-pixel phasor cloud; the phasor section
        overlays the universal semicircle and calibrates the axes.

        ``np.histogram2d`` puts the first argument on axis 0, so the transpose
        below is not cosmetic: without it the cloud is drawn mirrored about the
        diagonal, which for phasor data means every lifetime reads wrong.
        """
        g, s, n = self._disp("g"), self._disp("s"), self._disp("n_photons")
        if g is None or s is None:
            return None
        mask = (n > 0) if n is not None else np.ones_like(g, dtype=bool)
        gg, ss = g[mask].ravel(), s[mask].ravel()
        valid = np.isfinite(gg) & np.isfinite(ss)
        hist, _, _ = np.histogram2d(
            gg[valid], ss[valid], bins=bins,
            range=[list(self.PHASOR_G_RANGE), list(self.PHASOR_S_RANGE)],
        )
        return np.log1p(hist.T)

    # ── phasor cursors ──
    def cursor_extent(self) -> tuple:
        """Where a newly drawn cursor is placed: the phasor plot's own box."""
        return (*self.PHASOR_G_RANGE, *self.PHASOR_S_RANGE)

    def cursor_mask(self):
        """Return the pixels the combined cursor selects, as a boolean map.

        The phasor plane and the image are two views of the same pixels, which
        is the whole point of a cursor: a cluster picked out on ``(g, s)``
        answers *which pixels* have that lifetime. Nothing enabled means every
        pixel, not none.

        Returns
        -------
        numpy.ndarray or None
            Boolean map with the shape of the ``g`` map, or ``None`` when there
            is no phasor result yet.
        """
        g, s = self._disp("g"), self._disp("s")
        if g is None or s is None:
            return None
        combined = self.cursors.combined()
        if combined is None:
            return np.ones_like(g, dtype=bool)
        from ..analysis import mask_from_cursor

        return mask_from_cursor(np.asarray(g), np.asarray(s), combined)

    def cursor_summary(self) -> str:
        """One line on what the cursors select, for the panel."""
        mask = self.cursor_mask()
        if mask is None:
            return ""
        n = self._disp("n_photons")
        valid = np.isfinite(np.asarray(self._disp("g")))
        if n is not None:
            valid &= np.asarray(n) > 0
        total = int(valid.sum())
        picked = int((mask & valid).sum())
        if not total:
            return ""
        return f"{picked} of {total} px ({100.0 * picked / total:.1f} %)"

    def masked_intensity_map(self):
        """Intensity of the pixels the cursors select, zero elsewhere.

        This is what makes a cursor worth drawing: the image, gated by the
        lifetime cluster picked out on the phasor plane.
        """
        intensity = self._disp("n_photons")
        if intensity is None:
            return None
        mask = self.cursor_mask()
        if mask is None:
            return np.asarray(intensity)
        return np.where(mask, np.asarray(intensity), 0.0)

    def notify_cursors(self) -> None:
        """Tell the views the cursor set changed."""
        self.notify("cursor")
