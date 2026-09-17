import sys

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.experiments
import chisurf.core.fitting
import chisurf.gui
import chisurf.gui.decorators
import chisurf.gui.widgets
import chisurf.gui.widgets.parameter_editor
import chisurf.gui.widgets.wizard
import chisurf.macros
from chisurf.gui import QtWidgets


class ChisurfWizard(QtWidgets.QWizard):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWizardStyle(QtWidgets.QWizard.ModernStyle)

        # File format
        page = chisurf.gui.widgets.wizard.WizardFcsMerger()
        self.addPage(page)
        self._attach_help(page)

    def _attach_help(self, page) -> None:
        """Put the ``?`` and **Guide** pair at the top of the wizard page.

        A ``QWizard`` has no toolbar and its button box is reserved for
        navigation, so the strip goes at the top of the page's own layout. The
        tour still runs over the *wizard*, not the page, so its spotlight covers
        the whole window.

        ``owner`` anchors the resource lookup at this module, because the help
        files live with the plugin (``fcs_merger/help.md``) while the page class
        they describe lives in the shared wizard package.
        """
        from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide

        layout = page.layout()
        if layout is None:
            return
        toolbar = QtWidgets.QToolBar(page)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setStyleSheet("QToolBar { border: none; padding: 0px; spacing: 2px; }")
        attach_help_and_guide(self, toolbar, title="FCS curve merger — help", owner=type(self))
        if hasattr(layout, "insertWidget"):
            layout.insertWidget(0, toolbar)
        else:
            layout.addWidget(toolbar)


if __name__ == "plugin":
    wizard = ChisurfWizard()
    wizard.show()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    wizard = ChisurfWizard()
    wizard.show()
    sys.exit(app.exec_())
