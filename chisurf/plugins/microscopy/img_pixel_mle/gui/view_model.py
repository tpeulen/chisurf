"""Qt-free view-model for the pixel-wise FLIM MLE tool.

Holds the confocal (CLSM) + IRF file lists and analysis settings edited through
the AutoForm view (``pixel_mle.view.json``), runs the Qt-free core
(:func:`...core.pixel_mle.fit_pixel_lifetimes_from_file`) over the selected
files, and exposes the fitted lifetime map(s) for display.  No Qt imports — the
heavy :meth:`run` is driven from a background thread by the tool.

The persistent settings holder is the transport-agnostic
:class:`...api.models.PixelMleSettings` (the same dataclass the RPC backend and
CLI consume), so IRF preparation reuses ``backend.services._build_irf_vv_vh`` and
a per-file core :class:`...core.pixel_mle.PixelMleSettings` is assembled exactly
as the backend does.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.plugins.microscopy.mle_common.base import MleObserverMixin, scalar

from ..api.models import PixelMleSettings as ApiSettings

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "pixel_mle.view.json"


class PixelMleViewModel(MleObserverMixin):
    """State + logic for the pixel-wise MLE tool (no Qt)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.irf_files: list[str] = []
        self.settings = ApiSettings()
        self.status_text: str = ""
        #: Per-file :class:`...core.pixel_mle.PixelMleResult` of the last run.
        self.results: list = []
        #: Stems of the analysed files, aligned with :attr:`results`.
        self.result_names: list[str] = []
        #: Name of the result whose map is shown (in-plot channel combo).
        self.current_result_name: str = ""
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── shared-setup hook (Imaging Tools aggregator) ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt detector channels, micro-time range and polarisation corrections.

        Even routing channels are taken as parallel (∥), odd channels as
        perpendicular (⊥); the first detector's micro-time range sets the fit
        window, and its G-factor / l1 / l2 mixing corrections are carried into
        the fit (previously dropped, so the fit silently ran at g=1, l1=l2=0).
        """
        from chisurf.core.fluorescence.mle import parse_detector_setup

        setup = parse_detector_setup(payload)
        if not payload:
            return
        if setup.channels_parallel:
            self.settings.detector_chs_p = setup.channels_parallel
        if setup.channels_perpendicular:
            self.settings.detector_chs_s = setup.channels_perpendicular
        if setup.micro_range is not None:
            self.settings.micro_time_start = setup.micro_range[0]
            self.settings.micro_time_stop = setup.micro_range[1]
        if setup.g_factor is not None:
            self.settings.g_factor = setup.g_factor
        if setup.l1 is not None:
            self.settings.l1 = setup.l1
        if setup.l2 is not None:
            self.settings.l2 = setup.l2
        self.notify("setup")

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the pipeline's source TTTR as the imaging file to analyse."""
        source = (payload or {}).get("source")
        if source and str(source) not in self.files:
            self.files = [*self.files, str(source)]
            self.notify("changed")

    def apply_calibration(self, calibration: dict) -> None:
        """Adopt IRF file, background and fit window from the IRF & BG step.

        *calibration* maps detector name → ``{"irf": path(s), "bg_vv"/"bg_vh": …,
        "conv_start"/"conv_stop": …}``.  The first entry carrying an IRF is used,
        so the IRF/background are carried on rather than re-entered here.
        """
        if not calibration:
            return
        for vals in calibration.values():
            if not isinstance(vals, dict):
                continue
            irf = vals.get("irf")
            irf_files = list(irf) if isinstance(irf, (list, tuple)) else ([irf] if irf else [])
            if not irf_files:
                continue
            self.irf_files = [str(f) for f in irf_files]
            bg_vv = float(vals.get("bg_vv") or 0.0)
            bg_vh = float(vals.get("bg_vh") or 0.0)
            if bg_vv or bg_vh:
                self.settings.bg_p = bg_vv
                self.settings.bg_s = bg_vh
                self.settings.use_bg = True
            start = int(vals.get("conv_start") or 0)
            stop = int(vals.get("conv_stop") or 0)
            if stop > start:
                self.settings.micro_time_start = start
                self.settings.micro_time_stop = stop
            self.notify("setup")
            return

    # ── path-list bindings ──
    @property
    def sel_files(self) -> list:
        """CLSM imaging files to analyse (bound to the `path_list`)."""
        return list(self.files)

    @sel_files.setter
    def sel_files(self, value) -> None:
        self.files = [str(v) for v in (value or [])]

    @property
    def sel_irf_files(self) -> list:
        """IRF file(s); the first is used (bound to the `path_list`)."""
        return list(self.irf_files)

    @sel_irf_files.setter
    def sel_irf_files(self, value) -> None:
        self.irf_files = [str(v) for v in (value or [])]

    # ── channel-text bindings (space-separated ints) ──
    @staticmethod
    def _parse_channels(value) -> list[int]:
        try:
            return [int(x) for x in str(value).replace(",", " ").split()]
        except ValueError:
            logger.debug("invalid channel text: %r", value)
            return []

    @property
    def channels_parallel_text(self) -> str:
        """Parallel (∥) routing channels as a space-separated string."""
        return " ".join(str(c) for c in self.settings.detector_chs_p)

    @channels_parallel_text.setter
    def channels_parallel_text(self, value) -> None:
        self.settings.detector_chs_p = self._parse_channels(value)

    @property
    def channels_perpendicular_text(self) -> str:
        """Perpendicular (⊥) routing channels as a space-separated string."""
        return " ".join(str(c) for c in self.settings.detector_chs_s)

    @channels_perpendicular_text.setter
    def channels_perpendicular_text(self, value) -> None:
        self.settings.detector_chs_s = self._parse_channels(value)

    # ── scalar settings bindings (AutoForm value/choice/toggle sections) ──
    micro_time_start = scalar(
        "micro_time_start", int, "Fit-window start (binned micro-time channel)."
    )
    micro_time_stop = scalar(
        "micro_time_stop", int, "Fit-window stop (binned micro-time channel)."
    )
    micro_time_binning = scalar("micro_time_binning", int, "Micro-time down-binning factor.")
    irf_threshold = scalar(
        "irf_threshold", float, "IRF threshold fraction (bins below are zeroed)."
    )
    shift_sp = scalar("shift_sp", float, "Parallel IRF sub-bin shift.")
    shift_ss = scalar("shift_ss", float, "Perpendicular IRF sub-bin shift.")
    min_photons = scalar("min_photons", int, "Minimum photons per pixel to fit.")
    tau = scalar("tau", float, "Initial lifetime (ns).")
    gamma = scalar("gamma", float, "Initial scatter fraction.")
    r0 = scalar("r0", float, "Initial fundamental anisotropy.")
    rho = scalar("rho", float, "Initial rotational correlation time (ns).")
    fix_tau = scalar("fix_tau", bool, "Fix the lifetime.")
    fix_gamma = scalar("fix_gamma", bool, "Fix the scatter fraction.")
    fix_r0 = scalar("fix_r0", bool, "Fix the fundamental anisotropy.")
    fix_rho = scalar("fix_rho", bool, "Fix the rotational correlation time.")
    twoi_star = scalar("twoi_star", bool, "Optimise P+2S (2I*).")
    bifl_scatter = scalar("bifl_scatter", bool, "Soft BIFL scatter correction.")
    use_bg = scalar("use_bg", bool, "Subtract a flat background.")
    bg_p = scalar("bg_p", float, "Parallel background counts (fit window).")
    bg_s = scalar("bg_s", float, "Perpendicular background counts (fit window).")

    @property
    def engine(self) -> str:
        """Histogram-extraction engine ("auto"/"fast"/"loop")."""
        return str(self.settings.engine)

    @engine.setter
    def engine(self, value) -> None:
        self.settings.engine = str(value)

    @property
    def n_workers(self) -> int:
        """Fit worker threads (0 = auto = cpu-1; 1 = serial)."""
        return int(self.settings.n_workers or 0)

    @n_workers.setter
    def n_workers(self, value) -> None:
        n = int(value)
        self.settings.n_workers = None if n <= 0 else n

    # ── result map accessors (AutoForm image dock) ──
    def _current_index(self) -> int:
        """Index into :attr:`results` for the selected result name."""
        if not self.results:
            return 0
        if self.current_result_name in self.result_names:
            return self.result_names.index(self.current_result_name)
        return 0

    def result_file_names(self) -> list[str]:
        """File stems available in the in-plot result selector."""
        return list(self.result_names)

    def select_result(self, name) -> None:
        """Adopt *name* as the shown result (in-plot channel-combo callback)."""
        self.current_result_name = str(name)
        self.notify("select")

    def tau_map_image(self):
        """Fitted lifetime map of the current result as a ``(frame, y, x)`` stack."""
        if not self.results:
            return None
        result = self.results[self._current_index()]
        arr = np.asarray(result.tau, dtype=np.float32)
        # NaN/0 (unfitted) pixels render as the colormap floor; keep as-is.
        return arr

    def info_html(self) -> str:
        """Status / summary text shown above the results."""
        if self.status_text:
            return f"<i>{self.status_text}</i>"
        if not self.results:
            return (
                "<i>Add confocal (CLSM) TTTR image file(s) and an IRF, set the "
                "parallel/perpendicular channels and fit window, then press "
                "<b>Run</b>. Each pixel is fitted with a single-lifetime "
                "Poisson-MLE (Fit23) and the τ map is shown.</i>"
            )
        lines = []
        total_fit = 0
        for name, result in zip(self.result_names, self.results):
            taus = result.dataframe["tau"].to_numpy()
            taus = taus[np.isfinite(taus)]
            median = float(np.median(taus)) if taus.size else float("nan")
            total_fit += int(result.n_pixels_fit)
            lines.append(
                f"<b>{name}</b>: {result.n_pixels_fit} px fit, median &tau; = {median:.2f} ns"
            )
        head = f"<b>{len(self.results)}</b> file(s), <b>{total_fit}</b> pixels fitted."
        return head + "<br>" + "<br>".join(lines)

    # ── the run action ──
    def request_run(self) -> None:
        """Button action: ask the host to start the analysis on a worker thread."""
        self.notify("start_run")

    def can_run(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether a run is possible."""
        if not self.files:
            return False, "No imaging files selected."
        if not self.irf_files:
            return False, "No IRF file selected."
        if int(self.settings.micro_time_stop) <= int(self.settings.micro_time_start):
            return False, "Empty micro-time fit window."
        if not self.settings.detector_chs_p or not self.settings.detector_chs_s:
            return False, "Both parallel and perpendicular channels are required."
        return True, ""

    def run(self) -> None:
        """Analyse every selected file (BLOCKING — call from a worker thread).

        Builds a prepared VV/VH IRF from the first IRF file, fits each imaging
        file through the Qt-free core, writes a per-file ``<stem>_pixel_mle.csv``
        next to it (or in the file's directory), and keeps the results + τ maps
        for display.
        """
        from ..backend.services import _build_irf_vv_vh
        from ..core import PixelMleSettings, fit_pixel_lifetimes_from_file

        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return

        s = self.settings
        try:
            irf = _build_irf_vv_vh(self.irf_files[0], s)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            logger.debug("IRF preparation failed", exc_info=True)
            self.status_text = f"IRF error: {exc}"
            self.notify("done")
            return

        window = int(s.micro_time_stop) - int(s.micro_time_start)
        background = None
        if s.use_bg and window > 0:
            background = np.concatenate(
                [
                    np.full(window, s.bg_p / window, dtype=np.float64),
                    np.full(window, s.bg_s / window, dtype=np.float64),
                ]
            )

        self.results = []
        self.result_names = []
        for i, path in enumerate(self.files):
            stem = pathlib.Path(path).stem
            self.status_text = f"Fitting {stem} ({i + 1}/{len(self.files)})…"
            self.notify("progress")
            try:
                period_ns = self._period_ns(path, s.micro_time_binning)
                core_settings = PixelMleSettings(
                    channels_parallel=list(s.detector_chs_p),
                    channels_perpendicular=list(s.detector_chs_s),
                    irf=irf,
                    period=period_ns,
                    background=background,
                    binning_factor=s.micro_time_binning,
                    micro_time_start=s.micro_time_start,
                    micro_time_stop=s.micro_time_stop,
                    g_factor=s.g_factor,
                    l1=s.l1,
                    l2=s.l2,
                    min_photons=s.min_photons,
                    tau=s.tau,
                    gamma=s.gamma,
                    r0=s.r0,
                    rho=s.rho,
                    fix_tau=s.fix_tau,
                    fix_gamma=s.fix_gamma,
                    fix_r0=s.fix_r0,
                    fix_rho=s.fix_rho,
                    convolution_stop=-1,
                    p2s_twoIstar=s.twoi_star,
                    soft_bifl_scatter=s.bifl_scatter,
                    engine=s.engine,
                    n_workers=s.n_workers,
                )
                result = fit_pixel_lifetimes_from_file(path, core_settings)
            except Exception as exc:  # noqa: BLE001 - surfaced in the status line
                logger.debug("pixel MLE failed for %s", path, exc_info=True)
                self.status_text = f"{stem}: {exc}"
                continue
            self.results.append(result)
            self.result_names.append(stem)
            self._write_csv(path, result.dataframe)

        if self.result_names and self.current_result_name not in self.result_names:
            self.current_result_name = self.result_names[0]
        self.status_text = ""
        self.notify("done")

    @staticmethod
    def _period_ns(path: str, binning: int) -> float:
        """Excitation period (ns) from a TTTR header."""
        import tttrlib

        # Keep the TTTR alive: its ``header`` references freed C++ memory once the
        # owning TTTR is collected (``tttrlib.TTTR(path).header`` would dangle).
        tttr = tttrlib.TTTR(path)
        header = tttr.header
        return header.number_of_micro_time_channels * header.micro_time_resolution * 1e9

    @staticmethod
    def _write_csv(path: str, dataframe) -> None:
        """Write one file's per-pixel table next to it as ``<stem>_pixel_mle.csv``."""
        if dataframe is None or dataframe.empty:
            return
        out_dir = os.path.dirname(path) or "."
        stem = pathlib.Path(path).stem
        try:
            dataframe.to_csv(os.path.join(out_dir, f"{stem}_pixel_mle.csv"), index=False)
        except Exception:
            logger.debug("CSV export failed for %s", path, exc_info=True)


__all__ = ["PixelMleViewModel"]
