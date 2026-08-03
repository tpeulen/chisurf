from __future__ import annotations
from chisurf import typing
import chisurf as cs

import sys

from chisurf.gui import QtCore, QtWidgets
from chisurf.gui import chiplot as cp
from chisurf.gui.autoform.sections.progress_section import adopt_progress_bar
# Now using qtpy compatibility layer through cs.gui import

import numpy as np
import tttrlib

import chisurf.core.curve
import chisurf.core.decorators
#import cs.gui.tools
import chisurf.core.fio
import chisurf.core.fluorescence
import chisurf.core.data
import chisurf.gui.decorators
import chisurf.core.settings
import chisurf.core.fluorescence.fcs
import chisurf.gui.widgets
import chisurf.gui.widgets.experiments
import chisurf.gui.widgets.fio

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c



class Correlator(QtCore.QThread):

    procDone = QtCore.Signal(bool)
    partDone = QtCore.Signal(int)

    @property
    def data(self) -> cs.core.data.DataCurve:
        """Return the correlation result as a :class:`DataCurve`.

        Returns
        -------
        cs.core.data.DataCurve
            The cached data curve when available, otherwise a new empty
            :class:`DataCurve` associated with this correlator.
        """
        if isinstance(self._data_curve, cs.core.data.DataCurve):
            return self._data_curve
        else:
            return cs.core.data.DataCurve(
                setup=self
            )

    def __init__(
            self,
            photon_source,
            *args,
            **kwargs
    ):
        """Initialize the correlator thread.

        Parameters
        ----------
        photon_source : object
            Object exposing ``photon_source.photons`` (used to access
            the photon stream and its meta information).
        *args, **kwargs
            Forwarded to :class:`QtCore.QThread`.
        """
        super().__init__(*args, **kwargs)
        self.p = photon_source
        self.exiting = False
        self._data_curve = None
        self._results = list()
        self._dt1 = 0
        self._dt2 = 0

    def run(self):
        """Correlate the two channel selections and emit progress/done signals.

        The measurement is split into ``self.p.split`` equal *time* intervals,
        each interval is correlated on its own, and the results are averaged --
        splitting gives an estimate of the scatter between sub-measurements,
        which the noise model turns into error bars.

        Both channel selections are cut at the same interval boundaries. An
        earlier version selected channels by giving every photon a weight of
        one or zero and split by photon *index*, which put the two channels'
        groups over different stretches of the measurement whenever their count
        rates differed.
        """
        cs.logging.info("Correlation running...")
        cs.logging.info("Correlation method: %s" % self.p.method)
        cs.logging.info("Fine-correlation: %s" % self.p.fine)
        cs.logging.info("Data stream split into %s correlations." % self.p.split)

        photons = self.p.photon_source.photons
        stream_1 = photons.by_channel(self.p.ch1)
        stream_2 = photons.by_channel(self.p.ch2)
        macro_1 = stream_1.macro_times
        macro_2 = stream_2.macro_times
        if macro_1.size == 0 or macro_2.size == 0:
            cs.logging.warning(
                "no photons in channels %s / %s" % (self.p.ch1, self.p.ch2)
            )
            self.procDone.emit(False)
            return

        mt_clk = photons.mt_clk
        n_groups = max(1, int(self.p.split))
        start = min(macro_1[0], macro_2[0])
        stop = max(macro_1[-1], macro_2[-1])
        edges = np.linspace(float(start), float(stop), n_groups + 1)

        self._results = list()
        for i_group in range(n_groups):
            lo, hi = edges[i_group], edges[i_group + 1]
            t1 = macro_1[(macro_1 >= lo) & (macro_1 < hi)]
            t2 = macro_2[(macro_2 >= lo) & (macro_2 < hi)]
            if t1.size < 2 or t2.size < 2:
                continue

            correlator = tttrlib.Correlator()
            correlator.n_bins = int(self.p.B)
            correlator.n_casc = int(self.p.number_of_cascades)
            try:
                correlator.method = str(self.p.method)
            except Exception:
                cs.logging.warning("unknown correlation method %s" % self.p.method)
            correlator.set_macrotimes(
                np.ascontiguousarray(t1, dtype=np.uint64),
                np.ascontiguousarray(t2, dtype=np.uint64),
            )
            correlator.set_weights(
                np.ones(t1.size, dtype=np.float64),
                np.ones(t2.size, dtype=np.float64),
            )
            if self.p.fine:
                b = self.p.microtime_binning
                mt1 = stream_1.micro_times[(macro_1 >= lo) & (macro_1 < hi)]
                mt2 = stream_2.micro_times[(macro_2 >= lo) & (macro_2 < hi)]
                if b > 1:
                    mt1 = mt1 // b
                    mt2 = mt2 // b
                correlator.set_microtimes(mt1, mt2, self.p.effective_n_tac)
            correlator.run()

            # ChiSurf's FCS models take the lag axis in milliseconds, and the
            # macro-time resolution is in seconds. The old code multiplied by
            # the resolution alone and called the result milliseconds, so every
            # correlation this tool produced was a factor of 1000 off.
            tau = np.asarray(correlator.get_x_axis(), dtype=np.float64) * mt_clk * 1e3
            corr = np.asarray(correlator.get_corr_normalized(), dtype=np.float64)
            duration = (hi - lo) * mt_clk
            count_rate = (t1.size + t2.size) / duration / 1000.0  # kHz
            self._results.append([count_rate, duration, tau, corr])
            self.partDone.emit(float(i_group + 1) / n_groups * 100)

        if not self._results:
            cs.logging.warning("no interval contained enough photons to correlate")
            self.procDone.emit(False)
            return

        # Calculate average correlations
        cors = list()
        taus = list()
        weights = list()

        for c in self._results:
            cr, dur, tau, corr = c
            # The correlator's first bin is lag zero. It carries no correlation
            # information, and the noise model reads a diffusion time off the
            # axis -- a zero lag makes that estimate zero and the weights
            # divide by it. Drop it here, before weighting, so the weights and
            # the curve are computed on the same axis.
            if len(tau) and tau[0] <= 0.0:
                tau, corr = tau[1:], corr[1:]
            weight = self.weight(tau, corr, dur, cr)
            weights.append(weight)
            cors.append(corr)
            taus.append(tau)

        cor = np.array(cors)
        w = np.array(weights)

        data_curve = cs.core.data.DataCurve(
            x=np.array(taus).mean(axis=0),
            y=cor.mean(axis=0),
            ey=1. / w.mean(axis=0)
        )
        cs.logging.info("Correlation finished!")

        self._data_curve = data_curve
        self.procDone.emit(True)
        self.exiting = True

    def weight(
            self,
            tau,
            cor,
            acquisition_time,
            count_rate
    ):
        """Weight a per-group correlation by its expected noise.

        Parameters
        ----------
        tau : np.ndarray
            tau-axis in milliseconds.
        cor : np.ndarray
            Correlation amplitude corresponding to ``tau``.
        acquisition_time : float
            Duration of the group in seconds.
        count_rate : float
            Count-rate in kHz.

        Returns
        -------
        np.ndarray
            Weight vector as returned by ``cs.core.fluorescence.fcs.noise``
            using the configured ``weighting`` (``uniform`` or ``suren``).
        """
        if self.p.weighting == 1:
            return cs.core.fluorescence.fcs.noise(
                tau, cor, acquisition_time, count_rate, weight_type='uniform'
            )
        elif self.p.weighting == 0:
            return cs.core.fluorescence.fcs.noise(
                tau, cor, acquisition_time, count_rate, weight_type='suren'
            )


