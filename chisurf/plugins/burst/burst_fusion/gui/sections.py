"""The one bespoke widget of the Burst Fusion tool: its action bar.

Everything else in the tool is declarative (``fusion.view.json``). This section
exists because the two actions differ in kind and the difference has to be
visible: **Analyze** is cheap, repeatable and touches nothing, while **Write
fused folder** reopens the photon streams and creates a folder. They use the
canonical ``run`` and ``save`` buttons from
:mod:`chisurf.gui.widgets.tool_buttons`, so they are the same icon, colour and
position as the corresponding action in every other burst tool — and the shell's
*Next ▶* finds the ``toolAction_run`` and drives this step exactly like the
others.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.dialogs import ChiSurfMessageBox
from chisurf.gui.widgets.navigation import find_status_reporter
from chisurf.gui.widgets.tool_buttons import action_button

logger = logging.getLogger(__name__)


class FusionActionBar(QtWidgets.QWidget):
    """Analyze / write buttons bound to a :class:`~..gui.view_model.FusionViewModel`."""

    is_form_field = False

    def __init__(self, model=None, target: str = "", **options):
        super().__init__()
        self._model = model

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # A button row is exactly as tall as its buttons: without this the panel
        # hands it a share of the spare vertical space and the two buttons float
        # in the middle of a gap, far from the controls they act on.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.analyze_button = action_button(
            "run",
            on_click=self.analyze,
            tooltip="Estimate the same-molecule probability and show what this "
                    "threshold would fuse (reads the burst tables only).",
        )
        self.write_button = action_button(
            "save",
            on_click=self.write,
            tooltip="Write the fused bursts as a new burst-analysis folder "
                    "(reopens the photon streams; the source folder is not changed).",
        )
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.write_button)
        layout.addStretch(1)

    def _run(self, what: str, function) -> None:
        """Run *function* behind the shared status bar, reporting failures once."""
        reporter = find_status_reporter(self)
        task = None
        if reporter is not None:
            try:
                task = reporter.begin_task(what, 0)
            except Exception:
                task = None
        try:
            function()
        except Exception as exc:
            logger.warning("burst fusion: %s failed", what, exc_info=True)
            ChiSurfMessageBox.warning(self, "Burst fusion", str(exc))
        finally:
            if task is not None:
                try:
                    task.close()
                except Exception:
                    pass

    def analyze(self) -> None:
        """Estimate ``P_same`` and preview the fusion."""
        if self._model is None:
            return
        self._run("Estimating the same-molecule probability…", self._model.analyze)

    def write(self) -> None:
        """Write the fused burst folder."""
        if self._model is None:
            return
        self._run("Writing the fused burst folder…", self._model.write)


@register_section("fusion_actions")
def fusion_actions(model, target=None, **options):
    """AutoForm factory for the fusion action bar."""
    return FusionActionBar(model=model, target=target or "", **options)


__all__ = ["FusionActionBar", "fusion_actions"]
