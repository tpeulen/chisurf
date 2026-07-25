import typing

import chisurf as cs
import chisurf.gui.decorators
from chisurf.gui import QtWidgets
from chisurf.gui import chiplot as cp


def setup_ui(page):
    page.setTitle("Correlation merging")
    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    page.setSizePolicy(sizePolicy)
    page.textEdit.setVisible(False)

    page.correlations: typing.List[dict] = list()

    cs.gui.decorators.lineEdit_dragFile_injector(page.lineEdit, call=page.open_correlation_folder)

    # Setup plots. chiplot's Plot exposes drawing methods directly, so
    # ``plot_item_*`` aliases the widget itself (there is no separate plot-item).
    page.pw_fcs = cp.Plot(parent=page, title='FCS')
    page.pw_fcs.resize(100, 150)
    page.plot_item_fcs = page.pw_fcs
    page.plot_item_fcs.set_log(x=True, y=False)
    page.horizontalLayout_3.addWidget(page.pw_fcs)

    page.pw_fcs_mean = cp.Plot(parent=page, title='FCS Merged')
    page.pw_fcs_mean.resize(100, 150)
    page.plot_item_fcs_mean = page.pw_fcs_mean
    page.plot_item_fcs_mean.set_log(x=True, y=False)
    page.horizontalLayout_3.addWidget(page.pw_fcs_mean)

    # Setup table widget with an extra column for the merge checkbox.
    page.tableWidget.setColumnCount(5)
    page.tableWidget.setHorizontalHeaderLabels(["Use", "File", "CR A (kHz)", "CR B (kHz)", "Duration (s)"])

    # Remove the double-click deletion action and instead toggle the checkbox on double click.
    # self.actionRowDoubleClicked.triggered.connect(self.onRemoveRow)  <-- Removed!
    page.tableWidget.itemDoubleClicked.connect(page.onRowDoubleClicked)
    page.actionRowSingleClick.triggered.connect(page.update_plots)
    page.toolButton_3.clicked.connect(page.save_mean_correlation)