class CorrelatorWidget(QtWidgets.QWidget):

    @cs.gui.decorators.init_with_ui(ui_filename="correlatorWidget.ui")
    def __init__(
            self,
            photon_source,
            ch1: int = '0',
            ch2: int = '8',
            number_of_cascades: int = None,
            B: int = None,
            split: int = None,
            weighting: str = None,
            fine: bool = None
    ):
        # Import settings here to make them dynamic
        from chisurf.core.settings import cs_settings
        correlator_settings = cs_settings['correlator']

        # Use default settings if parameters are None
        if number_of_cascades is None:
            number_of_cascades = correlator_settings['number_of_cascades']
        if B is None:
            B = correlator_settings['B']
        if split is None:
            split = correlator_settings['split']
        if weighting is None:
            weighting = correlator_settings['weighting']
        if fine is None:
            fine = correlator_settings['fine']
        self.number_of_cascades = number_of_cascades
        self.B = B
        self.split = split
        self.weighting = weighting
        self.fine = fine
        self.cr = 0.0
        self.ch1 = ch1
        self.ch2 = ch2

        self.photon_source = photon_source
        self.correlator_thread = Correlator(
            photon_source=self
        )

        # fill widgets
        self.comboBox_3.addItems(cs.core.fluorescence.fcs.weightCalculations)
        self.comboBox_2.addItems(cs.core.fluorescence.fcs.correlationMethods)
        self.checkBox.setChecked(False)
        self.comboBox_micro_binning.addItems(['1', '2', '4', '8', '16'])
        self.comboBox_micro_binning.setEnabled(False)
        self.checkBox.toggled.connect(
            self.comboBox_micro_binning.setEnabled
        )
        # The bar comes from the .ui file; swap in the shared one so a
        # correlation looks like every other long run in ChiSurf.
        adopt_progress_bar(self)
        self.progressBar.setValue(0)

        # connect widgets
        self.pushButton_3.clicked.connect(self.correlator_thread.start)
        self.correlator_thread.partDone.connect(self.updateProgressBar)

    def updateProgressBar(self, val):
        self.progressBar.setValue(val)

    @property
    def data(self) -> cs.core.data.DataCurve:
        return self.correlator_thread.data

    @property
    def effective_n_tac(self) -> int:
        b = self.microtime_binning
        return (self.photon_source.photons.n_tac + b - 1) // b

    @property
    def dt(self):
        dt = self.photon_source.photons.mt_clk
        if self.fine:
            dt /= self.effective_n_tac
        return dt

    @property
    def microtime_binning(self) -> int:
        return int(self.comboBox_micro_binning.currentText())

    @microtime_binning.setter
    def microtime_binning(self, v: int):
        idx = self.comboBox_micro_binning.findText(str(v))
        if idx >= 0:
            self.comboBox_micro_binning.setCurrentIndex(idx)

    @property
    def weighting(self) -> int:
        return self.comboBox_3.currentIndex()

    @weighting.setter
    def weighting(
            self,
            v: int
    ):
        self.comboBox_3.setCurrentIndex(int(v))

    @property
    def ch1(self) -> typing.List[int]:
        return [int(x) for x in str(self.lineEdit_4.text()).split()]

    @ch1.setter
    def ch1(
            self,
            v: str
    ):
        self.lineEdit_4.setText(str(v))

    @property
    def ch2(self) -> typing.List[int]:
        return [int(x) for x in str(self.lineEdit_5.text()).split()]

    @ch2.setter
    def ch2(
            self,
            v: str
    ):
        self.lineEdit_5.setText(str(v))

    @property
    def fine(self) -> int:
        return int(self.checkBox.isChecked())

    @fine.setter
    def fine(
            self,
            v: bool
    ):
        self.checkBox.setCheckState(v)

    @property
    def B(self) -> int:
        return int(self.spinBox_3.value())

    @B.setter
    def B(
            self,
            v: int
    ):
        return self.spinBox_3.setValue(v)

    @property
    def number_of_cascades(self) -> int:
        return int(self.spinBox_2.value())

    @number_of_cascades.setter
    def number_of_cascades(
            self,
            v: int
    ):
        self.spinBox_2.setValue(v)

    @property
    def method(self) -> str:
        return str(self.comboBox_2.currentText())

    @property
    def split(self) -> float:
        return int(self.spinBox.value())

    @split.setter
    def split(
            self,
            v: float
    ):
        self.spinBox.setValue(v)


