from __future__ import annotations

from qtpy import QtWidgets

import chisurf.core.base
import chisurf.core.structure
import chisurf.core.support.decorators
import chisurf.gui.decorators
import chisurf.gui.widgets

#: File dialog filter for photon data, re-exported from the reading seam.
#:
#: Defined once beside the reader, because a dialog listing a different set from
#: the reader is a dialog that hides files ChiSurf can open — which is how
#: `.pto` came to be absent from every one of them while being the format they
#: all produce. `.pto` is first; the vendor formats after it are import sources.
from chisurf.core.fio.staging import TTTR_FILE_FILTER  # noqa: E402,F401


class CsvWidget(chisurf.core.base.Base, QtWidgets.QWidget):
    @chisurf.gui.decorators.init_with_ui(ui_filename="csvInput.ui")
    def __init__(self, *args, **kwargs):
        self.actionUseHeader.triggered.connect(self.changeCsvParameter)
        self.actionSkiprows.triggered.connect(self.changeCsvParameter)
        self.actionColspecs.triggered.connect(self.changeCsvParameter)
        self.actionCsvType.triggered.connect(self.changeCsvParameter)
        self.actionSetError.triggered.connect(self.changeCsvParameter)
        self.actionColumnsChanged.triggered.connect(self.changeCsvParameter)
        self.verbose = kwargs.get("verbose", chisurf.core.settings.cs_settings["verbose"])

    def changeCsvParameter(self):
        set_errx_on = bool(self.checkBox_3.isChecked())
        set_erry_on = bool(self.checkBox_4.isChecked())
        colspecs = str(self.lineEdit.text())
        use_header = bool(self.checkBox_2.isChecked())
        n_skip = int(self.spinBox.value())
        # If "Auto" is selected, the reading routine will be automatically determined based on the file extension
        if self.radioButton_4.isChecked():
            mode = "auto"
        elif self.radioButton_2.isChecked():
            mode = "csv"
        elif self.radioButton.isChecked():
            mode = "fwf"
        else:
            mode = "yaml"
        chisurf.run(
            "\n".join(
                [
                    f"cs.current_setup.error_y_on = {set_erry_on}",
                    f"cs.current_setup.error_x_on = {set_errx_on}",
                    f"cs.current_setup.colspecs = '{colspecs}'",
                    f"cs.current_setup.use_header = {use_header}",
                    f"cs.current_setup.skiprows = {n_skip}",
                    f"cs.current_setup.reading_routine = '{mode}'",
                    f"cs.current_setup.col_ey = {self.spinBox_5.value()}",
                    f"cs.current_setup.col_ex = {self.spinBox_3.value()}",
                    f"cs.current_setup.col_x = {self.spinBox_2.value()}",
                    f"cs.current_setup.col_y = {self.spinBox_4.value()}",
                ]
            )
        )

    @property
    def filename(self) -> str:
        return str(self.lineEdit_8.text())

    @filename.setter
    def filename(self, v: str):
        self.lineEdit_8.setText(v)


# To be deleted
#
# class CSVFileWidget(QtWidgets.QWidget):
#
#     def __init__(
#             self,
#             *args,
#             **kwargs
#     ):
#         super().__init__(
#             *args,
#             **kwargs
#         )
#
#         layout = QtWidgets.QVBoxLayout(self)
#         layout.setSpacing(0)
#         layout.setContentsMargins(0, 0, 0, 0)
#
#         self.layout = layout
#         self.csvWidget = CsvWidget(**kwargs)
#         self.layout.addWidget(self.csvWidget)
#
#     def load_data(
#             self,
#             filename: str = None
#     ) -> chisurf.experiment.data.DataCurve:
#         """
#         Loads csv-data into a Curve-object
#         :param filename:
#         :return: Curve-object
#         """
#         d = chisurf.experiment.data.DataCurve(setup=None)
#         if filename is not None:
#             self.csvWidget.load(filename)
#             d.filename = filename
#         else:
#             self.csvWidget.load()
#             d.filename = self.csvWidget.filename
#
#         d.x, d.y = self.csvWidget.data_x, self.csvWidget.data_y
#         if self.weight_calculation is None:
#             d.set_weights(self.csvWidget.error_y)
#         else:
#             d.set_weights(self.weight_calculation(d.y))
#         return d
#
#     def get_data(self, *args, **kwargs):
#         return self.load_data(*args, **kwargs)
