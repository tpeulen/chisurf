"""GUI entry point of the Burst Fusion step, powered by emtk.

A :class:`~chisurf.gui.widgets.tools.chisurf_dock_tool.ChisurfDockTool` hosting
:class:`~.app.BurstFusionApp` through :class:`emtk.qt_host.ControlHost` over the
Qt-free :class:`~.view_model.FusionViewModel`.
"""

from __future__ import annotations

import logging
from typing import Any

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets

from chisurf.gui.dialogs import ChiSurfMessageBox
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

from .app import WINDOW_BG, BurstFusionApp
from .view_model import FusionViewModel

logger = logging.getLogger(__name__)


class _FormShim:
    """Compatibility shim for callers expecting an AutoForm interface."""

    def __init__(self, host: QtWidgets.QWidget) -> None:
        self._host = host

    def sync_fields(self) -> None:
        self._host.update()

    def refresh_plots(self) -> None:
        self._host.update()


class BurstFusionTool(ChisurfDockTool):
    """Fuse bursts the same molecule produced into a new burst folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Burst Fusion")
        self.setMinimumSize(900, 620)

        self.model = FusionViewModel()
        self.app = BurstFusionApp(
            model=self.model,
            on_demo=self.load_demo,
            on_guide=self._start_guide,
            on_help=self._show_help,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)
        self.form = _FormShim(self.host)

        toolbar = QtWidgets.QToolBar()
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._demo_action = toolbar.addAction("🧪 Load demo")
        self._demo_action.setToolTip(
            "Simulate a measurement whose answer is declared — a known number of "
            "molecules, a known fraction of their crossings cut up by the burst "
            "search — and load its burst folder, so fusion can be judged against "
            "a number instead of a feeling."
        )
        self._demo_action.triggered.connect(self.load_demo)
        guide_btn = self.add_toolbar_guide(toolbar, resource="guide.json", model=self.model)
        if guide_btn is not None:
            try:
                guide_btn.clicked.disconnect()
            except Exception:
                pass
            guide_btn.clicked.connect(self._start_guide)

        help_btn = self.add_toolbar_help(
            toolbar, resource="help.md", title="Burst Fusion — Help", model=self.model
        )
        if help_btn is not None and getattr(help_btn, "button", None) is not None:
            try:
                help_btn.button.clicked.disconnect()
            except Exception:
                pass
            help_btn.button.clicked.connect(self._show_help)

        self.toolbar = toolbar
        self.toolbar.setVisible(False)
        self.toolbar.hide()

        # Invisible proxy action buttons for navigation shell discovery and testing
        self.btn_run = QtWidgets.QToolButton(self)
        self.btn_run.setObjectName("toolAction_run")
        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_run.hide()

        self.btn_refresh = QtWidgets.QToolButton(self)
        self.btn_refresh.setObjectName("toolAction_refresh")
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        self.btn_refresh.hide()

        self.model.add_observer(self._on_model_event)

    def _on_run_clicked(self) -> None:
        self.process_bursts()

    def _on_refresh_clicked(self) -> None:
        try:
            self.model.analyze()
        except Exception:
            logger.warning("burst fusion: analyze failed", exc_info=True)

    def _start_guide(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "start_guide"):
            self.app.start_guide()
            return
        if getattr(self, "_guide_button", None) is not None:
            self._guide_button.click()

    def _show_help(self) -> None:
        if hasattr(self, "app") and hasattr(self.app, "show_help"):
            self.app.show_help()
            return
        if getattr(self, "_help_button", None) is not None:
            self._help_button.show_help()

    def tour_target(self, target: dict[str, Any]) -> tuple[QtWidgets.QWidget, tuple | None] | None:
        """Tell GuidedTour where a step target is on this emtk surface."""
        action = target.get("action")
        if action and hasattr(self, "_demo_action"):
            w = self.toolbar.widgetForAction(self._demo_action)
            if w is not None:
                return w, None
        key = target.get("key") or target.get("attr") or target.get("title") or target.get("name")
        if key:
            rect = self.app.fusion_gui.item_rects.get(str(key))
            if rect is not None:
                return self.host, rect
            return self.host, (0.0, 0.0, float(self.host.width()), float(self.host.height()))
        return None

    def load_demo(self) -> None:
        """Generate (or reuse) the demo measurement and load its burst folder."""
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
            self.host.update()
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
        self.host.update()

    def set_channel_settings(self, settings: dict) -> None:
        """Adopt the workflow's detector definition for regenerating the bursts."""
        settings = settings or {}
        self.model.detectors = dict(settings.get("detectors") or {})
        self.model.windows = dict(settings.get("windows") or {})

    def output_folder(self) -> str:
        """Return the fused folder written by the last run (empty before that)."""
        return self.model.written_folder

    def process_bursts(self) -> str:
        """Fuse the bursts and write the folder — the headless *Run*."""
        if self.model.can_run() is not None:
            return ""
        result = self.model.fuse()
        self.host.update()
        return result

    def _on_model_event(self, event: str) -> None:
        """Redraw whenever the model changed."""
        try:
            self.host.update()
        except Exception:
            logger.warning("burst fusion: refresh failed", exc_info=True)


__all__ = ["BurstFusionTool"]
