"""Unified fit-style window and plot pages for the legacy acquisition plugin."""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

import chisurf
from chisurf.gui import chiplot
from chisurf.gui.widgets.dock_area import DockArea
from chisurf.gui.widgets.mdi_custom_titlebar import CustomMdiSubWindow

from .controllers import (
    CorrelationPlotController,
    CountRatePlotController,
    DecayPlotController,
    MacrotimePlotController,
    MCSPlotController,
)

#: Per-channel curve colours, shared by every acquisition view so that channel 2
#: is the same colour in the decay, the count rate and the correlation. The fifth
#: is the "All" trace of the count-rate page.
CHANNEL_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (128, 128, 128),
]


class AcquisitionPlotPage(QtWidgets.QWidget):
    """A plot page embedded in the acquisition fit window's dock area."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Preserve the attributes consumed by generic ChiSurf window handling.
        self.fit = None
        self.fit_widget = None
        self.current_plot_controller = None
        self._content_layout = QtWidgets.QVBoxLayout(self)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

    def set_content(self, widget: QtWidgets.QWidget) -> None:
        """Install the page content without introducing an extra MDI frame."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
        self._content_layout.addWidget(widget)


class AcquisitionFitWindow(CustomMdiSubWindow):
    """One MDI acquisition surface with settings and plot pages as dock tabs."""

    def __init__(
        self,
        settings_page: QtWidgets.QWidget,
        plot_pages,
        main_window=None,
        parent=None,
        close_callback=None,
    ):
        super().__init__(title="acq", parent=parent)
        self.setWindowTitle("acq")
        self.main_window = main_window
        self._close_callback = close_callback
        self.fit = None
        self.fit_widget = None
        self.settings_page = settings_page
        self._pages = [settings_page, *[page for _name, page in plot_pages]]

        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.plot_tab_widget = DockArea(self)
        self.plot_tab_widget.setNewTabButtonVisible(False)
        self.content_layout.addWidget(self.plot_tab_widget)

        self.plot_tab_widget.addTab(settings_page, "Acq Settings")
        for name, page in plot_pages:
            self.plot_tab_widget.addTab(page, name)

        self.current_plot_controller = None
        self.plot_tab_widget.currentChanged.connect(self.on_change_plot)
        xs, ys = chisurf.settings.gui["fit_windows_size"]
        # Acquisition controls are deliberately denser than generic fit plots;
        # honour a larger user fit-window preference but never start so narrow
        # that the output and settings actions are clipped.
        width = max(int(xs), 750)
        height = max(int(ys), 600)
        self.setMinimumSize(width, height)
        self.resize(width, height)
        self.on_change_plot()

    def on_change_plot(self, *_args) -> None:
        """Expose the selected graph's existing controller in Plot Settings."""
        old_controller = self.current_plot_controller
        page = self.plot_tab_widget.currentWidget()
        controller = getattr(page, "plot_controller", None)
        if old_controller is not None and old_controller is not controller:
            old_controller.hide()
        self.current_plot_controller = controller
        self._sync_host_plot_settings()

    def _sync_host_plot_settings(self) -> None:
        """Reuse the host's established MDI-to-Plot-Settings integration."""
        host = self.main_window
        if host is None:
            return
        mdi_area = getattr(host, "mdiarea", None)
        if mdi_area is not None and mdi_area.currentSubWindow() is not self:
            return
        activated = getattr(host, "subWindowActivated", None)
        if callable(activated):
            activated()
            return

        layout = getattr(host, "plotOptionsLayout", None)
        if layout is None:
            return
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                widget.hide()
        if self.current_plot_controller is not None:
            layout.addWidget(self.current_plot_controller)
            self.current_plot_controller.show()

    def set_page_visible(self, page: QtWidgets.QWidget, visible: bool) -> None:
        """Apply the legacy Show checkboxes to pages of the unified window."""
        try:
            index = self._pages.index(page)
        except ValueError:
            return
        if visible:
            self.plot_tab_widget.showTab(index)
            self.plot_tab_widget.setCurrentWidget(page)
            return
        if page is self.settings_page:
            return
        if self.plot_tab_widget.currentWidget() is page:
            self.plot_tab_widget.setCurrentWidget(self.settings_page)
        self.plot_tab_widget.hideTab(index)

    def prepare_for_teardown(self) -> None:
        """Disable delegated close handling before the manager tears this page down."""
        self._close_callback = None
        timer = getattr(self, "_check_view_mode_timer", None)
        if timer is not None:
            timer.stop()

    def closeEvent(self, event) -> None:
        """Delegate user-initiated MDI close requests to the acquisition manager."""
        close_callback = self._close_callback
        if close_callback is None:
            super().closeEvent(event)
            return
        event.ignore()
        close_callback()


