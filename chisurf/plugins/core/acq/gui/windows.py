"""Window classes for SM Acquisition plugin."""

import numpy as np
from qtpy.QtWidgets import (
    QMdiSubWindow,
    QDockWidget,
    QGroupBox,
    QGridLayout,
    QComboBox,
    QCheckBox,
    QToolButton,
    QSpinBox,
    QDoubleSpinBox,
    QProgressBar,
    QLabel,
    QLCDNumber,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qtpy.QtGui import QFont
from qtpy.QtCore import Qt
from chisurf.gui import chiplot
import chisurf
from chisurf.gui.widgets.mdi_custom_titlebar import CustomMdiSubWindow
from .controllers import (
    DecayPlotController,
    CorrelationPlotController,
    CountRatePlotController,
    MCSPlotController,
    MacrotimePlotController,
)


#: Per-channel curve colours, shared by every acquisition window so that
#: channel 2 is the same colour in the decay, the count rate and the
#: correlation. The fifth is the "All" trace of the count-rate window.
CHANNEL_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (128, 128, 128),
]


class DecayWindow(CustomMdiSubWindow):
    """Window for displaying fluorescence decays."""

    def __init__(self, parent=None):
        """Initialize the decay window."""
        super().__init__(title="Acquisition - Fluorescence Decays", parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Create the decay plot widget - single plot instead of stacked
        self.decay_plot_widget = chiplot.Plot()
        self.decay_plot_widget.set_log(y=False)  # Linear scale to show zeros
        self.decay_plot_widget.set_labels(left='Counts', bottom='Time (ns)')

        # Create curves for each channel (4 channels)
        self.decay_curves = [
            self.decay_plot_widget.line([], [], pen=color, width=2)
            for color in CHANNEL_COLORS[:4]
        ]

        # Two live quality numbers that cost nothing to have: the photons are
        # already being pushed through the decay histogram, so the phasor and
        # the burst search ride along on the same pass. They belong beside the
        # decay because that is the window an operator watches while aligning.
        self.qc_label = QLabel("Bursts: — · Phasor: —")
        self.qc_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qc_label.setToolTip(
            "Live quality numbers from the same photon pass as the decay:\n"
            "• Bursts — sliding-window burst search, as a count and a rate\n"
            "• Phasor — (g, s) of all micro times at the laser repetition rate"
        )

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.decay_plot_widget)
        layout.addWidget(self.qc_label)

        # Set the plot widget as content
        self.set_content(content)

        # Set reasonable default size from settings (same as fit windows)
        xs, ys = chisurf.settings.gui['fit_windows_size']
        self.resize(xs, ys)

        # Add dummy attributes to prevent AttributeError in main window
        self.fit = None
        self.fit_widget = None

        # Create plot controller and parent it to this window so it survives
        # layout changes when the main GUI switches contexts.
        self.plot_controller = DecayPlotController(self)

        # Set current_plot_controller after plot_controller is created
        self.current_plot_controller = self.plot_controller

    def closeEvent(self, event):
        """Handle window close event."""
        # Update checkbox state when window is closed
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            chisurf.cs._acquisition_manager.acquisition_dock.show_decay_checkbox.setChecked(False)
        event.accept()

    def update_decays(self, decay_data):
        """Update the decay plots with new data."""
        for i, decay in enumerate(decay_data):
            if len(decay) > 0:
                self.decay_data[i] = decay

        # Update the plot using controller settings
        self.update_decay_plot()

    def update_decay_plot(self):
        """Update the decay plot based on controller settings."""
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            manager = chisurf.cs._acquisition_manager
            manager.update_decay_plot()


