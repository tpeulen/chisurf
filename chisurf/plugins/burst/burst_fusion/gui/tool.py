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
        self.add_toolbar_guide(toolbar, resource="guide.json", model=self.model)
        self.add_toolbar_help(
            toolbar, resource="help.md", title="Burst Fusion — Help", model=self.model
        )
        self.toolbar = toolbar
        self.addToolBar(toolbar)

        self.form = AutoForm(self.model)
        self.setCentralWidget(self.form)
        self.model.add_observer(self._on_model_event)

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
        """The fused folder written by the last run (empty before that)."""
        return self.model.written_folder

    def process_bursts(self) -> None:
        """Analyse without writing — what walking *past* this step does.

        Fusion is an **optional** step, so the shell's *Next ▶* / ⏩ walk must not
        silently change the bursts every later step sees. The walk clicks the
        canonical ``toolAction_run`` button, which is *Analyze*: it estimates the
        probability and shows the preview. Writing the fused folder — the act
        that redirects the pipeline — stays a deliberate press of the save
        button. This method is the same thing for headless callers.
        """
        if self.model.can_run() is None:
            self.model.analyze()

    def _on_model_event(self, event: str) -> None:
        """Redraw whenever the model changed.

        ``refresh_plots`` reaches the summary table and the status block too —
        both opt into ``AUTOFORM_REFRESH`` — so one call keeps every view of the
        analysis in step.
        """
        try:
            self.form.refresh_plots()
        except Exception:
            logger.warning("burst fusion: refresh failed", exc_info=True)


__all__ = ["BurstFusionTool"]