class DecayWindow(AcquisitionPlotPage):
    """Page for displaying fluorescence decays."""

    def __init__(self, parent=None):
        super().__init__("Acquisition - Fluorescence Decays", parent=parent)
        self.decay_plot_widget = chiplot.Plot()
        self.decay_plot_widget.set_log(y=False)
        self.decay_plot_widget.set_labels(left="Counts", bottom="Time (ns)")
        self.decay_curves = [
            self.decay_plot_widget.line([], [], pen=color, width=2) for color in CHANNEL_COLORS[:4]
        ]

        self.qc_label = QtWidgets.QLabel("Bursts: — · Phasor: —")
        self.qc_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.qc_label.setToolTip(
            "Live quality numbers from the same photon pass as the decay:\n"
            "• Bursts — sliding-window burst search, as a count and a rate\n"
            "• Phasor — (g, s) of all micro times at the laser repetition rate"
        )
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.decay_plot_widget)
        layout.addWidget(self.qc_label)
        self.set_content(content)
        self.plot_controller = DecayPlotController(self)
        self.current_plot_controller = self.plot_controller

    def update_decays(self, decay_data):
        """Update the decay plots with new data."""
        for i, decay in enumerate(decay_data):
            if len(decay) > 0:
                self.decay_data[i] = decay
        self.update_decay_plot()

    def update_decay_plot(self):
        """Request a redraw from the acquisition manager."""
        manager = getattr(getattr(chisurf, "cs", None), "_acquisition_manager", None)
        if manager is not None:
            manager.update_decay_plot()


class CorrelationWindow(AcquisitionPlotPage):
    """Page for displaying correlation curves."""

    def __init__(self, parent=None):
        super().__init__("Acquisition - Correlation Curve", parent=parent)
        self.correlation_plot_widget = chiplot.Plot()
        self.correlation_plot_widget.set_log(x=True)
        self.correlation_plot_widget.set_labels(left="G(τ)", bottom="τ (ms)")
        self.correlation_curves = [
            self.correlation_plot_widget.line([], [], pen=color, width=2)
            for color in CHANNEL_COLORS[:4]
        ]
        self.set_content(self.correlation_plot_widget)
        self.plot_controller = CorrelationPlotController(self)
        self.current_plot_controller = self.plot_controller

    def update_correlation(self, times, amplitudes):
        """Update correlation curves with new data."""
        if times is not None and amplitudes is not None:
            self.correlation_times = times
            self.correlation_amplitudes = amplitudes
        self.update_correlation_plot()

    def update_correlation_plot(self):
        """Request a redraw from the acquisition manager."""
        manager = getattr(getattr(chisurf, "cs", None), "_acquisition_manager", None)
        if manager is not None:
            manager.update_correlation_plot()


class CountRateWindow(AcquisitionPlotPage):
    """Page for displaying count-rate traces."""

    def __init__(self, parent=None):
        super().__init__("Acquisition - Count Rate", parent=parent)
        self.count_rate_plot_widget = chiplot.Plot()
        self.count_rate_plot_widget.set_labels(left="Count Rate (cps)", bottom="Macrotime (s)")
        self.count_rate_plot_widget.set_compact(True)
        self.count_rate_plot_widget.set_axis_visible(top=False, right=False)
        self.count_rate_plot_widget.set_menu_enabled(False)
        self.count_rate_curves = [
            self.count_rate_plot_widget.line([], [], pen=color, width=2) for color in CHANNEL_COLORS
        ]
        self.mean_lines = []
        self.set_content(self.count_rate_plot_widget)
        self.plot_controller = CountRatePlotController(self)
        self.current_plot_controller = self.plot_controller

    def update_count_rate(self, time_data, count_rate_data):
        """Update count-rate data."""
        if time_data is not None and count_rate_data is not None:
            self.time_data = time_data
            self.count_rate_data = count_rate_data

    def update_count_rate_plot(self):
        """Request a redraw from the acquisition manager."""
        manager = getattr(getattr(chisurf, "cs", None), "_acquisition_manager", None)
        if manager is not None:
            manager.update_count_rate_plot()


class MCSWindow(AcquisitionPlotPage):
    """Page for displaying MCS traces."""

    def __init__(self, parent=None):
        super().__init__("Acquisition - MCS Trace", parent=parent)
        self.mcs_plot_widget = chiplot.Plot()
        self.mcs_plot_widget.set_labels(left="Intensity (counts)", bottom="Time (ms)")
        self.mcs_curve = self.mcs_plot_widget.line([], [], pen=(0, 150, 150), width=2)
        self.set_content(self.mcs_plot_widget)
        self.plot_controller = MCSPlotController(self)
        self.current_plot_controller = self.plot_controller


class MacrotimeWindow(AcquisitionPlotPage):
    """Page for displaying macrotime time-series data."""

    def __init__(self, parent=None):
        super().__init__("Acquisition - Macrotime Plot", parent=parent)
        self.macrotime_plot_widget = chiplot.Plot()
        self.macrotime_plot_widget.set_labels(left="Macrotime Difference", bottom="Time (s)")
        self.macrotime_curve = self.macrotime_plot_widget.line([], [], pen=(150, 75, 0), width=2)
        self.set_content(self.macrotime_plot_widget)
        self.plot_controller = MacrotimePlotController(self)
        self.current_plot_controller = self.plot_controller

    def update_macrotime(self, histogram_data):
        """Update macrotime data."""
        if histogram_data is not None:
            bins, counts = histogram_data
            self.macrotime_bins = bins
            self.macrotime_counts = counts
        self.update_macrotime_plot()

    def update_macrotime_plot(self):
        """Request a redraw from the acquisition manager."""
        manager = getattr(getattr(chisurf, "cs", None), "_acquisition_manager", None)
        if manager is not None:
            manager.update_macrotime_plot()