class CorrelationWindow(CustomMdiSubWindow):
    """Window for displaying correlation curves."""

    def __init__(self, parent=None):
        """Initialize the correlation window."""
        super().__init__(title="Acquisition - Correlation Curve", parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Create the correlation plot widget
        self.correlation_plot_widget = chiplot.Plot()
        self.correlation_plot_widget.set_log(x=True)
        self.correlation_plot_widget.set_labels(left='G(\u03c4)', bottom='\u03c4 (ms)')

        # Create curves for each correlation (4 curves)
        self.correlation_curves = [
            self.correlation_plot_widget.line([], [], pen=color, width=2)
            for color in CHANNEL_COLORS[:4]
        ]

        # Set the plot widget as content
        self.set_content(self.correlation_plot_widget)

        # Set reasonable default size from settings (same as fit windows)
        xs, ys = chisurf.settings.gui['fit_windows_size']
        self.resize(xs, ys)

        # Add dummy attributes to prevent AttributeError in main window
        self.fit = None
        self.fit_widget = None

        # Create plot controller
        self.plot_controller = CorrelationPlotController(self)

        # Set current_plot_controller after plot_controller is created
        self.current_plot_controller = self.plot_controller

    def closeEvent(self, event):
        """Handle window close event."""
        # Update checkbox state when window is closed
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            chisurf.cs._acquisition_manager.acquisition_dock.show_correlation_checkbox.setChecked(False)
        event.accept()

    def update_correlation(self, times, amplitudes):
        """Update the correlation plot with new data."""
        if times is not None and amplitudes is not None:
            self.correlation_times = times
            self.correlation_amplitudes = amplitudes

        # Update the plot using controller settings
        self.update_correlation_plot()

    def update_correlation_plot(self):
        """Update the correlation plot based on controller settings."""
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            manager = chisurf.cs._acquisition_manager
            manager.update_correlation_plot()


class CountRateWindow(CustomMdiSubWindow):
    """Window for displaying count rate traces."""

    def __init__(self, parent=None):
        """Initialize the count rate window."""
        super().__init__(title="Acquisition - Count Rate", parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Create the count rate plot widget
        self.count_rate_plot_widget = chiplot.Plot()
        self.count_rate_plot_widget.set_labels(
            left='Count Rate (cps)', bottom='Macrotime (s)')
        # The count-rate panel is a strip, not a figure: no spare chrome.
        self.count_rate_plot_widget.set_compact(True)
        self.count_rate_plot_widget.set_axis_visible(top=False, right=False)
        self.count_rate_plot_widget.set_menu_enabled(False)

        # Create curves for each channel (4 channels) plus "All"
        # 4 channels + 1 for "All"
        self.count_rate_curves = [
            self.count_rate_plot_widget.line([], [], pen=color, width=2)
            for color in CHANNEL_COLORS
        ]

        # Store horizontal mean lines
        self.mean_lines = []

        # Set the plot widget as content
        self.set_content(self.count_rate_plot_widget)

        # Set reasonable default size from settings (same as fit windows)
        xs, ys = chisurf.settings.gui['fit_windows_size']
        self.resize(xs, ys)

        # Add dummy attributes to prevent AttributeError in main window
        self.fit = None
        self.fit_widget = None

        # Create plot controller
        self.plot_controller = CountRatePlotController(self)

        # Set current_plot_controller after plot_controller is created
        self.current_plot_controller = self.plot_controller

    def closeEvent(self, event):
        """Handle window close event."""
        # Update checkbox state when window is closed
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            chisurf.cs._acquisition_manager.acquisition_dock.show_count_rate_checkbox.setChecked(False)
        event.accept()

    def update_count_rate(self, time_data, count_rate_data):
        """Update the count rate plot with new data."""
        if time_data is not None and count_rate_data is not None:
            self.time_data = time_data
            self.count_rate_data = count_rate_data

    def update_count_rate_plot(self):
        """Update the count rate plot based on controller settings."""
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            manager = chisurf.cs._acquisition_manager
            manager.update_count_rate_plot()


class MCSWindow(CustomMdiSubWindow):
    """Window for displaying MCS trace."""

    def __init__(self, parent=None):
        """Initialize the MCS window."""
        super().__init__(title="Acquisition - MCS Trace", parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Create the MCS plot widget
        self.mcs_plot_widget = chiplot.Plot()
        self.mcs_plot_widget.set_labels(left='Intensity (counts)', bottom='Time (ms)')

        self.mcs_curve = self.mcs_plot_widget.line([], [], pen=(0, 150, 150), width=2)

        # Set the plot widget as content
        self.set_content(self.mcs_plot_widget)

        # Set reasonable default size
        xs, ys = chisurf.settings.gui['fit_windows_size']
        self.resize(xs, ys)

        # Create plot controller
        self.plot_controller = MCSPlotController(self)

        # Set current_plot_controller after plot_controller is created
        self.current_plot_controller = self.plot_controller

    def closeEvent(self, event):
        """Handle window close event."""
        # Update checkbox state when window is closed
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            chisurf.cs._acquisition_manager.acquisition_dock.show_mcs_checkbox.setChecked(False)
        event.accept()


class MacrotimeWindow(CustomMdiSubWindow):
    """Window for displaying macrotime time series plot."""

    def __init__(self, parent=None):
        """Initialize the macrotime window."""
        super().__init__(title="Acquisition - Macrotime Plot", parent=parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # Create the macrotime plot widget
        self.macrotime_plot_widget = chiplot.Plot()
        self.macrotime_plot_widget.set_labels(
            left='Macrotime Difference', bottom='Time (s)')

        self.macrotime_curve = self.macrotime_plot_widget.line(
            [], [], pen=(150, 75, 0), width=2)

        # Set the plot widget as content
        self.set_content(self.macrotime_plot_widget)

        # Set reasonable default size from settings (same as fit windows)
        xs, ys = chisurf.settings.gui['fit_windows_size']
        self.resize(xs, ys)

        # Add dummy attributes to prevent AttributeError in main window
        self.fit = None
        self.fit_widget = None

        # Create plot controller
        self.plot_controller = MacrotimePlotController(self)

        # Set current_plot_controller after plot_controller is created
        self.current_plot_controller = self.plot_controller

    def closeEvent(self, event):
        """Handle window close event."""
        # Update checkbox state when window is closed
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            chisurf.cs._acquisition_manager.acquisition_dock.show_macrotime_checkbox.setChecked(False)
        event.accept()

    def update_macrotime(self, histogram_data):
        """Update the macrotime plot with new histogram data."""
        if histogram_data is not None:
            bins, counts = histogram_data
            self.macrotime_bins = bins
            self.macrotime_counts = counts

        # Update the plot using controller settings
        self.update_macrotime_plot()

    def update_macrotime_plot(self):
        """Update the macrotime plot based on controller settings."""
        import chisurf
        if hasattr(chisurf.cs, '_acquisition_manager'):
            manager = chisurf.cs._acquisition_manager
            manager.update_macrotime_plot()
