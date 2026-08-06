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

from chisurf.core.datastore import write_csv_table
import numpy as np

from chisurf.core.fluorescence.mle.fit2x import parameter_names_of, Fit2xModel
from chisurf.plugins.microscopy.mle_common.base import MleObserverMixin, scalar

from ..api.models import PixelMleSettings as ApiSettings

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "pixel_mle.view.json"

#: Selectable fit2x estimators and their combo labels.
_FIT_MODELS = ("fit23", "fit24", "fit25")
_FIT_MODEL_LABELS = (
    "Single lifetime + anisotropy (fit23)",
    "Bi-exponential (fit24)",
    "Lifetime selection (fit25)",
)

#: Per-parameter display metadata (initial value, bounds, label) keyed by the
#: registry free-parameter name. ``fixed`` is *not* here — it is model-specific
#: (fit25 fixes its four candidate lifetimes, fit24 frees tau1/tau2), so it lives
#: in :data:`_MODEL_FIXED_DEFAULT`.
_PARAM_META = {
    "tau":    {"label": "τ (ns)",  "default": 2.0,  "min": 0.0, "max": 100.0},
    "tau1":   {"label": "τ1 (ns)", "default": 2.0,  "min": 0.0, "max": 100.0},
    "tau2":   {"label": "τ2 (ns)", "default": 0.5,  "min": 0.0, "max": 100.0},
    "tau3":   {"label": "τ3 (ns)", "default": 4.0,  "min": 0.0, "max": 100.0},
    "tau4":   {"label": "τ4 (ns)", "default": 8.0,  "min": 0.0, "max": 100.0},
    "gamma":  {"label": "γ",       "default": 0.0,  "min": 0.0, "max": 1.0},
    "A2":     {"label": "A2",      "default": 0.5,  "min": 0.0, "max": 1.0},
    "offset": {"label": "offset",  "default": 0.0,  "min": 0.0, "max": 1e6},
    "r0":     {"label": "r0",      "default": 0.38, "min": 0.0, "max": 0.4},
    "rho":    {"label": "ρ (ns)",  "default": 1.0,  "min": 0.0, "max": 1000.0},
}

#: Default fixed mask per model (1 = fixed). fit23 frees τ only; fit24 frees the
#: two lifetimes + their fraction; fit25 fixes all four candidate lifetimes (it
#: *selects* the best-describing one) and γ.
_MODEL_FIXED_DEFAULT = {
    "fit23": [0, 1, 1, 1],
    "fit24": [0, 1, 0, 0, 1],
    "fit25": [1, 1, 1, 1, 1],
}

#: Widest free-parameter vector across the offered models (fit24/fit25 → 5).
_MAX_SLOTS = 5


