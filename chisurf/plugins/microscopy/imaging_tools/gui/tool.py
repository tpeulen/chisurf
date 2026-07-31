"""ImagingToolsTool — unified imaging panel using NavigationPanelTool.

A single **"Setup"** panel (the detector/PIE-window wizard) is the one place a
user defines channels for the whole imaging workflow.  Its definition is
published to the central ``detector_setups.*`` RPC store and pulled by every
sub-tool through a uniform ``apply_setup_settings(payload)`` adapter — so the
detector wizard is no longer duplicated across the embedded tools.

Each sub-tool still works **standalone** (with its own embedded wizard) when
launched on its own; the embedded copy is only suppressed here, where the shared
Setup panel feeds it via RPC.

Panels (lazy-loaded via factory functions):

  1. Setup            — SetupChannelDefinitionWidget (shared, publishes via RPC)
  2. Browser          — TTTRImageBrowserTool
  3. Pixel-wise MLE   — ImgPixelMleTool (embedded)
  4. Molecule-wise MLE — SmImageMleTool (embedded)
  5. CLSM Draw        — CLSMPixelSelect
  ─────────────────── (separator)
  6. PSF Determination — PsfDeterminationTool
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.navigation import NavigationPanelTool

from .client import DetectorSetupClient

logger = logging.getLogger(__name__)


class _PipelineSignals(QtCore.QObject):
    """Cross-thread signals for the background pipeline compute."""

    progress = QtCore.Signal(str, float, str)  # role, fraction, text
    model_done = QtCore.Signal(str)  # role (results ready for that step)
    all_done = QtCore.Signal()


class _PipelineComputeTask(QtCore.QRunnable):
    """Compute each step's view-model off the UI thread.

    Runs the steps sequentially so the shared CLSM cache (in the worker process)
    is built once and every step's results are ready before the user navigates to
    it. The heavy TTTR read + CLSM fills hold the GIL, so each ``compute`` routes
    them to a worker process (see ``compute_windows``); this QThread only waits on
    the result, leaving the UI fully responsive throughout the pipeline.
    """

    def __init__(self, jobs, signals: _PipelineSignals):
        super().__init__()
        self._jobs = jobs  # list of (role, model)
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: N802 (Qt override)
        for role, model in self._jobs:
            try:
                if hasattr(model, "needs_recompute") and not model.needs_recompute():
                    self._signals.model_done.emit(role)
                    continue
                model.compute(
                    progress=lambda f, t, role=role: self._signals.progress.emit(role, float(f), str(t))
                )
            except Exception:
                logger.debug("background compute of %r failed", role, exc_info=True)
            self._signals.model_done.emit(role)
        self._signals.all_done.emit()


# ---------------------------------------------------------------------------
# Panel factory functions — each imported lazily to keep startup fast.
# Every factory receives the ImagingToolsTool coordinator as its argument and
# registers the created widget so the coordinator can feed it the shared setup.
# ---------------------------------------------------------------------------

def _setup(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    """Channel / detector setup — the single shared definition (RPC publisher)."""
    from chisurf.plugins.core.setup_channel_definition.gui.tool import (
        SetupChannelDefinitionWidget,
    )
    widget = SetupChannelDefinitionWidget(parent=parent)
    parent._register_setup_panel(widget)
    return widget


def _browser(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.tttr.tttr_image_browser.gui.tool import TTTRImageBrowserTool
    widget = TTTRImageBrowserTool(parent=parent)
    parent._register_panel("browser", widget)
    return widget


def _drift(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_drift.gui.tool import ImgDriftTool
    widget = ImgDriftTool(parent=parent, embedded=True)
    parent._register_panel("drift", widget)
    return widget


def _frc(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_frc.gui.tool import ImgFrcTool
    widget = ImgFrcTool(parent=parent, embedded=True)
    parent._register_panel("frc", widget)
    return widget


def _flow(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_flow.gui.tool import ImgFlowTool
    widget = ImgFlowTool(parent=parent, embedded=True)
    parent._register_panel("flow", widget)
    return widget


def _tracking(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_tracking.gui.tool import ImgTrackingTool
    widget = ImgTrackingTool(parent=parent, embedded=True)
    parent._register_panel("tracking", widget)
    return widget


def _pixel_mle(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_pixel_mle.gui.tool import ImgPixelMleTool
    widget = ImgPixelMleTool(parent=parent, embedded=True)
    parent._register_panel("pixel_mle", widget)
    return widget


def _molecule_mle(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.sm_image_mle.gui.tool import SmImageMleTool
    widget = SmImageMleTool(parent=parent, embedded=True)
    parent._register_panel("molecule_mle", widget)
    return widget


def _pixel_intensity(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.tool import ImgPixelIntensityTool
    widget = ImgPixelIntensityTool(
        parent=parent, embedded=True, view_model=parent.get_or_create_model("pixel_intensity"),
    )
    parent._register_panel("pixel_intensity", widget)
    return widget


def _pixel_nb(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_pixel_nb.gui.tool import ImgPixelNBTool
    widget = ImgPixelNBTool(
        parent=parent, embedded=True, view_model=parent.get_or_create_model("pixel_nb"),
    )
    parent._register_panel("pixel_nb", widget)
    return widget


def _pixel_micro_time(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_pixel_micro_time.gui.tool import ImgPixelMicroTimeTool
    widget = ImgPixelMicroTimeTool(
        parent=parent, embedded=True, view_model=parent.get_or_create_model("pixel_micro_time"),
    )
    parent._register_panel("pixel_micro_time", widget)
    return widget


def _pixel_phasor(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.tool import ImgPixelPhasorTool
    widget = ImgPixelPhasorTool(
        parent=parent, embedded=True, view_model=parent.get_or_create_model("pixel_phasor"),
    )
    parent._register_panel("pixel_phasor", widget)
    return widget


def _calibration(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.img_calibration.gui.tool import ImgCalibrationTool
    widget = ImgCalibrationTool(parent=parent, embedded=True)
    parent._register_panel("calibration", widget)
    return widget


def _clsm_draw(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.clsm.gui.tool import CLSMPixelSelect
    widget = CLSMPixelSelect(parent=parent)
    parent._register_panel("clsm_draw", widget)
    return widget


def _psf(parent: ImagingToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.microscopy.psf_determination.gui.tool import PsfDeterminationTool
    widget = PsfDeterminationTool(parent=parent)
    parent._register_panel("psf", widget)
    return widget


# ---------------------------------------------------------------------------
# Panel list
# ---------------------------------------------------------------------------

IMAGING_PANELS: list[dict] = [
    {
        "name": "Setup",
        "icon": "🧭",
        "description": "Define detector channels and PIE time windows once for all imaging tools.",
        "factory": _setup,
        "role": "setup",
    },
    {
        "name": "Browser",
        "icon": Glyphs.OPEN,
        "description": "Browse TTTR image files and explore intensity maps.",
        "factory": _browser,
        "role": "browser",
    },
    {
        "name": "Drift",
        "icon": "🎯",
        "description": (
            "Optional pre-processing: measure and remove inter-frame sample drift. "
            "Belongs before the numbered steps — every per-pixel map below is built "
            "from frames that must already be aligned. Photon streams are corrected "
            "photon by photon, so the steps below still see real photons."
        ),
        "factory": _drift,
        "role": "drift",
    },
    {
        "name": "Resolution",
        "icon": "◎",
        "description": (
            "How fine a detail this acquisition actually resolves, by Fourier ring "
            "correlation between two independent halves of it. Sits after Drift "
            "because drift blurs the image and so lowers the measured resolution — "
            "measure it on frames that are already aligned."
        ),
        "factory": _frc,
        "role": "frc",
    },
    {
        "name": "Flow",
        "icon": "\U0001F30A",
        "description": (
            "Map the velocity field: one arrow per tile, over the image. Sits "
            "beside Tracking because both measure motion rather than building a "
            "per-pixel map -- and after Drift for the same reason Tracking is, "
            "since a drifting stage is indistinguishable from a sample flowing "
            "the other way. Tracking follows individual particles; this reads a "
            "velocity from the correlations of everything at once, so it works "
            "where the labels are too dense to resolve as spots."
        ),
        "factory": _flow,
        "role": "flow",
    },
    {
        "name": "Tracking",
        "icon": "\U0001F41C",
        "description": (
            "Follow individual particles through the frames and fit their diffusion "
            "coefficient. Sits after Drift because a drifting sample looks exactly "
            "like directed motion, and outside the numbered steps because it "
            "measures motion rather than building a per-pixel map."
        ),
        "factory": _tracking,
        "role": "tracking",
    },
    {
        "name": "1. Intensity",
        "icon": "🔆",
        "description": "Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference).",
        "factory": _pixel_intensity,
        "role": "pixel_intensity",
    },
    {
        "name": "2. Number & Brightness",
        "icon": Glyphs.SPARKLE,
        "description": "Per-pixel Number (N) and Brightness (B); adds fields to the imaging HDF5.",
        "factory": _pixel_nb,
        "role": "pixel_nb",
    },
    {
        "name": "3. Mean Micro-Time",
        "icon": Glyphs.TIMER,
        "description": "Per-pixel mean micro-time (arrival time, ns) per detector window; adds fields to the imaging HDF5.",
        "factory": _pixel_micro_time,
        "role": "pixel_micro_time",
    },
    {
        "name": "4. IRF & BG",
        "icon": Glyphs.GRID,
        "description": "Optional: per-detector IRF file + background (kHz); transferred to Phasor and MLE. Skippable.",
        "factory": _calibration,
        "role": "calibration",
    },
    {
        "name": "5. Phasor-FLIM",
        "icon": "◐",
        "description": "Per-pixel phasor (g, s) maps and phasor plot; adds fields to the imaging HDF5.",
        "factory": _pixel_phasor,
        "role": "pixel_phasor",
    },
    {
        "name": "6. Pixel-wise MLE",
        "icon": "🗺️",
        "description": "Pixel-wise MLE lifetime analysis; adds fields to the imaging HDF5.",
        "factory": _pixel_mle,
        "role": "pixel_mle",
    },
    {
        "name": "────────",
        "icon": "",
        "separator": True,
        "role": "separator",
    },
    {
        "name": "CLSM Draw",
        "icon": Glyphs.EDIT,
        "description": "Interactive CLSM pixel selection, ROI drawing and decay extraction; opens imaging HDF5 (via source back-reference).",
        "factory": _clsm_draw,
        "role": "clsm_draw",
    },
    {
        "name": "Molecule-wise MLE",
        "icon": "💠",
        "description": "Molecule-wise MLE lifetime analysis from TTTR imaging data.",
        "factory": _molecule_mle,
        "role": "molecule_mle",
    },
    {
        "name": "PSF Determination",
        "icon": "🔭",
        "description": "3D Gaussian PSF fitting and bead detection.",
        "factory": _psf,
        "role": "psf",
    },
]


class ImagingToolsTool(NavigationPanelTool):
    """Unified imaging toolbox with a left-navigation panel.

    Holds one :class:`DetectorSetupClient`; the Setup panel publishes the active
    detector definition to the central ``detector_setups.*`` RPC store, and each
    analysis sub-tool pulls it through ``apply_setup_settings``.
    """

    #: Analysis steps in pipeline order for the "Next ▶" convenience.
    PIPELINE_ORDER = (
        "browser", "drift", "frc", "tracking", "pixel_intensity", "pixel_nb",
        "pixel_micro_time", "calibration", "pixel_phasor", "pixel_mle",
    )
    #: Roles whose (Qt-free) view-models the coordinator owns + pre-computes.
    ANALYSIS_ROLES = ("pixel_intensity", "pixel_nb", "pixel_micro_time", "pixel_phasor")

    def __init__(self, parent=None, *, mmfdb_db=None, mmfdb_session=None):
        # Initialise coordination state *before* super().__init__, because the
        # base class loads the first panel (Setup) during construction.
        self._setup_client = DetectorSetupClient()
        self._setup_page = None
        self._panels_by_role: dict[str, QtWidgets.QWidget] = {}
        # Shared, coordinator-owned view-models (so steps can be pre-computed in
        # the background before their panel is opened).
        self._models: dict[str, object] = {}
        # Per-detector IRF/BG calibration (from the skippable IRF & BG step).
        self._calibration: dict = {}
        # Shared pipeline context: the current source (TTTR) and the imaging
        # HDF5 remembered for the image, so any step (freely navigable) reuses
        # them and enrichment tools target the same file.
        self._pipeline: dict[str, str] = {"source": "", "hdf5": ""}
        self._mmfdb_db = mmfdb_db or getattr(mmfdb_session, "db", None)
        self._mmfdb_session = mmfdb_session
        self._owns_mmfdb_db = False
        self._mmfdb_source_artifact_id = ""
        super().__init__(
            title=f"{Glyphs.SCIENCE} Image Tools",
            panels=IMAGING_PANELS,
            parent=parent,
            minimum_size=(900, 600),
            initial_size=(1200, 750),
            navigation_width=210,
        )
        # Auto-run a step when it is navigated to and has no cached result yet.
        # NB: use a distinct name — the base's ``_on_nav_changed`` loads panels.
        try:
            self.nav_list.currentRowChanged.connect(self._autorun_on_nav)
        except Exception:
            logger.debug("could not connect nav auto-run", exc_info=True)
        # Open on the Browser by default (the base shell starts on the Setup
        # panel, which also loads its context); the user typically begins by
        # picking an image, not editing the detector setup.
        for i, panel in enumerate(self.panels):
            if panel.get("role") == "browser":
                self.nav_list.setCurrentRow(i)
                break

    def _autorun_on_nav(self, row: int) -> None:
        """Auto-run the newly selected step if it has a source but no result."""
        if row is None or row < 0 or row >= len(self.panels):
            return
        role = self.panels[row].get("role")
        if not role:
            return
        # Defer so the (lazily loaded) panel is registered before we run it.
        QtCore.QTimer.singleShot(0, lambda r=role: self.autorun_role(r))

    # ── panel registration / setup propagation ─────────────────────────
    def _register_setup_panel(self, widget: QtWidgets.QWidget) -> None:
        """Wire the shared Setup panel to publish definitions over RPC."""
        page = getattr(widget, "page", None)
        if page is None:
            return
        self._setup_page = page
        signal = getattr(page, "detectorsChanged", None)
        if signal is not None:
            try:
                signal.connect(self._on_setup_changed)
            except Exception:  # pragma: no cover - signal wiring is best-effort
                logger.debug("Could not connect detectorsChanged", exc_info=True)
        # Publish whatever the wizard currently holds so panels loaded later
        # (or already loaded) immediately see a definition.
        self._on_setup_changed()

    def _register_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        """Track a sub-tool panel and push the current setup + pipeline to it."""
        self._panels_by_role[role] = widget
        # Wire the panel into the shared pipeline: it can advance ("Next"),
        # remember a written HDF5 (sink), and receive the current context.
        widget._coordinator = self
        widget._pipeline_role = role
        model = getattr(widget, "model", None)
        if model is not None:
            try:
                model.pipeline_sink = self.set_pipeline
            except Exception:
                logger.debug("could not set pipeline_sink on %r", role, exc_info=True)
            # The calibration step publishes its IRF/BG to the pipeline.
            if hasattr(model, "publish"):
                model.publish = self.set_calibration
        self._apply_setup_to_panel(widget)
        self._apply_pipeline_to_panel(widget)
        # Push the current IRF/BG calibration to panels that consume it (MLE).
        apply_cal = getattr(widget, "apply_calibration", None)
        if callable(apply_cal) and self._calibration:
            try:
                apply_cal(self._calibration)
            except Exception:
                logger.debug("apply_calibration on new panel failed", exc_info=True)
        # The panel may wrap an already-(being-)computed shared model → refresh.
        if model is not None and getattr(model, "_columns", None):
            try:
                model.notify("run")
            except Exception:
                logger.debug("panel adopt-refresh failed", exc_info=True)

    # ── coordinator-owned view-models (for background pre-compute) ──────
    def get_or_create_model(self, role: str):
        """Return the shared view-model for *role*, creating + configuring it once."""
        model = self._models.get(role)
        if model is not None:
            return model
        model = self._make_model(role)
        if model is None:
            return None
        try:
            model.pipeline_sink = self.set_pipeline
            model.apply_setup_settings(self._setup_client.get_current())
            model.apply_calibration(self._calibration)
            model.apply_pipeline_context(dict(self._pipeline))
            self._bind_model_to_mmfdb(model)
        except Exception:
            logger.debug("configuring model %r failed", role, exc_info=True)
        self._models[role] = model
        return model

    def set_calibration(self, calibration: dict) -> None:
        """Adopt per-detector IRF/BG and re-compute the affected steps in bg."""
        self._calibration = dict(calibration or {})
        for model in self._models.values():
            try:
                model.apply_calibration(self._calibration)
            except Exception:
                logger.debug("apply_calibration on shared model failed", exc_info=True)
        # Panels that consume calibration directly (e.g. the pixel-wise MLE).
        for widget in self._panels_by_role.values():
            apply = getattr(widget, "apply_calibration", None)
            if callable(apply):
                try:
                    apply(self._calibration)
                except Exception:
                    logger.debug("apply_calibration on panel failed", exc_info=True)
        if self._models and self._pipeline.get("source"):
            self._start_background_compute()

    @staticmethod
    def _make_model(role: str):
        if role == "pixel_intensity":
            from chisurf.plugins.microscopy.img_pixel_intensity.gui.view_model import (
                IntensityViewModel,
            )
            return IntensityViewModel()
        if role == "pixel_nb":
            from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel
            return NBViewModel()
        if role == "pixel_micro_time":
            from chisurf.plugins.microscopy.img_pixel_micro_time.gui.view_model import (
                MicroTimeViewModel,
            )
            return MicroTimeViewModel()
        if role == "pixel_phasor":
            from chisurf.plugins.microscopy.img_pixel_phasor.gui.view_model import (
                PhasorImgViewModel,
            )
            return PhasorImgViewModel()
        return None

    # ── shared pipeline context (source TTTR + imaging HDF5) ────────────
    def set_pipeline(self, source: str | None = None, hdf5: str | None = None) -> None:
        """Update the remembered source/HDF5, push it out, pre-compute steps in bg."""
        new_source = bool(source) and str(source) != self._pipeline.get("source")
        if source:
            self._pipeline["source"] = str(source)
            if new_source:
                self._mmfdb_source_artifact_id = self._ensure_mmfdb_source(
                    str(source)
                )
        if hdf5:
            self._pipeline["hdf5"] = str(hdf5)
        for widget in self._panels_by_role.values():
            self._apply_pipeline_to_panel(widget)
        for model in self._models.values():
            try:
                model.apply_pipeline_context(dict(self._pipeline))
                self._bind_model_to_mmfdb(model)
            except Exception:
                logger.debug("apply_pipeline_context on shared model failed", exc_info=True)
        if new_source:
            self._start_background_compute()

    def _start_background_compute(self) -> None:
        """Compute all analysis steps in the background so results are ready early.

        Non-blocking: the GIL-holding read + fills run in a worker process, so the
        UI stays responsive; progress → status bar, never a modal dialog. Each step
        is refreshed as soon as its results are ready.
        """
        jobs = []
        for role in self.ANALYSIS_ROLES:
            model = self.get_or_create_model(role)
            if model is None:
                continue
            try:
                model.apply_pipeline_context(dict(self._pipeline))
            except Exception:
                logger.debug("apply_pipeline_context failed for %r", role, exc_info=True)
            jobs.append((role, model))
        if not jobs:
            return
        self._set_status("Computing imaging steps in background …")
        signals = _PipelineSignals()
        signals.progress.connect(self._on_bg_progress)
        signals.model_done.connect(self._on_bg_model_done)
        signals.all_done.connect(lambda: self._set_status(""))
        self._pipeline_signals = signals  # keep a ref so signals survive
        QtCore.QThreadPool.globalInstance().start(_PipelineComputeTask(jobs, signals))

    def _on_bg_progress(self, role: str, fraction: float, text: str) -> None:
        self._set_status(f"{role}: {text} ({int(fraction * 100)}%)")

    def _on_bg_model_done(self, role: str) -> None:
        model = self._models.get(role)
        if model is not None:
            try:
                model.notify("run")  # refresh the panel if it is loaded (UI thread)
            except Exception:
                logger.debug("model notify after bg compute failed", exc_info=True)

    def _set_status(self, message: str) -> None:
        """Show background activity in the status bar (best-effort)."""
        try:
            self.statusBar().showMessage(message)
        except Exception:
            logger.debug("status bar update failed", exc_info=True)

    def _apply_pipeline_to_panel(self, widget: QtWidgets.QWidget) -> None:
        """Apply the shared pipeline context to one panel, if it accepts it."""
        apply = getattr(widget, "apply_pipeline_context", None)
        if callable(apply):
            try:
                apply(dict(self._pipeline))
            except Exception:
                logger.debug("apply_pipeline_context failed for %r", widget, exc_info=True)

    def goto_role(self, role: str) -> bool:
        """Switch the navigation to the panel with *role* (free jumping)."""
        for i, panel in enumerate(self.panels):
            if panel.get("role") == role:
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def advance_from(self, role: str) -> None:
        """Go to the next analysis step after *role* (the 'Next ▶' convenience)."""
        order = self.PIPELINE_ORDER
        if role in order:
            idx = order.index(role)
            if idx + 1 < len(order):
                nxt = order[idx + 1]
                self.goto_role(nxt)
                self.autorun_role(nxt)

    def autorun_role(self, role: str) -> None:
        """Auto-run a step's tool if it has a source but no results yet.

        Drives the near-hands-off pipeline: advancing (or the Browser hand-off)
        computes + auto-persists the next step without a manual Run click.
        """
        # Only the compute steps auto-run; settings steps (e.g. IRF & BG) don't.
        if role not in self.ANALYSIS_ROLES:
            return
        widget = self._panels_by_role.get(role)
        model = getattr(widget, "model", None)
        if model is None:
            return
        # Prefer the host's background/status-bar run; fall back to model.run.
        runner = getattr(widget, "run_with_progress", None) or getattr(model, "run", None)
        if runner is None:
            return
        if getattr(model, "filename", "") and not getattr(model, "_columns", None):
            try:
                runner()
            except Exception:
                logger.debug("autorun of %r failed", role, exc_info=True)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist each step's in-memory results and free the compute worker."""
        self.flush_pipeline_hdf5()
        try:
            from chisurf.core.fluorescence.imaging import shutdown_proc_pool

            shutdown_proc_pool()  # release the worker process + its cached TTTR
        except Exception:
            logger.debug("proc pool shutdown on close failed", exc_info=True)
        if self._owns_mmfdb_db and self._mmfdb_db is not None:
            self._mmfdb_db.close()
            self._mmfdb_db = None
            self._mmfdb_session = None
        super().closeEvent(event)

    def _ensure_mmfdb_context(self) -> bool:
        """Open and authenticate the coordinator's local MMFDB context lazily."""
        if self._mmfdb_db is None:
            try:
                from mmfdb.repository import MFDatabase
                from mmfdb.store.database_resolver import resolve_database_path

                self._mmfdb_db = MFDatabase(resolve_database_path())
                self._owns_mmfdb_db = True
            except Exception:
                logger.debug("imaging MMFDB connection unavailable", exc_info=True)
                return False
        if self._mmfdb_session is None:
            from chisurf.core.transform.mmfdb import runtime_session_for_database

            self._mmfdb_session = runtime_session_for_database(self._mmfdb_db)
        if self._mmfdb_session is None:
            return False
        try:
            from chisurf.core.transform.mmfdb import require_authenticated_session

            require_authenticated_session(self._mmfdb_db, self._mmfdb_session)
            return True
        except Exception:
            logger.warning("imaging MMFDB session is invalid", exc_info=True)
            return False

    def _ensure_mmfdb_source(self, source: str) -> str:
        """Reuse a readable raw artifact or register the selected TTTR source."""
        path = Path(source).expanduser().resolve()
        if not path.is_file() or not self._ensure_mmfdb_context():
            return ""
        db = self._mmfdb_db
        session = self._mmfdb_session
        hasher = hashlib.md5(usedforsecurity=False)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        from mmfdb.security.auth import (
            PERM_READ,
            AuthenticatedPrincipal,
            can_access,
        )

        principal = AuthenticatedPrincipal(session.user_id, session.is_admin)
        candidates = db.conn.execute(
            "SELECT artifact_id FROM mmfdb_artifact WHERE deleted_at IS NULL "
            "AND artifact_kind IN ('raw_data', 'raw_measurement') "
            "AND (file_path = ? OR checksum = ?) ORDER BY created_at DESC",
            (str(path), digest),
        ).fetchall()
        for row in candidates:
            if can_access(db.conn, principal, "artifact", row["artifact_id"], PERM_READ):
                return str(row["artifact_id"])

        from mmfdb.provenance.result_registry import register_raw_measurement

        return register_raw_measurement(
            str(path),
            metadata={"source_path": str(path), "integration": "imaging_tools"},
            db=db,
            session=session,
        )

    def _bind_model_to_mmfdb(self, model) -> None:
        """Bind one per-pixel model to the authenticated source artifact."""
        if not self._mmfdb_source_artifact_id or not self._ensure_mmfdb_context():
            return
        from mmfdb.security.auth import AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            self._mmfdb_session.user_id, self._mmfdb_session.is_admin
        )
        model.bind_mmfdb(
            self._mmfdb_db,
            source_artifact_id=self._mmfdb_source_artifact_id,
            principal=principal,
        )

    def flush_pipeline_hdf5(self) -> None:
        """Write steps to the shared HDF5 in pipeline order (Intensity first).

        Uses the coordinator-owned models so steps computed in the background but
        never opened are still persisted.
        """
        for role in self.PIPELINE_ORDER:
            model = self._models.get(role)
            if model is None:
                model = getattr(self._panels_by_role.get(role), "model", None)
            flush = getattr(model, "flush_to_hdf5", None)
            if callable(flush):
                try:
                    flush()
                except Exception:
                    logger.debug("flush of %r failed", role, exc_info=True)

    def _on_setup_changed(self, *args) -> None:
        """Publish the current Setup definition and refresh all sub-tools + models."""
        if self._setup_page is None:
            return
        try:
            settings = self._setup_page.get_settings()
        except Exception:  # pragma: no cover - depends on wizard state
            logger.debug("Could not read setup settings", exc_info=True)
            return
        if settings:
            self._setup_client.set_current(settings)
        for widget in self._panels_by_role.values():
            self._apply_setup_to_panel(widget)
        # Propagate the new detector windows to the coordinator-owned models and
        # re-compute in the background (windows changed → recompute needed).
        for model in self._models.values():
            try:
                model.apply_setup_settings(self._setup_client.get_current())
            except Exception:
                logger.debug("apply_setup to shared model failed", exc_info=True)
        if self._models and self._pipeline.get("source"):
            self._start_background_compute()

    def _apply_setup_to_panel(self, widget: QtWidgets.QWidget) -> None:
        """Apply the shared detector definition to one sub-tool, if it accepts it."""
        apply = getattr(widget, "apply_setup_settings", None)
        if not callable(apply):
            return
        payload = self._setup_client.get_current()
        if not payload:
            return
        try:
            apply(payload)
        except Exception:  # pragma: no cover - sub-tool apply is best-effort
            logger.debug("apply_setup_settings failed for %r", widget, exc_info=True)


__all__ = ["ImagingToolsTool"]