@persist_plugin_state("tttr_correlate")
class CorrelateTTTR(
    QtWidgets.QWidget
):

    name = "tttr-correlate"

    @property
    def curve_name(self):
        s = str(self.lineEdit.text())
        if len(s) == 0:
            return "no-name"
        else:
            return s

    def onRemoveDataset(self):
        selected_index = [
            i.row() for i in self.cs.selectedIndexes()
        ]
        l = list()
        for i, c in enumerate(self._curves):
            if i not in selected_index:
                l.append(c)
        self._curves = l
        self.cs.update()
        self.plot_curves()

    def clear_curves(self):
        self._curves = list()
        self.plot.clear()

    def get_data_curves(
            self,
            *args,
            **kwargs
    ) -> typing.List[cs.core.curve.Curve]:
        return self._curves

    def plot_curves(self):
        self.plot.clear()
        self.plot.legend()
        self.plot.set_log(x=True, y=False)
        self.plot.set_labels(bottom="lag time / ms", left="G(tau)")
        self.plot.grid(x=True, y=True, alpha=1.0)

        # Import settings here to make them dynamic
        from chisurf.core.settings import cs_settings, colors
        plot_settings = cs_settings['gui']['plot']

        current_curve = self.cs.selected_curve_index
        lw = plot_settings['line_width']
        for i, curve in enumerate(self._curves):
            w = lw * 0.5 if i != current_curve else 1.5 * lw
            self.plot.line(
                curve.x, curve.y,
                pen=colors[i % len(colors)]['hex'],
                width=w,
                name=curve.name
            )

    def closeEvent(self, event):
        """Close the file widget too, so its photon file is released.

        Qt delivers a close event only to the widget being closed, not to its
        children, so the tool has to pass it on.
        """
        self.fileWidget.close()
        super().closeEvent(event)

    def add_curve(self):
        self._curves = [self.correlator.data]
        self.cs.update()
        self.plot_curves()

    @cs.gui.decorators.init_with_ui("tttr_correlate.ui")
    def __init__(self):
        self._curves = list()

        self.fileWidget = cs.gui.widgets.fio.SpcFileWidget()
        self.verticalLayout.addWidget(self.fileWidget)

        # Import settings here to make them dynamic
        from chisurf.core.settings import cs_settings
        correlator_settings = cs_settings['correlator']

        self.correlator = CorrelatorWidget(
            photon_source=self.fileWidget,
            number_of_cascades=correlator_settings['number_of_cascades'],
            B=correlator_settings['B'],
            split=correlator_settings['split']
        )
        self.verticalLayout.addWidget(self.correlator)

        self.cs = cs.gui.widgets.experiments.widgets.ExperimentalDataSelector(
            get_data_sets=self.get_data_curves,
            click_close=False
        )
        self.verticalLayout_6.addWidget(self.cs)

        self.correlator.correlator_thread.finished.connect(self.add_curve)
        # self.curve_selector.itemClicked.connect(self.plot_curves)

        self.plot = cp.Plot()
        self.verticalLayout_9.addWidget(self.plot)
        self.plot.legend()
        self.cs.onRemoveDataset = self.onRemoveDataset


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = CorrelateTTTR()
    win.show()
    sys.exit(app.exec_())
