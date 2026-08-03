"""GUI entry point of the Burst Fusion step.

A :class:`~chisurf.gui.widgets.tools.chisurf_dock_tool.ChisurfDockTool` holding
one :class:`~chisurf.gui.autoform.AutoForm` over the Qt-free
:class:`~.view_model.FusionViewModel`, laid out by ``fusion.view.json``. The
toolbar carries only the ``?`` help and the guided tour; the two actions live in
the form itself (``gui.sections``) because they belong beside the threshold that
drives them.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform import AutoForm
from chisurf.gui.dialogs import ChiSurfMessageBox
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from . import sections  # noqa: F401  (side effect: registers the action bar)
from .view_model import FusionViewModel

logger = logging.getLogger(__name__)


class BurstFusionTool(ChisurfDockTool):
    """Fuse bursts the same molecule produced into a new burst folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Burst Fusion")
        self.setMinimumSize(900, 620)

        self.model = FusionViewModel()

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        demo = toolbar.addAction("🧪 Load demo")
        demo.setToolTip(
            "Simulate a measurement whose answer is declared — a known number of "
            "molecules, a known fraction of their crossings cut up by the burst "
            "search — and load its burst folder, so fusion can be judged against "
            "a number instead of a feeling."
        )
        demo.triggered.connect(self.load_demo)
        self.add_toolbar_guide(toolbar, resource="guide.json", model=self.model)
        self.add_toolbar_help(
            toolbar, resource="help.md", title="Burst Fusion — Help", model=self.model
        )
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        self.form = AutoForm(self.model)
        self.setCentralWidget(self.form)
        self.model.add_observer(self._on_model_event)

    def load_demo(self) -> None:
        """Generate (or reuse) the demo measurement and load its burst folder.

        The first run simulates a photon stream and runs a burst search over it,
        which takes a few seconds, so it reports into the shared status bar (or
        the window's own, standalone) rather than freezing silently.
        """
        from chisurf.gui.widgets.navigation import find_status_reporter

        reporter = find_status_reporter(self)
        task = None
        if reporter is not None:
            try:
                task = reporter.begin_task("Simulating the demo measurement…", 100)
            except Exception:
                task = None

        def progress(fraction: float, message: str) -> None:
            if task is not None:
                try:
                    task.setValue(int(fraction * 100))
                    task.setLabelText(message)
                except Exception:
                    pass
            else:
                self.statusBar().showMessage(message)

        try:
            self.model.load_demo(progress=progress)
            self.form.sync_fields()
        except Exception as exc:
            logger.warning("burst fusion: the demo could not be built", exc_info=True)
            ChiSurfMessageBox.warning(self, "Burst fusion — demo", str(exc))
        finally:
            if task is not None:
                try:
                    task.close()
                except Exception:
                    pass

    # ── workflow hand-off ───────────────────────────────────────────────
    def set_folder(self, folder: str) -> None:
        """Point the step at the burst folder an upstream step produced."""
        self.model.set_folder(str(folder))
        self.form.sync_fields()

    def set_channel_settings(self, settings: dict) -> None:
        """Adopt the workflow's detector definition for regenerating the bursts.

        The fused burst table is re-derived from the photons, which needs the
        detector/window definition. The source folder's reading manifest carries
        it, but a folder written by an older version does not — and then the
        workflow's own channel page is the only place it exists.
        """
        settings = settings or {}
        self.model.detectors = dict(settings.get("detectors") or {})
        self.model.windows = dict(settings.get("windows") or {})

    def output_folder(self) -> str:
        """Return the fused folder written by the last run (empty before that)."""
        return self.model.written_folder

    def process_bursts(self) -> str:
        """Fuse the bursts and write the folder — the headless *Run*.

        Running this step means producing its output: the fused folder, handed
        to the workflow so every later step analyses it. The shell's *Next ▶* /
        ⏩ walk never reaches this, because the step is declared ``optional`` and
        the walk passes over optional steps without running them — pressing Next
        on an un-run fusion step leaves the pipeline on the bursts it already
        had, which is the whole meaning of "optional" here.
        """
        if self.model.can_run() is not None:
            return ""
        return self.model.fuse()

    def _on_model_event(self, event: str) -> None:
        """Redraw whenever the model changed.

        ``refresh_plots`` reaches the summary table and the status block too —
        both opt into ``AUTOFORM_REFRESH`` — so one call keeps every view of the
        analysis in step.
        """
        try:
            self.form.refresh_plots()
            # Also re-read the fields: the model is written to from outside the
            # form as well (the demo, the embedding workflow), and a control still
            # showing the old value next to a result computed from the new one is
            # worse than no control at all.
            self.form.sync_fields()
        except Exception:
            logger.warning("burst fusion: refresh failed", exc_info=True)


__all__ = ["BurstFusionTool"]