class PixelMleViewModel(MleObserverMixin):
    """State + logic for the pixel-wise MLE tool (no Qt)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.irf_files: list[str] = []
        self.settings = ApiSettings()
        #: Selected fit2x estimator and per-model (start-vector, fixed-mask) state.
        self._fit_model: str = "fit23"
        self._model_params: dict[str, tuple[list[float], list[int]]] = {}
        self.status_text: str = ""
        #: Per-file :class:`...core.pixel_mle.PixelMleResult` of the last run.
        self.results: list = []
        #: Stems of the analysed files, aligned with :attr:`results`.
        self.result_names: list[str] = []
        #: Name of the result whose map is shown (in-plot channel combo).
        self.current_result_name: str = ""
        #: Path of a stored region confining the fit ("" = the whole frame).
        self._roi_path: str = ""
        #: The loaded region itself (:class:`chisurf.core.roi.ROI` or ``None``).
        self.roi = None
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec, injecting the model-aware fit editor.

        The base layout comes from the authored ``pixel_mle.view.json``; the fit
        section is generated per selected model (a model combo + one value/fix
        row per registry free parameter), so switching model rebuilds the editor
        to match the estimator. Parsing a plain dict keeps the JSON the single
        source for everything else.
        """
        import json

        from chisurf.core.dataspec import load_view_spec

        spec = json.loads(_VIEW_JSON.read_text())
        panel = self._analysis_panel(spec)
        if panel is not None:
            rows = panel.setdefault("sections", [])
            # Insert the model combo + parameter panel just before "IRF
            # preparation" (falls back to appending if the anchor is absent).
            at = next(
                (i for i, s in enumerate(rows)
                 if s.get("type") == "panel" and str(s.get("title", "")).startswith("IRF")),
                len(rows),
            )
            rows[at:at] = [self._fit_model_choice_dict(), self._fit_param_panel_dict()]
        return load_view_spec(spec)

    @staticmethod
    def _analysis_panel(spec: dict):
        """Return the authored "Analysis" panel dict inside the view spec (or None)."""
        stack = list(spec.get("sections", []))
        while stack:
            s = stack.pop()
            if s.get("type") == "panel" and s.get("title") == "Analysis":
                return s
            stack.extend(s.get("sections", []) or [])
        return None

    def _fit_model_choice_dict(self) -> dict:
        """Build the fit-model combo section (a ``choice`` bound to ``fit_model``)."""
        return {
            "type": "choice", "attr": "fit_model", "call": "set_fit_model",
            "label": "Fit model", "options": list(_FIT_MODELS),
            "labels": list(_FIT_MODEL_LABELS),
            "description": "Per-pixel fit2x estimator. fit23 = one lifetime + "
                           "anisotropy; fit24 = bi-exponential; fit25 = pick the "
                           "best of four fixed lifetimes. The τ map is x[0] for "
                           "every model.",
        }

    def _fit_param_panel_dict(self) -> dict:
        """Build a value/fix row per free parameter of the selected model."""
        names = parameter_names_of(Fit2xModel(self._fit_model))
        sections = []
        for i, nm in enumerate(names):
            meta = _PARAM_META.get(nm, {})
            sections.append({
                "type": "value", "attr": f"p{i}_value", "kind": "float",
                "label": meta.get("label", nm), "decimals": 3,
                "minimum": float(meta.get("min", 0.0)),
                "maximum": float(meta.get("max", 1e6)),
                "description": f"Initial value of {nm}.",
            })
            sections.append({
                "type": "toggle", "attr": f"p{i}_fix", "label": "fix",
                "description": f"Hold {nm} fixed during the fit.",
            })
        return {
            "type": "panel", "title": f"Fit parameters ({self._fit_model})",
            "n_col": 2, "collapsed": False, "sections": sections,
        }

    # ── fit-model selection ──
    @property
    def fit_model(self) -> str:
        """The selected fit2x estimator (``"fit23"``/``"fit24"``/``"fit25"``)."""
        return self._fit_model

    @fit_model.setter
    def fit_model(self, value) -> None:
        value = str(value)
        self._fit_model = value if value in _FIT_MODELS else "fit23"

    def set_fit_model(self, value) -> None:
        """Combo callback: adopt *value* and rebuild the editor for its params."""
        self.fit_model = value
        self.notify("rebuild")

    def _ensure_model_params(self, model: str) -> tuple[list[float], list[int]]:
        """Return the (start-vector, fixed-mask) lists for *model*, seeded on first use."""
        if model not in self._model_params:
            names = parameter_names_of(Fit2xModel(model))
            x0 = [float(_PARAM_META.get(n, {}).get("default", 1.0)) for n in names]
            fx = list(_MODEL_FIXED_DEFAULT.get(model, [0] * len(names)))
            if len(fx) != len(names):
                fx = [0] * len(names)
            self._model_params[model] = (x0, fx)
        return self._model_params[model]

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

    @property
    def roi_path(self) -> str:
        """Path of the region the fit is confined to (empty = whole frame)."""
        return self._roi_path

    @roi_path.setter
    def roi_path(self, value) -> None:
        """Load a stored region, or clear it when the path is empty.

        Reads whatever :mod:`chisurf.core.roi.io` reads — the native JSON, a
        Cellpose segmentation, a label image, a binary mask — so a region drawn
        in CLSM Draw and saved there restricts the fit here. Several regions in
        one file are combined into their union.
        """
        path = str(value or "")
        self._roi_path = path
        if not path:
            self.roi = None
            self.notify("roi")
            return
        from chisurf.core.roi.io import load_regions
        from chisurf.core.roi.roi import union_of

        try:
            regions = load_regions(path)
            self.roi = union_of(regions)
            self.status_text = f"Region loaded: {len(regions)} region(s) from {path}"
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            logger.debug("could not read region %s", path, exc_info=True)
            self.roi = None
            self.status_text = f"Could not read region: {exc}"
        self.notify("roi")
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
                "parallel/perpendicular channels and fit window, pick a fit "
                "model, then press <b>Run</b>. Each pixel is fitted by "
                "Poisson-MLE and the τ map is shown.</i>"
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
                x0, fixed = self._ensure_model_params(self._fit_model)
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
                    roi=self.roi,
                    fit_model=self._fit_model,
                    initial_values=list(x0),
                    fixed_flags=list(fixed),
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
            write_csv_table(os.path.join(out_dir, f"{stem}_pixel_mle.csv"), dataframe, delimiter=",")
        except Exception:
            logger.debug("CSV export failed for %s", path, exc_info=True)


def _slot_value_property(i: int):
    """Make a float property bound to slot *i* of the active model's start vector."""
    def getter(self: PixelMleViewModel) -> float:
        x0, _ = self._ensure_model_params(self._fit_model)
        return float(x0[i]) if i < len(x0) else 0.0

    def setter(self: PixelMleViewModel, value) -> None:
        x0, _ = self._ensure_model_params(self._fit_model)
        if i < len(x0):
            x0[i] = float(value)

    return property(getter, setter)


def _slot_fix_property(i: int):
    """Make a bool property bound to slot *i* of the active model's fixed mask."""
    def getter(self: PixelMleViewModel) -> bool:
        _, fx = self._ensure_model_params(self._fit_model)
        return bool(fx[i]) if i < len(fx) else False

    def setter(self: PixelMleViewModel, value) -> None:
        _, fx = self._ensure_model_params(self._fit_model)
        if i < len(fx):
            fx[i] = int(bool(value))

    return property(getter, setter)


# Static, model-independent binding slots (p0…p4). ``view_spec`` emits only as
# many rows as the active model has free parameters; each row's ``attr`` (e.g.
# ``p2_value``/``p2_fix``) reads/writes the corresponding slot of that model's
# start vector / fixed mask via these properties.
for _slot in range(_MAX_SLOTS):
    setattr(PixelMleViewModel, f"p{_slot}_value", _slot_value_property(_slot))
    setattr(PixelMleViewModel, f"p{_slot}_fix", _slot_fix_property(_slot))


__all__ = ["PixelMleViewModel"]
