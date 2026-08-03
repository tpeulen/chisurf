from __future__ import annotations

import numpy as np
from qtpy import QtWidgets

import chisurf.core.decorators
import chisurf.core.base
import chisurf.gui.decorators
import chisurf.core.structure
import chisurf.gui.widgets

#: File dialog filter covering the TTTR containers the reader supports. The
#: reader detects the container from the file, so the filter is a convenience
#: rather than a choice of format.
TTTR_FILE_FILTER = (
    "TTTR files (*.ptu *.ht3 *.spc *.h5 *.hdf5 *.set);;All files (*.*)"
)


class SpcFileWidget(
    QtWidgets.QWidget
):

    @chisurf.gui.decorators.init_with_ui(
        ui_filename="spcSampleSelectWidget.ui"
    )
    def __init__(self, *args, **kwargs):
        self._photons = None
        self.filenames = list()
        # Actions
        self.actionSample_changed.triggered.connect(self.onSampleChanged)
        self.actionLoad_sample.triggered.connect(self.onLoadSample)

    @property
    def sample_name(self) -> str:
        try:
            return self.filename
        except AttributeError:
            return "--"

    @property
    def dt(self) -> float:
        return float(self.doubleSpinBox.value())

    @dt.setter
    def dt(self, v: float):
        self.doubleSpinBox.setValue(v)

    def onSampleChanged(self):
        """Show the loaded measurement's calibration and count rate."""
        # The box is labelled in nanoseconds and the calibration is in seconds.
        # It used to be scaled by 1e6, which showed a picosecond TAC width as
        # a rounded-to-zero "0.0001".
        self.dt = float(self._photons.dt) * 1e9
        self.nTAC = self._photons.n_tac
        # The routing-channel box had never been filled. Show the channels the
        # measurement actually used -- that is what a user needs in order to
        # type a channel number into the tool below it.
        channels = np.unique(self._photons.routing_channels)
        self.lineEdit_3.setText(", ".join(str(int(c)) for c in channels))
        self.number_of_photons = self._photons.nPh
        self.measurement_time = self._photons.measurement_time
        self.lineEdit_7.setText("%.2f" % self.count_rate)

    @property
    def measurement_time(self) -> float:
        return float(self._photons.measurement_time)

    @measurement_time.setter
    def measurement_time(
            self,
            v: float
    ):
        self.lineEdit_6.setText("%.1f" % v)

    @property
    def number_of_photons(self) -> int:
        return int(self.lineEdit_5.value())

    @number_of_photons.setter
    def number_of_photons(
            self,
            v: int
    ):
        self.lineEdit_5.setText(str(v))

    @property
    def rep_rate(self) -> float:
        return float(self.doubleSpinBox_2.value())

    @rep_rate.setter
    def rep_rate(
            self,
            v: float
    ):
        self.doubleSpinBox_2.setValue(v)

    @property
    def nTAC(self) -> int:
        return int(self.lineEdit.text())

    @nTAC.setter
    def nTAC(
            self,
            v: int
    ):
        self.lineEdit.setText(str(v))

    @property
    def count_rate(self) -> float:
        return self._photons.nPh / float(self._photons.measurement_time) / 1000.0

    @property
    def file_type(self) -> str:
        """Container type to read with, or ``None`` to detect it from the file.

        Detection is the right default: the reader identifies the container
        from the file itself, and a type guessed from an extension gets it
        wrong for the formats that share one.
        """
        return None

    @property
    def filename(self) -> str:
        try:
            return self.filenames[0]
        except:
            return "--"

    def onLoadSample(
            self,
            event,
            filenames: str = None,
            file_type: str = None
    ) -> None:
        """Load a TTTR measurement, asking for the file if none is given.

        Parameters
        ----------
        event
            Unused; the action's signal argument.
        filenames : list of str, optional
            Files to read. A measurement split over several files is read as
            one continuous stream.
        file_type : str, optional
            Container type; detected from the file when omitted.
        """
        if file_type is None:
            file_type = self.file_type
        if filenames is None:
            filename = chisurf.gui.widgets.get_filename(
                'Open TTTR file',
                TTTR_FILE_FILTER
            )
            filenames = [str(filename)]

        self.lineEdit_2.setText(str(filenames[0]))
        self.filenames = filenames
        # Drop the previous measurement before reading the next one: a TTTR
        # file is held in memory, so keeping both would double the footprint
        # for as long as the widget lives.
        if self._photons is not None:
            self._photons.close()
        self._photons = chisurf.core.fio.fluorescence.photons.Photons(filenames, file_type)
        #self.samples = self._photons.samples
        #self.comboBox.addItems(self._photons.sample_names)
        self.onSampleChanged()

    @property
    def photons(self) -> chisurf.core.fio.fluorescence.photons.Photons:
        return self._photons

    def closeEvent(self, event):
        """Release the loaded measurement when the widget is closed."""
        if self._photons is not None:
            self._photons.close()
            self._photons = None
        super().closeEvent(event)


class CsvWidget(
    chisurf.core.base.Base,
    QtWidgets.QWidget
):

    @chisurf.gui.decorators.init_with_ui(
        ui_filename="csvInput.ui"
    )
    def __init__(
            self,
            *args,
            **kwargs
    ):
        self.actionUseHeader.triggered.connect(self.changeCsvParameter)
        self.actionSkiprows.triggered.connect(self.changeCsvParameter)
        self.actionColspecs.triggered.connect(self.changeCsvParameter)
        self.actionCsvType.triggered.connect(self.changeCsvParameter)
        self.actionSetError.triggered.connect(self.changeCsvParameter)
        self.actionColumnsChanged.triggered.connect(
            self.changeCsvParameter
        )
        self.verbose = kwargs.get('verbose', chisurf.core.settings.cs_settings['verbose'])

    def changeCsvParameter(self):
        set_errx_on = bool(self.checkBox_3.isChecked())
        set_erry_on = bool(self.checkBox_4.isChecked())
        colspecs = str(self.lineEdit.text())
        use_header = bool(self.checkBox_2.isChecked())
        n_skip = int(self.spinBox.value())
        # If "Auto" is selected, the reading routine will be automatically determined based on the file extension
        if self.radioButton_4.isChecked():
            mode = 'auto'
        elif self.radioButton_2.isChecked():
            mode = 'csv'
        elif self.radioButton.isChecked():
            mode = 'fwf'
        else:
            mode = 'yaml'
        chisurf.run(
            "\n".join(
                [
                    "cs.current_setup.error_y_on = %s" % set_erry_on,
                    "cs.current_setup.error_x_on = %s" % set_errx_on,
                    "cs.current_setup.colspecs = '%s'" % colspecs,
                    "cs.current_setup.use_header = %s" % use_header,
                    "cs.current_setup.skiprows = %s" % n_skip,
                    "cs.current_setup.reading_routine = '%s'" % mode,
                    "cs.current_setup.col_ey = %s" % self.spinBox_5.value(),
                    "cs.current_setup.col_ex = %s" % self.spinBox_3.value(),
                    "cs.current_setup.col_x = %s" % self.spinBox_2.value(),
                    "cs.current_setup.col_y = %s" % self.spinBox_4.value()
                ]
            )
        )

    @property
    def filename(self) -> str:
        return str(self.lineEdit_8.text())

    @filename.setter
    def filename(
            self,
            v: str
    ):
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
