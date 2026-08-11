# Main acquisition classes for SM Acquisition plugin

import json
import copy
from pathlib import Path

import logging
import time
import numpy as np
from chisurf.gui import dialogs
from chisurf.gui.widgets.system_info_watermark import memory_usage_mb, total_memory_mb

from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLCDNumber,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSpinBox,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy
)
from qtpy.QtCore import QThread, Qt, QTimer, Signal

import queue
import threading

from chisurf import settings
from chisurf.gui import chiplot
import tttrlib

from .windows import DecayWindow, CorrelationWindow, CountRateWindow, MCSWindow, MacrotimeWindow
from ..tcspc_devices import TCSPCDevice, BHSPCCardSetupDialog
from ..pipeline import AcquisitionPipeline, PipelineConfig, record_type_for_device


logger = logging.getLogger(__name__)


def _default_acquisition_output_path() -> str:
    """Return the configured acquisition output folder or a fallback path."""
    acq_cfg = getattr(settings, "gui", {}).get("acquisition", {})
    configured = str(acq_cfg.get("output_path", "") or "").strip()
    if configured:
        return str(Path(configured).expanduser())

    working_path = getattr(settings, "working_path", "") or ""
    if working_path:
        return str(Path(working_path).expanduser() / "acquisition")

    return str(Path.home() / "chisurf" / "acquisition")


class AcquisitionThread(QThread):
    """Thread for acquiring data from the TCSPC device."""

    data_ready = Signal(object)
    acquisition_complete = Signal()
    error = Signal(str)

    def __init__(self, device, duration, parent=None, chunk_size=32768):
        """Initialize the acquisition thread.

        Args:
            device (TCSPCDevice): The TCSPC device to acquire data from.
            duration (float): The duration of the acquisition in seconds.
            parent (QObject): The parent object.
            chunk_size (int): Number of 16-bit words to read per chunk.
        """
        super().__init__(parent)
        self.device = device
        self.duration = duration
        self.chunk_size = chunk_size
        self.running = False
        self.data = []

    def run(self):
        """Run the acquisition thread."""
        self.running = True
        self.data = []

        try:
            if not self.device.start_measurement():
                self.error.emit("Failed to start measurement")
                return

            start_time = time.monotonic()
            buf_size = self.chunk_size  # Use configurable chunk size

            while self.running:
                elapsed = time.monotonic() - start_time
                if elapsed >= self.duration:
                    logger.info(f"Time limit reached ({elapsed:.1f} s / {self.duration:.1f} s), stopping measurement")
                    self.device.stop_measurement()
                    break

                # Read data from device
                buf = self.device.read_fifo(buf_size)
                if buf is not None and len(buf):
                    logger.debug(f"Read {len(buf)} words from device")
                    self.data.append(buf)
                    self.data_ready.emit(buf)
                else:
                    logger.debug("No data read from device")

                # Check if we should stop before sleeping
                if not self.running:
                    break

                if buf is None or len(buf) < buf_size:
                    # We've read all there is to read, wait a bit
                    time.sleep(0.001)
                else:
                    # We read a full chunk. Sleep briefly to prevent flooding the
                    # main thread's event loop, especially during simulation.
                    time.sleep(0.005)

            # Make sure to read the data that arrived after stopping
            while True:
                buf = self.device.read_fifo(buf_size)
                if buf is None or not len(buf):
                    break
                self.data.append(buf)
                self.data_ready.emit(buf)

            self.acquisition_complete.emit()

        except Exception as e:
            self.error.emit(f"Error during acquisition: {e}")
            try:
                self.device.stop_measurement()
            except:
                pass

        self.running = False

    def stop(self):
        """Stop the acquisition thread."""
        try:
            # First stop the device measurement to interrupt any blocking read operations
            if hasattr(self, 'device') and self.device is not None:
                try:
                    self.device.stop_measurement()
                except Exception as e:
                    print(f"Error stopping device measurement: {e}")

            # Then set the running flag to False
            self.running = False

            # Don't call wait() here - let the caller handle thread cleanup
            # This prevents issues when stop() is called from signal handlers
        except Exception as e:
            print(f"Error in AcquisitionThread.stop(): {e}")

    def get_data(self):
        """Get the acquired data.

        Returns:
            numpy.ndarray: Array of 32-bit records.
        """
        if not self.data:
            return np.array([], dtype=np.uint32)
        return np.concatenate(self.data)


class DataProcessingThread(QThread):
    """Background thread around the acquisition pipeline.

    The thread owns the queue and the Qt signals; everything that happens to a
    photon lives in :class:`~chisurf.plugins.core.acq.pipeline.AcquisitionPipeline`,
    which is Qt-free and is what the tests drive. There used to be a second
    copy of the decode -> accumulate -> histogram -> correlate loop on the
    manager itself, and the two drifted: the manager decoded B&H records with
    the photon library while this thread's base-class fallback bit-shifted them
    by hand. One pipeline, one decoder, one place a defect can be.

    Signals
    -------
    results_ready : Signal()
        New display state is available; the GUI polls :meth:`get_results`.
    stop_requested : Signal(str)
        A configured stop condition (time or photon count) was met.
    """

    results_ready = Signal()
    stop_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = queue.Queue(maxsize=50)
        self._results_lock = threading.Lock()
        self._results = None
        self._running = False
        self._pipeline = None
        self._stop_emitted = False

        # Configuration, applied to the pipeline when the acquisition starts.
        self._record_type = tttrlib.RECORD_SPC130
        self._macrotime_clock = 50e-9
        self._channel_mapping = [8, 9, 10, 0]
        self._mcs_bin_width_ms = 1.0
        self._mcs_rollaround_ms = 1000.0
        self._time_limit = 0.0
        self._photon_limit = 0
        self._correlation_pairs = [(0, 0, 0)]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, **kwargs):
        """Set processing parameters (call before :meth:`reset`)."""
        for k, v in kwargs.items():
            attr = f'_{k}'
            if hasattr(self, attr):
                setattr(self, attr, v)

    def set_correlation_pairs(self, pairs):
        """Set which channel pairs to correlate.

        Parameters
        ----------
        pairs : list of (curve_idx, ch_a, ch_b)
        """
        self._correlation_pairs = list(pairs)

    def reset(self):
        """Build a pipeline for a new acquisition and drain anything stale."""
        self._pipeline = AcquisitionPipeline(
            PipelineConfig(
                record_type=self._record_type,
                macrotime_clock=self._macrotime_clock,
                channels=tuple(self._channel_mapping[:4]),
                correlation_pairs=tuple(self._correlation_pairs),
                mcs_bin_width_ms=self._mcs_bin_width_ms,
                mcs_rollaround_ms=self._mcs_rollaround_ms,
                time_limit_s=self._time_limit,
                photon_limit=self._photon_limit,
            )
        )
        self._stop_emitted = False

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._results_lock:
            self._results = None

    @property
    def pipeline(self):
        """The pipeline this thread feeds, or ``None`` before :meth:`reset`."""
        return self._pipeline

    # ------------------------------------------------------------------
    # Thread control
    # ------------------------------------------------------------------

    def submit(self, raw_data):
        """Submit raw TCSPC records for processing (thread-safe)."""
        try:
            self._queue.put_nowait(raw_data)
        except queue.Full:
            logger.warning("DataProcessingThread queue full, dropping chunk")

    def get_results(self):
        """Return the latest display state (thread-safe, non-blocking)."""
        with self._results_lock:
            return self._results

    def stop(self):
        """Ask the thread to finish."""
        self._running = False

    def flush(self):
        """Close out the run — the correlators emit their last bin."""
        if self._pipeline is not None:
            self._pipeline.flush()
            self._store_results()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self._running = True
        while self._running:
            try:
                raw_data = self._queue.get(timeout=0.01)
            except queue.Empty:
                continue
            try:
                self._process_chunk(raw_data)
            except Exception as e:
                logger.error("DataProcessingThread error: %s", e, exc_info=True)

    def _process_chunk(self, data):
        if self._pipeline is None:
            return
        if self._pipeline.push(data) == 0:
            return
        self._store_results()
        reason = self._pipeline.stop_reason
        if reason and not self._stop_emitted:
            self._stop_emitted = True
            self.stop_requested.emit(reason)

    def _store_results(self):
        with self._results_lock:
            self._results = self._pipeline.snapshot()
        self.results_ready.emit()


class AcquisitionDockWidget(QDockWidget):
    """Dock widget for acquisition controls and settings."""

    def __init__(self, parent=None):
        """Initialize the acquisition dock widget."""
        super().__init__("Acquisition", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._create_contents()

    def _create_contents(self):
        """Create the dock widget contents."""
        # Control panel
        control_panel = QGroupBox("Control Panel")
        control_layout = QGridLayout(control_panel)
        control_layout.setSpacing(0)
        control_layout.setContentsMargins(0, 0, 0, 0)

        # Device initialization
        self.device_type_combo = QComboBox()
        # Prefer Simulation first for quick testing, then hardware devices
        self.device_type_combo.addItem("Simulation")
        self.device_type_combo.addItem("BH SPC 830")
        self.device_type_combo.addItem("PicoQuant")
        # Acquisition parameters (global stop conditions)
        # Time limit (seconds). 0 disables time-based stopping.
        self.duration_spinbox = QDoubleSpinBox()
        self.duration_spinbox.setRange(0.0, 36000.0)
        self.duration_spinbox.setValue(900.0)
        self.duration_spinbox.setSuffix(" s")

        # Photon-count limit in kilo-photons (kPh). 0 disables photon-based stopping.
        self.photon_limit_spinbox = QDoubleSpinBox()
        # 0 = disabled, otherwise value is in kPh (1 kPh = 1000 photons)
        self.photon_limit_spinbox.setRange(0.0, 1e6)  # Up to 1e9 photons
        self.photon_limit_spinbox.setDecimals(0)
        self.photon_limit_spinbox.setSingleStep(5.0)
        self.photon_limit_spinbox.setValue(20.0)  # Default 20 kPh
        self.photon_limit_spinbox.setSuffix(" k photons")
        self.photon_limit_spinbox.setToolTip("Photon stop limit in kilo-photons (kPh). 0 disables photon-based stopping.")


        self.start_button = QToolButton()
        self.start_button.setText("Start")
        self.start_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.start_button.setEnabled(True)

        self.stop_button = QToolButton()
        self.stop_button.setText("Stop")
        self.stop_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stop_button.setEnabled(False)

        # Channel selection
        self.channel_spinboxes = []
        for i in range(4):
            spinbox = QSpinBox()
            spinbox.setRange(0, 15)
            spinbox.setValue(i)
            self.channel_spinboxes.append(spinbox)

        # Next row: stop conditions (time and/or number of photons) and Start/Stop
        control_layout.addWidget(QLabel("Time [s]:"), 0, 0)
        control_layout.addWidget(self.duration_spinbox, 0, 1)
        control_layout.addWidget(QLabel("Nbr Ph [k]:"), 0, 2)
        control_layout.addWidget(self.photon_limit_spinbox, 0, 3)
        control_layout.addWidget(self.start_button, 0, 4)
        control_layout.addWidget(self.stop_button, 0, 5)

        # Optional Simulation Setup button (will be dynamically shown/hidden)
        self.sim_setup_button = QToolButton()
        self.sim_setup_button.setText("Simulation Setup...")
        self.sim_setup_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control_layout.addWidget(self.sim_setup_button, 1, 0, 1, 6)
        self.sim_setup_button.setVisible(False)

        # Status row directly below the controls
        status_layout = QHBoxLayout()
        status_layout.setSpacing(0)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        # Set initial status text in progress bar
        self.progress_bar.setFormat("Status: Ready (auto-init on Start)")
        status_layout.addWidget(self.progress_bar)

        self.count_rate_lcd = QLCDNumber()
        self.count_rate_lcd.setDigitCount(8)
        self.count_rate_lcd.setSegmentStyle(QLCDNumber.Flat)
        self.count_rate_lcd.display(0.0)
        status_layout.addWidget(self.count_rate_lcd)

        control_layout.addLayout(status_layout, 3, 0, 1, 6)

        # Output folder (shown below status)
        output_layout = QHBoxLayout()
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(4)

        output_label = QLabel("Output folder:")
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Optional folder for SPC/TTTR output")
        self.output_path_edit.setText(_default_acquisition_output_path())
        self.output_browse_button = QToolButton()
        self.output_browse_button.setText("...")
        self.output_browse_button.clicked.connect(self._browse_output_path)

        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.output_browse_button)

        control_layout.addLayout(output_layout, 4, 0, 1, 4)

        # Add JSON save/load buttons
        json_layout = QHBoxLayout()
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.setSpacing(4)

        self.save_json_button = QToolButton()
        self.save_json_button.setText("Save Settings")
        self.save_json_button.setToolTip("Save acquisition settings to JSON file")
        self.save_json_button.clicked.connect(lambda: self.parent().save_settings_json() if hasattr(self.parent(), 'save_settings_json') else None)

        self.load_json_button = QToolButton()
        self.load_json_button.setText("Load Settings")
        self.load_json_button.setToolTip("Load acquisition settings from JSON file")
        self.load_json_button.clicked.connect(lambda: self.parent().load_settings_json() if hasattr(self.parent(), 'load_settings_json') else None)

        json_layout.addWidget(self.save_json_button)
        json_layout.addWidget(self.load_json_button)

        control_layout.addLayout(json_layout, 4, 4, 1, 2)

        # Show windows controls (compact grid layout)
        windows_group = QGroupBox("Show")
        windows_layout = QGridLayout(windows_group)
        windows_layout.setSpacing(2)
        windows_layout.setContentsMargins(2, 2, 2, 2)

        self.show_decay_checkbox = QCheckBox("Fluorescence Decays")
        self.show_decay_checkbox.setChecked(True)
        self.show_correlation_checkbox = QCheckBox("Correlation Curve")
        self.show_correlation_checkbox.setChecked(True)
        self.show_count_rate_checkbox = QCheckBox("Count Rate")
        self.show_count_rate_checkbox.setChecked(True)
        self.show_macrotime_checkbox = QCheckBox("Macrotime Plot")
        self.show_macrotime_checkbox.setChecked(False)  # Default off since it's new
        self.show_mcs_checkbox = QCheckBox("MCS Trace")
        self.show_mcs_checkbox.setChecked(False)  # Default off since it's new

        windows_layout.addWidget(self.show_decay_checkbox, 0, 0)
        windows_layout.addWidget(self.show_correlation_checkbox, 0, 1)
        windows_layout.addWidget(self.show_count_rate_checkbox, 1, 0)
        windows_layout.addWidget(self.show_macrotime_checkbox, 1, 1)
        windows_layout.addWidget(self.show_mcs_checkbox, 2, 0)

        # Row 5, not 4: the output-folder row and the settings buttons already
        # occupy row 4, and a QGridLayout silently draws overlapping cells on
        # top of each other rather than complaining.
        control_layout.addWidget(windows_group, 5, 0, 1, 6)

        # Spare height goes to the empty row above the status bar. Without this
        # the grid shares it out evenly and the five checkboxes below end up in
        # a group box taller than the controls it belongs to.
        for row in (0, 1, 3, 4, 5):
            control_layout.setRowStretch(row, 0)
        control_layout.setRowStretch(2, 1)

        self.setWidget(control_panel)

    def _recreate_contents(self):
        """Recreate the dock widget contents if they were deleted."""
        logger.info("Recreating dock widget contents...")
        self._create_contents()

    def _browse_output_path(self):
        """Open a dialog to select an output folder for saving data files."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            self.output_path_edit.text() or _default_acquisition_output_path(),
        )
        if path:
            self.output_path_edit.setText(path)

    # Convenience properties for accessing core UI values

    @property
    def duration(self) -> float:
        """Acquisition duration in seconds."""
        return float(self.duration_spinbox.value())

    @duration.setter
    def duration(self, value: float) -> None:
        self.duration_spinbox.setValue(float(value))

    @property
    def photon_limit(self) -> int:
        """Photon-count limit in photons (0 disables).

        The UI spinbox is expressed in kilo-photons (kPh). 0 means disabled.
        Any non-zero value less than 5 kPh is clamped to 5 kPh.
        """
        kph = float(self.photon_limit_spinbox.value())
        if 0.0 < kph < 5:
            kph = 5
        return kph * 1000

    @photon_limit.setter
    def photon_limit(self, value: int) -> None:
        # Value is given in photons; convert to kPh for the UI spinbox.
        if value <= 0:
            self.photon_limit_spinbox.setValue(0.0)
        else:
            kph = float(value) / 1000
            if 0.0 < kph < 5.0:
                kph = 5.0
            self.photon_limit_spinbox.setValue(kph)

    @property
    def output_path(self) -> str:
        """Output folder path for SPC/TTTR data."""
        return self.output_path_edit.text()

    @output_path.setter
    def output_path(self, value: str) -> None:
        self.output_path_edit.setText(value)

    @property
    def show_decay(self) -> bool:
        return self.show_decay_checkbox.isChecked()

    @show_decay.setter
    def show_decay(self, value: bool) -> None:
        self.show_decay_checkbox.setChecked(bool(value))

    @property
    def show_correlation(self) -> bool:
        return self.show_correlation_checkbox.isChecked()

    @show_correlation.setter
    def show_correlation(self, value: bool) -> None:
        self.show_correlation_checkbox.setChecked(bool(value))

    @property
    def show_count_rate(self) -> bool:
        return self.show_count_rate_checkbox.isChecked()

    @show_count_rate.setter
    def show_count_rate(self, value: bool) -> None:
        self.show_count_rate_checkbox.setChecked(bool(value))

    @property
    def show_macrotime(self) -> bool:
        return self.show_macrotime_checkbox.isChecked()

    @show_macrotime.setter
    def show_macrotime(self, value: bool) -> None:
        self.show_macrotime_checkbox.setChecked(bool(value))

    @property
    def show_mcs(self) -> bool:
        return self.show_mcs_checkbox.isChecked()

    @show_mcs.setter
    def show_mcs(self, value: bool) -> None:
        self.show_mcs_checkbox.setChecked(bool(value))

    def closeEvent(self, event):
        """When the dock is closed, close acquisition mode."""
        # Close acquisition mode without additional confirmation
        try:
            manager = None
            parent = self.parent()
            if parent is not None and hasattr(parent, '_acquisition_manager'):
                manager = getattr(parent, '_acquisition_manager', None)
            else:
                try:
                    import chisurf
                    if hasattr(chisurf.cs, '_acquisition_manager'):
                        manager = chisurf.cs._acquisition_manager
                except Exception:
                    manager = None

            if manager is not None and hasattr(manager, 'close_acquisition_mode'):
                manager.close_acquisition_mode()
        except Exception as e:
            logger.warning(f"Error closing acquisition mode from dock closeEvent: {e}")

        event.accept()


class SMAcquisitionManager:
    """Manager for Single-Molecule Acquisition components."""

    def __init__(self, standalone_main_window=None):
        """Initialize the acquisition manager.

        Args:
            standalone_main_window: If provided, use this as main window instead of chisurf
        """
        # Find a window to host the acquisition views. The question is whether a
        # main window *exists*, not whether chisurf imports: chisurf always
        # imports, but ``chisurf.cs`` is None until the GUI builds its main
        # window, so keying on ImportError made this crash at
        # ``self.main_window._acquisition_manager = self`` whenever the tool was
        # opened without one (headless, a test, or before the window is up).
        try:
            import chisurf
            host = getattr(chisurf, 'cs', None)
        except ImportError:
            host = None
        self.chisurf_available = host is not None
        if host is None:
            host = standalone_main_window
        self.main_window = host
        logger.info(
            "Running in chisurf mode" if self.chisurf_available
            else "Running in standalone mode" if host is not None
            else "Running without a host window; the acquisition views stay free-floating"
        )

        # Check if acquisition manager already exists
        if self.main_window is not None and hasattr(self.main_window, '_acquisition_manager'):
            logger.warning("SM Acquisition manager already exists, not creating another instance")
            # Maybe bring the existing windows to front or show a message
            if hasattr(self.main_window, '_acquisition_manager') and self.main_window._acquisition_manager:
                existing_manager = self.main_window._acquisition_manager
                # Bring existing windows to front
                try:
                    existing_manager.decay_window.raise_()
                    existing_manager.decay_window.activateWindow()
                except:
                    pass
                try:
                    existing_manager.correlation_window.raise_()
                    existing_manager.correlation_window.activateWindow()
                except:
                    pass
                try:
                    existing_manager.count_rate_window.raise_()
                    existing_manager.count_rate_window.activateWindow()
                except:
                    pass
            return

        # Initialize device
        # Start with a Simulation device so it matches the default selection
        # in the GUI's device_type_combo ("Simulation"). This will be
        # immediately updated by on_device_type_changed below if the combo
        # is changed or settings are loaded.
        self.device = TCSPCDevice("SIMULATION")
        self.data = None
        self.decay_data = [np.zeros(4096) for _ in range(4)]
        self.correlation_data = None
        self.correlation_times = None
        self.correlation_amplitudes = None
        self.mean_countrate = 0.0
        self.start_time = 0.0
        self._last_results = None

        # Simulation mode (default to True)
        self.simulation_mode = True

        # There are deliberately no photon arrays here. The manager holds
        # display state only; the photons live in the streaming consumers
        # inside the pipeline, which never keep them either. Three growing
        # arrays used to sit at this spot and were `np.concatenate`-d on every
        # chunk — O(N^2) copying, unbounded RAM, and the reason the plugin's
        # feature list advertises "RAM usage monitoring".
        self.total_photons = 0

        # Count rate data
        self.count_rate_times = []
        self.count_rate_data = [[] for _ in range(5)]
        self.count_rate_update_counter = 0
        self.last_count_rate_time = 0.0

        # Device timing parameters
        self.macrotime_clock = 50e-9  # Default 50 ns (20 MHz), will be updated from device
        # ns per TAC channel; None until a device says, and then the decay
        # window's axis is TAC channels rather than invented nanoseconds.
        self.microtime_resolution_ns = None

        # Macrotime data for plotting
        self.macrotime_data = []  # List of macrotime values (dt differences)
        self.macrotime_times = []  # Corresponding time points for plotting

        # MCS trace data
        self.mcs_trace = None  # MCS trace histogram (bins, counts)
        self.mcs_bin_width_ms = 1.0  # Bin width in milliseconds (default 1ms)
        self.mcs_rollaround_time_ms = 1000.0  # Rollaround time in milliseconds (default 1s)

        # Update frequency counters
        self.decay_update_counter = 0
        self.correlation_update_counter = 0
        self.macrotime_update_counter = 0

        # Create UI components
        self.decay_window = DecayWindow()
        self.correlation_window = CorrelationWindow()
        self.count_rate_window = CountRateWindow()
        self.macrotime_window = MacrotimeWindow()
        self.mcs_window = MCSWindow()
        self.acquisition_dock = AcquisitionDockWidget(self.main_window)

        # Store reference in main window
        if self.main_window is not None:
            self.main_window._acquisition_manager = self

        # Connect signals
        self.setup_connections()

        # Read device timing parameters
        self._read_device_timing_parameters()

        # Add to main window
        if self.chisurf_available:
            # chisurf mode - use MDI area
            self.main_window.mdiarea.addSubWindow(self.decay_window)
            self.main_window.mdiarea.addSubWindow(self.correlation_window)
            self.main_window.mdiarea.addSubWindow(self.count_rate_window)
            self.main_window.mdiarea.addSubWindow(self.macrotime_window)
            self.main_window.mdiarea.addSubWindow(self.mcs_window)
            self.main_window.addDockWidget(Qt.LeftDockWidgetArea, self.acquisition_dock)
        elif self.main_window is not None:
            # Standalone mode - use MDI area from standalone window
            if hasattr(self.main_window, 'mdiarea'):
                self.main_window.mdiarea.addSubWindow(self.decay_window)
                self.main_window.mdiarea.addSubWindow(self.correlation_window)
                self.main_window.mdiarea.addSubWindow(self.count_rate_window)
                self.main_window.mdiarea.addSubWindow(self.macrotime_window)
                self.main_window.mdiarea.addSubWindow(self.mcs_window)
                # For standalone, add dock as regular widget
                if hasattr(self.main_window, 'addDockWidget'):
                    self.main_window.addDockWidget(Qt.LeftDockWidgetArea, self.acquisition_dock)
                else:
                    # Fallback: add to central widget
                    self.main_window.centralWidget().layout().addWidget(self.acquisition_dock)

        # Show windows
        self.decay_window.show()
        self.correlation_window.show()
        self.count_rate_window.show()
        self.acquisition_dock.show()  # Make sure dock is visible

    def show(self):
        """Bring all acquisition windows to front."""
        self.decay_window.show()
        self.correlation_window.show()
        self.count_rate_window.show()
        self.acquisition_dock.show()
        self.raise_()
        self.activateWindow()

    def raise_(self):
        """Raise all acquisition windows."""
        for w in [self.decay_window, self.correlation_window, self.count_rate_window, self.acquisition_dock]:
            try:
                w.raise_()
            except Exception:
                pass

    def activateWindow(self):
        """Activate the primary acquisition window."""
        try:
            self.decay_window.activateWindow()
        except Exception:
            pass

    def _read_device_timing_parameters(self):
        """Read timing parameters from the device and update instance variables."""
        try:
            if self.device.device_type == "BH_SPC" and self.device.initialized:
                # For BH SPC devices, read the macrotime clock parameter
                # The macrotime clock is typically derived from the master clock and divider
                # For now, we'll try to read MACRO_TIME_CLK parameter
                try:
                    from ..tcspc_devices.bh_spc.wrapper import ParID
                    if hasattr(self.device.device, 'get_parameter') and self.device.active_cards:
                        mod_no = self.device.active_cards[0]  # Use first active card
                        macrotime_clock_param = self.device.device.get_parameter(mod_no, ParID.MACRO_TIME_CLK)
                        if macrotime_clock_param > 0:
                            # Convert from parameter value to actual time in seconds
                            # BH SPC macrotime clock parameter is typically in units of 50 ps (0.05 ns)
                            self.macrotime_clock = macrotime_clock_param * 50e-12  # Convert to seconds
                            logger.info(f"Read macrotime clock from BH SPC: {self.macrotime_clock*1e9:.1f} ns")
                        else:
                            logger.warning("Invalid macrotime clock parameter, using default")
                    else:
                        logger.info("Cannot read macrotime clock from BH SPC device, using default: 50 ns")
                except Exception as e:
                    logger.error(f"Error reading macrotime clock from BH SPC device: {e}")
                    logger.info("Using default macrotime clock: 50 ns")
                logger.info(f"PicoQuant macrotime clock: {self.macrotime_clock*1e12:.0f} ps ({1/(self.macrotime_clock*1e-6):.0f} MHz)")
            elif self.device.device_type == "SIMULATION":
                # For simulation, use the same timing as BH_SPC devices since the DLL
                # produces BH_SPC compatible data with realistic timing
                self.macrotime_clock = 50e-9  # 50 ns (same as BH_SPC default)
                logger.info(f"Simulation macrotime clock: {self.macrotime_clock*1e9:.1f} ns")
            else:
                logger.info(f"Unknown device type {self.device.device_type}, using default macrotime clock: {self.macrotime_clock*1e9:.1f} ns")

            # Micro-time (TAC) resolution, which sets the decay window's axis.
            # Only the simulator states it today; a card that cannot say keeps
            # the axis in TAC channels rather than inventing nanoseconds.
            self.microtime_resolution_ns = None
            sim_params = getattr(self.device, "simulation_params", None)
            if isinstance(sim_params, dict) and sim_params.get("tac_dt"):
                self.microtime_resolution_ns = float(sim_params["tac_dt"])
            try:
                self.decay_window.decay_plot_widget.set_labels(
                    bottom="Time (ns)" if self.microtime_resolution_ns
                    else "Micro time (TAC channel)"
                )
            except (AttributeError, RuntimeError):
                pass

            # Update GUI display if available
            if self.macrotime_clock < 1e-9:  # Less than 1 ns
                display_text = f"{self.macrotime_clock*1e12:.1f} ps"
            else:  # 1 ns or more
                display_text = f"{self.macrotime_clock*1e9:.1f} ns"

            self.acquisition_dock.macrotime_clock_label.setText(f"Macrotime Clock: {display_text}")
        except Exception as e:
            logger.debug(f"Could not update macrotime clock display: {e}")


    def setup_connections(self):
        """Set up signal-slot connections."""
        self.acquisition_dock.start_button.clicked.connect(self.start_acquisition)
        self.acquisition_dock.stop_button.clicked.connect(self.stop_acquisition)
        self.acquisition_dock.sim_setup_button.clicked.connect(self.open_card_setup)
        self.acquisition_dock.show_decay_checkbox.toggled.connect(self.toggle_decay_window)
        self.acquisition_dock.show_correlation_checkbox.toggled.connect(self.toggle_correlation_window)
        self.acquisition_dock.show_count_rate_checkbox.toggled.connect(self.toggle_count_rate_window)
        self.acquisition_dock.show_macrotime_checkbox.toggled.connect(self.toggle_macrotime_window)
        self.acquisition_dock.show_mcs_checkbox.toggled.connect(self.toggle_mcs_window)

        # Connect device log messages
        self.device.message_logged.connect(self._device_log_handler)

    @staticmethod
    def _safe_spinbox_value(spinbox, default_value):
        """Return spinbox value or default if widget was deleted."""
        if spinbox is None:
            return default_value

        try:
            return spinbox.value()
        except RuntimeError:
            return default_value

    def update_ui_for_device_type(self):
        """Update UI elements based on selected device type."""
        self.device_type = self.device.device_type
        
        # Show/hide Simulation Setup button
        if self.device_type == "Simulation":
            self.acquisition_dock.sim_setup_button.setVisible(True)
        else:
            self.acquisition_dock.sim_setup_button.setVisible(False)

        # Configure stop-condition semantics per device type
        time_sb = self.acquisition_dock.duration_spinbox
        ph_sb = self.acquisition_dock.photon_limit_spinbox

        # Time control is always in seconds for all devices
        time_sb.setDecimals(1)
        time_sb.setRange(0.0, 3600.0)
        time_sb.setSingleStep(0.1)
        time_sb.setSuffix(" s")

        # Photon limit spinbox works in kilo-photons (kPh); 0 disables.
        ph_sb.setDecimals(0)
        ph_sb.setRange(0.0, 1e6)
        ph_sb.setSingleStep(5.0)
        ph_sb.setSuffix(" kPh")

        if self.device_type == "Simulation":
            # Use larger defaults for simulation if not already set
            if ph_sb.value() <= 0:
                ph_sb.setValue(20.0)  # 20 kPh default for simulation

    def initialize_device(self):
        """Initialize the TCSPC device."""
        simulation = self.simulation_mode

        if self.device.initialized:
            self.device.close()

        # Initialize the device
        if self.device.initialize(simulation):
            # Get the active cards/devices
            active_cards = self.device.get_active_cards()

            if active_cards:
                device_type = self.acquisition_dock.device_type_combo.currentText()
                if device_type == "PicoQuant":
                    self._safe_set_status_text(f"Status: Initialized ({len(active_cards)} devices)")
                else:
                    self._safe_set_status_text(f"Status: Initialized ({len(active_cards)} cards)")
                logger.info(f"Active devices: {active_cards}")
                self._safe_set_button_enabled("start_button", True)
                self.acquisition_dock.initialize_button.setText("Init Device")
                self._safe_set_button_enabled("card_setup_button", True)
            else:
                self._safe_set_status_text("Status: Initialized (no active devices)")
                logger.info("No active devices detected")
                self._safe_set_button_enabled("start_button", False)
                self._safe_set_button_enabled("card_setup_button", True)

            # Read timing parameters from the device
            self._read_device_timing_parameters()

            return True
        else:
            self._safe_set_status_text("Status: Initialization failed")
            self._safe_set_button_enabled("start_button", False)
            self._safe_set_button_enabled("card_setup_button", False)

    def start_acquisition(self):
        """Start data acquisition."""
        # Read settings from central config
        from chisurf.settings import gui as gui_settings
        acq_config = gui_settings.get("acquisition", {})
        device_type = acq_config.get("device_type", "Simulation")

        # Re-create and initialize device if type changed or not initialized
        if self.device.device_type != device_type or not self.device.initialized:
            logger.info(f"Auto-initializing device type: {device_type}")
            if self.device.initialized:
                self.device.close()

            from chisurf.plugins.core.acq.tcspc_devices.device_factory import TCSPCDevice
            if device_type == "Becker-Hickl":
                self.device = TCSPCDevice("BH_SPC")
            elif device_type == "PicoQuant":
                self.device = TCSPCDevice("PICOQUANT")
            elif device_type == "Simulation":
                self.device = TCSPCDevice("SIMULATION")
            elif device_type == "BrickMic":
                self.device = TCSPCDevice("BRICKMIC")
            else:
                self.device = TCSPCDevice("SIMULATION")

            self.device.message_logged.connect(self._device_log_handler)
            if not self.device.initialize(simulation=self.simulation_mode):
                dialogs.error(self.main_window, "Error", f"Failed to initialize {device_type} device.")
                return

            self._read_device_timing_parameters()
            self.update_ui_for_device_type()

        # Check if acquisition is already running
        if getattr(self, '_acquisition_in_progress', False):
            dialogs.information(self.main_window, "Information", "Acquisition is already running")
            return

        # Read stop conditions
        time_limit = float(self.acquisition_dock.duration)
        photon_limit = float(self.acquisition_dock.photon_limit)

        # Require at least one active stop condition
        if time_limit <= 0.0 and photon_limit <= 0.0:
            dialogs.warning(self.main_window, "Warning", "Set a time and/or photon stop condition before starting acquisition")
            return

        # Persist limits for progress and photon-based stopping
        self._time_limit = max(0.0, time_limit)
        self._photon_limit = max(0, int(photon_limit))

        # Thread still uses a time duration; if disabled, use a very large sentinel
        thread_duration = self._time_limit if self._time_limit > 0.0 else 1e12

        # Set flag to prevent multiple starts
        self._acquisition_in_progress = True

        # Read settings from central config
        from chisurf.settings import gui as gui_settings
        acq_config = gui_settings.get("acquisition", {})
        
        chunk_size_photons = acq_config.get("chunk_size", 16384)
        chunk_size_words = chunk_size_photons * 2  # Convert photons to 16-bit words


        self.data = None
        self.decay_data = [np.zeros(4096) for _ in range(4)]
        self.correlation_data = None
        self.correlation_times = [None] * 4
        self.correlation_amplitudes = [None] * 4

        # Reset count rate data
        self.count_rate_times = []  # Time points for count rate plot
        self.count_rate_data = [[] for _ in range(5)]  # 4 channels + 1 for "All"
        self.count_rate_update_counter = 0
        self.last_count_rate_time = time.monotonic()  # Initialize for rate calculation
        self.last_channel_counts = [0, 0, 0, 0]  # Track photons per channel for rate calculation

        # Reset macrotime data
        self.macrotime_data = []
        self.macrotime_times = []
        self.mcs_trace = None
        self.macrotime_update_counter = 0

        # Reset update counters
        self.decay_update_counter = 0
        self.correlation_update_counter = 0
        self.mcs_update_counter = 0

        # Reset photon counter used for photon-based stop condition. The
        # overflow accumulator that used to live beside it belongs to the
        # decoder, which is the only thing that has ever needed it.
        self.total_photons = 0

        # Clear plots
        for i in range(4):
            self.decay_window.decay_curves[i].set_data([], [])
        for i in range(4):
            self.correlation_window.correlation_curves[i].set_data([], [])

        # Clear count rate plot and mean lines
        for i in range(5):
            self.count_rate_window.count_rate_curves[i].set_data([], [])
        for line in self.count_rate_window.mean_lines:
            line.remove()
        self.count_rate_window.mean_lines.clear()

        # Pass output folder and photon target to device/simulation where applicable
        output_path = (self.acquisition_dock.output_path or "").strip()
        if not output_path:
            output_path = _default_acquisition_output_path().strip()
            self.acquisition_dock.output_path = output_path
        device_type = self.acquisition_dock.device_type_combo.currentText()
        if output_path:
            output_path = str(Path(output_path).expanduser())
            self.acquisition_dock.output_path = output_path
            Path(output_path).mkdir(parents=True, exist_ok=True)
            # For simulation device, store as SPC output path in simulation parameters
            if device_type == "Simulation" and hasattr(self.device, "simulation_params"):
                self.device.simulation_params["spc_output_path"] = output_path
            elif device_type == "BrickMic" and hasattr(self.device, "device") and hasattr(self.device.device, "spc_output_path"):
                self.device.device.spc_output_path = output_path

        # For Simulation device, use chunk size (photons) as the per-file photon target
        if device_type == "Simulation" and hasattr(self.device, "simulation_params"):
            # Apply saved simulation parameters from the centralized settings panel
            saved_sim_params = acq_config.get("simulation_params")
            if saved_sim_params:
                import copy
                self.device.simulation_params.update(copy.deepcopy(saved_sim_params))
                logger.info("Applied saved simulation parameters from settings panel")
            
            target_photons = max(1, chunk_size_photons)
            self.device.simulation_params["N_ph_per_file"] = target_photons
            
            # Pass real_time_sim flag to simulation params
            self.device.simulation_params["real_time_sim"] = acq_config.get("real_time_sim", False)
                
        elif device_type == "BrickMic" and hasattr(self.device, "device") and hasattr(self.device.device, "N_ph_per_file"):
            target_photons = max(1, chunk_size_photons)
            self.device.device.N_ph_per_file = target_photons

        # --- Set up background data processing thread ---
        self._processing_thread = DataProcessingThread(self.main_window)
        self._processing_thread.configure(
            record_type=record_type_for_device(self.device),
            macrotime_clock=self.macrotime_clock,
            channel_mapping=[s.value() for s in self.acquisition_dock.channel_spinboxes],
            time_limit=self._time_limit,
            photon_limit=self._photon_limit,
            mcs_bin_width_ms=self.mcs_bin_width_ms,
            mcs_rollaround_ms=self.mcs_rollaround_time_ms,
        )
        # Discover enabled correlation pairs from the plot controller
        try:
            pairs = []
            if (hasattr(self.correlation_window, 'plot_controller')
                    and hasattr(self.correlation_window.plot_controller, 'correlation_widgets')):
                for i, (sa, sb, cb) in enumerate(self.correlation_window.plot_controller.correlation_widgets):
                    if cb.isChecked():
                        pairs.append((i, sa.value(), sb.value()))
            if not pairs:
                pairs = [(0, 0, 0)]
            self._processing_thread.set_correlation_pairs(pairs)
        except Exception:
            self._processing_thread.set_correlation_pairs([(0, 0, 0)])
        # The correlation update interval now throttles the *redraw*, not the
        # correlation: every photon reaches the correlator as it arrives, so
        # there is no longer an expensive recomputation to skip.
        self.correlation_redraw_interval = 1
        try:
            if (hasattr(self.correlation_window, 'plot_controller')
                    and hasattr(self.correlation_window.plot_controller, 'update_frequency_spinbox')):
                self.correlation_redraw_interval = max(
                    1, self.correlation_window.plot_controller.update_frequency_spinbox.value()
                )
        except Exception:
            self.correlation_redraw_interval = 1
        self._processing_thread.reset()
        self._processing_thread.results_ready.connect(self._apply_results)
        self._processing_thread.stop_requested.connect(self._on_processing_stop)
        self._processing_thread.start()

        self.acquisition_thread = AcquisitionThread(self.device, thread_duration, self.main_window, chunk_size_words)
        self.acquisition_thread.data_ready.connect(self._on_data_ready)
        self.acquisition_thread.acquisition_complete.connect(self.acquisition_completed)
        self.acquisition_thread.error.connect(self.acquisition_error)

        self._safe_set_button_enabled("start_button", False)
        self._safe_set_button_enabled("stop_button", True)
        self._safe_set_status_text("Status: Acquiring data")

        # Start progress timer
        self.start_time = time.monotonic()
        self.progress_timer = QTimer(self.main_window)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(100)  # Update every 100 ms

        # Start FIFO usage timer
        self.fifo_timer = QTimer(self.main_window)
        self.fifo_timer.timeout.connect(self.update_fifo_usage)
        self.fifo_timer.start(2000)  # Update every 2 seconds instead of 500ms

        self.acquisition_thread.start()

    def _on_data_ready(self, data):
        """Slot for incoming raw data – forward to the processing thread."""
        if hasattr(self, '_processing_thread') and self._processing_thread is not None:
            self._processing_thread.submit(data)

    def _apply_results(self):
        """Poll results from the processing thread and update plots."""
        proc = getattr(self, '_processing_thread', None)
        if proc is not None:
            results = proc.get_results()
        else:
            results = getattr(self, '_last_results', None)
        if results is None:
            return
        self._last_results = results

        try:
            self.decay_data = results['decay_data']
            self.total_photons = results['total_photons']

            # Correlation. The results are in *pair* order and each pair names
            # the curve it belongs to, which is not the same thing: correlating
            # only curve 2 gives one result, and reading it positionally draws
            # it as curve 0.
            corr_results = results.get('correlation_results', [])
            corr_pairs = results.get('correlation_pairs', [])
            for (curve_idx, _a, _b), c in zip(corr_pairs, corr_results):
                if c is not None and 0 <= curve_idx < len(self.correlation_times):
                    self.correlation_times[curve_idx] = c[0]
                    self.correlation_amplitudes[curve_idx] = c[1]

            # Count rates
            self.count_rate_times = results.get('count_rate_times', [])
            self.count_rate_data = results.get('count_rate_data', [[] for _ in range(5)])
            self.mean_countrate = results.get('mean_count_rate_khz', 0.0)

            # MCS
            self.mcs_trace = results.get('mcs_trace', None)

            # Macrotime
            self.macrotime_data = results.get('macrotime_data', [])
            self.macrotime_times = results.get('macrotime_times', [])

            # Update count rate LCD
            try:
                self.acquisition_dock.count_rate_lcd.display(f"{self.mean_countrate:.1f}")
            except Exception:
                pass

            # Live quality numbers, from the same photon pass as the decay.
            try:
                bursts = results.get('burst_count')
                phasor = results.get('phasor')
                text = "Bursts: —" if bursts is None else (
                    f"Bursts: {bursts:,} ({results.get('burst_rate_hz', 0.0):.1f}/s)"
                )
                if phasor is not None and phasor[2] > 0:
                    text += f" · Phasor: g={phasor[0]:.3f} s={phasor[1]:.3f}"
                else:
                    text += " · Phasor: —"
                self.decay_window.qc_label.setText(text)
            except (AttributeError, RuntimeError):
                pass

            # Update plots (lightweight chiplot set_data calls)
            self.update_decay_plot()
            self.update_correlation_plot()
            self.update_count_rate_plot()
            self.update_mcs_plot()
            self.update_macrotime_plot()

        except Exception as e:
            logger.error("Error applying results: %s", e, exc_info=True)

    def _on_processing_stop(self, reason):
        """Handle stop condition fired by the processing thread."""
        logger.info("Processing thread stop requested: %s", reason)
        self._safe_set_status_text(f"Status: {reason}")
        QTimer.singleShot(0, self.stop_acquisition)

    def process_data(self, data):
        """Legacy slot – now just forwards to the processing thread."""
        self._on_data_ready(data)

    def _safe_set_button_enabled(self, button_name, enabled):
        """Safely set button enabled state, handling widget deletion."""
        try:
            button = getattr(self.acquisition_dock, button_name)
            button.setEnabled(enabled)
        except (RuntimeError, AttributeError) as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning(f"{button_name} was deleted, skipping button state update")
            else:
                raise

    def _safe_set_status_text(self, text):
        """Safely set status text in progress bar, handling widget deletion."""
        try:
            # For progress bar format, we want to show the status text
            # The default format will show percentage, but we want custom status
            self.acquisition_dock.progress_bar.setFormat(text)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Progress bar was deleted, skipping status update")
            else:
                raise

    def stop_acquisition(self):
        """Stop data acquisition."""
        try:
            # Stop the background processing thread first (drains queue)
            proc = getattr(self, '_processing_thread', None)
            if proc is not None:
                # Cache last results for any pending _apply_results callbacks
                self._last_results = proc.get_results()
                proc.stop()
                proc.wait(3000)
                self._processing_thread = None

            if hasattr(self, 'acquisition_thread') and self.acquisition_thread is not None:
                logger.debug(f"Stopping acquisition thread (running: {self.acquisition_thread.isRunning()})")
                if self.acquisition_thread.isRunning():
                    self.acquisition_thread.stop()
                    # Give the thread a moment to stop
                    import time
                    timeout = 0
                    while self.acquisition_thread.isRunning() and timeout < 50:  # 5 second timeout
                        time.sleep(0.1)
                        timeout += 1

                    if self.acquisition_thread.isRunning():
                        logger.warning("Acquisition thread did not stop gracefully")
                    else:
                        logger.debug("Acquisition thread stopped successfully")
                else:
                    logger.debug("Acquisition thread was not running")

            # Update UI regardless of thread state
            self._safe_set_status_text("Status: Acquisition stopped")
            self._safe_set_button_enabled("start_button", True)
            self._safe_set_button_enabled("stop_button", False)

            # Clear acquisition flag
            self._acquisition_in_progress = False

        except Exception as e:
            # If something goes wrong, at least update the UI
            logger.error(f"Error stopping acquisition: {e}")
            try:
                self._safe_set_status_text("Status: Stopped (with errors)")
                self._safe_set_button_enabled("start_button", True)
                self._safe_set_button_enabled("stop_button", False)
                # Clear acquisition flag even on error
                self._acquisition_in_progress = False
            except:
                pass

        # Stop timers safely
        try:
            if hasattr(self, 'progress_timer') and self.progress_timer is not None:
                self.progress_timer.stop()
        except Exception as e:
            logger.error(f"Error stopping progress timer: {e}")

        try:
            if hasattr(self, 'fifo_timer') and self.fifo_timer is not None:
                self.fifo_timer.stop()
        except Exception as e:
            logger.error(f"Error stopping FIFO timer: {e}")

    # Add remaining methods here...

    def update_progress(self):
        """Update the progress bar."""
        if not self.acquisition_thread or not self.acquisition_thread.isRunning():
            return

        progress = 0
        have_progress = False

        # Time-based progress (if enabled)
        time_limit = getattr(self, "_time_limit", 0.0)
        if time_limit and time_limit > 0.0:
            elapsed = time.monotonic() - self.start_time
            if time_limit > 0.0:
                time_progress = int(min(100, elapsed / time_limit * 100))
                progress = max(progress, time_progress)
                have_progress = True

        # Photon-based progress (if enabled)
        photon_limit = getattr(self, "_photon_limit", 0)
        if photon_limit and photon_limit > 0 and hasattr(self, "total_photons"):
            ph_progress = int(min(100, self.total_photons / photon_limit * 100))
            progress = max(progress, ph_progress)
            have_progress = True

        if not have_progress:
            return

        # Safe progress bar update
        try:
            self.acquisition_dock.progress_bar.setValue(progress)
            # During progress updates, show percentage
            self.acquisition_dock.progress_bar.setFormat("%p%")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Progress bar was deleted, skipping progress update")
            else:
                raise

    def update_fifo_usage(self):
        """Log the FIFO usage."""
        # Only update FIFO usage if measurement is running
        if not hasattr(self, 'device') or not self.device.initialized:
            return

        # Check if measurement is running (for simulation and other devices)
        try:
            if hasattr(self.device, 'measurement_running'):
                if not self.device.measurement_running:
                    return
            elif hasattr(self.device, 'device') and hasattr(self.device.device, 'measurement_running'):
                # For factory devices
                if not self.device.device.measurement_running:
                    return
        except:
            pass

        usage_dict = self.device.get_fifo_usage()
        if not usage_dict:
            return

        try:
            device_type = self.acquisition_dock.device_type_combo.currentText()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Device type combo was deleted, skipping FIFO usage update")
                return
            else:
                raise

        # If there's only one active device, log its usage
        if len(usage_dict) == 1:
            device_index, usage = next(iter(usage_dict.items()))
            if usage >= 0:
                if device_type == "PicoQuant":
                    logger.debug(f"Buffer Usage (Device {device_index}): {usage:.1f}%")
                else:
                    logger.debug(f"FIFO Usage (Module {device_index}): {usage:.1f}%")
        # If there are multiple active devices, log the average usage
        else:
            valid_usages = [u for u in usage_dict.values() if u >= 0]
            if valid_usages:
                avg_usage = sum(valid_usages) / len(valid_usages)
                if device_type == "PicoQuant":
                    logger.debug(f"Avg Buffer Usage ({len(valid_usages)} devices): {avg_usage:.1f}%")
                else:
                    logger.debug(f"Avg FIFO Usage ({len(valid_usages)} cards): {avg_usage:.1f}%")

    def _safe_set_count_rate_text(self, count_rate_khz):
        """Safely set count rate in kHz on the LCD display, handling widget deletion."""
        try:
            # Format to one decimal place
            self.acquisition_dock.count_rate_lcd.display(f"{count_rate_khz:.1f}")
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Count rate LCD was deleted, skipping count rate update")
            else:
                raise

    def update_ram_usage(self):
        """Log the RAM usage.

        The readings come from the watermark helpers, which own the optional
        ``psutil`` import; this module never had one, so every call raised
        ``NameError`` before. Both return ``None`` when the reading is not
        available, and then there is nothing to log.
        """
        ram_usage = memory_usage_mb()
        total_ram = total_memory_mb()
        if ram_usage is None or not total_ram:
            return
        percent = ram_usage / total_ram * 100
        logger.debug(f"RAM usage: {ram_usage:.1f} MB ({percent:.1f}%)")

    def open_card_setup(self):
        """Open the card setup dialog."""
        if not self.device.initialized:
            dialogs.warning(self.main_window, "Warning", "Device not initialized")
            return

        # Create the card setup dialog
        device_type = self.acquisition_dock.device_type_combo.currentText()
        if device_type == "Simulation":
            try:
                logger.info("Attempting to import EnhancedSimulationSetupDialog")
                from ..tcspc_devices.simulation.setup_dialog import EnhancedSimulationSetupDialog
                logger.info("Successfully imported EnhancedSimulationSetupDialog")
                dialog = EnhancedSimulationSetupDialog(self.device, self.main_window)
                logger.info("Successfully created EnhancedSimulationSetupDialog instance")
            except Exception as e:
                logger.error(f"Failed to create enhanced setup dialog: {e}")
                dialogs.warning(self.main_window, "Setup Error", 
                                  f"Could not create simulation setup dialog: {e}")
                return
        elif device_type == "PicoQuant":
            from ..tcspc_devices import PicoQuantSetupDialog
            dialog = PicoQuantSetupDialog(self.device, self.main_window)
        else:
            dialog = BHSPCCardSetupDialog(self.device.device, self.main_window)
            # Set the current simulation mode in the dialog (only for BH cards)
            dialog.set_simulation_mode(self.simulation_mode)
        
        result = dialog.exec_()
        logger.info(f"Dialog exec_() returned: {result}")
        if hasattr(dialog, 'windowTitle'):
            logger.info(f"Dialog title: {dialog.windowTitle()}")
        else:
            logger.info("Dialog has no windowTitle method")

        # If the dialog was accepted, update the simulation mode and active cards
        if result == QDialog.Accepted:
            if hasattr(dialog, 'get_simulation_mode'):
                self.simulation_mode = dialog.get_simulation_mode()
            elif hasattr(dialog, 'get_parameters'):
                # Simulation or PicoQuant dialog returns parameters
                new_params = dialog.get_parameters()
                if hasattr(self.device, 'simulation_params'):
                    self.device.simulation_params.update(new_params)
                    logger.info("Updated simulation parameters")
                # For PicoQuant, we could store parameters if needed
                logger.info("Updated device parameters")
            active_cards = self.device.get_active_cards()
            logger.info(f"Active devices: {active_cards}")

    def _device_log_handler(self, message):
        """Handle device log messages and forward to chisurf logging."""
        logger.info(message)

    def toggle_decay_window(self, checked):
        """Toggle the fluorescence decays window visibility."""
        if checked:
            self.decay_window.show()
            self.decay_window.raise_()  # Bring to front
        else:
            self.decay_window.hide()

    def toggle_correlation_window(self, checked):
        """Toggle the correlation curve window visibility."""
        if checked:
            self.correlation_window.show()
            self.correlation_window.raise_()  # Bring to front
        else:
            self.correlation_window.hide()

    def toggle_count_rate_window(self, checked):
        """Toggle the count rate window visibility."""
        if checked:
            self.count_rate_window.show()
            self.count_rate_window.raise_()  # Bring to front
        else:
            self.count_rate_window.hide()

    def toggle_macrotime_window(self, checked):
        """Toggle the macrotime window visibility."""
        if checked:
            self.macrotime_window.show()
            self.macrotime_window.raise_()  # Bring to front
        else:
            self.macrotime_window.hide()

    def toggle_mcs_window(self, checked):
        """Toggle the MCS window visibility."""
        if checked:
            self.mcs_window.show()
            self.mcs_window.raise_()  # Bring to front
        else:
            self.mcs_window.hide()

    def show_help(self):
        """Show the help documentation window."""
        try:
            if not hasattr(self, 'help_window') or self.help_window is None:
                self.help_window = HelpViewerWindow(self.main_window)
                if self.chisurf_available:
                    self.main_window.mdiarea.addSubWindow(self.help_window)
                else:
                    # In standalone mode, just show the window
                    pass

            self.help_window.show()
            self.help_window.raise_()  # Bring to front
            self.help_window.activateWindow()
        except Exception as e:
            logger.error(f"Error opening help window: {e}")
            dialogs.warning(self.main_window, "Help Error", f"Could not open help documentation:\n{e}")

    def close_acquisition_mode(self):
        """Close the acquisition mode and clean up all components."""

        # Ask for confirmation
        reply = dialogs.question(
            self.main_window,
            "Close Acquisition Mode",
            "Are you sure you want to close the acquisition mode?\n\nThis will stop any ongoing acquisition and close all acquisition windows.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Stop any ongoing acquisition
        if hasattr(self, 'acquisition_thread') and self.acquisition_thread and self.acquisition_thread.isRunning():
            self.acquisition_thread.stop()

        # Close device
        if self.device.initialized:
            self.device.close()

        # Stop timers
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        if hasattr(self, 'fifo_timer'):
            self.fifo_timer.stop()

        # Remove plot controllers from chisurf's plot options layout
        if hasattr(self.main_window, 'plotOptionsLayout'):
            # Remove decay plot controller
            if hasattr(self.decay_window, 'plot_controller') and self.decay_window.plot_controller is not None:
                try:
                    self.main_window.plotOptionsLayout.removeWidget(self.decay_window.plot_controller)
                    self.decay_window.plot_controller.hide()
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Decay plot controller was already removed from layout")
                    else:
                        raise

            # Remove correlation plot controller
            if hasattr(self.correlation_window, 'plot_controller') and self.correlation_window.plot_controller is not None:
                try:
                    self.main_window.plotOptionsLayout.removeWidget(self.correlation_window.plot_controller)
                    self.correlation_window.plot_controller.hide()
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Correlation plot controller was already removed from layout")
                    else:
                        raise

            # Remove count rate plot controller
            if hasattr(self.count_rate_window, 'plot_controller') and self.count_rate_window.plot_controller is not None:
                try:
                    self.main_window.plotOptionsLayout.removeWidget(self.count_rate_window.plot_controller)
                    self.count_rate_window.plot_controller.hide()
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Count rate plot controller was already removed from layout")
                    else:
                        raise

        # Remove windows from MDI area
        self.main_window.mdiarea.removeSubWindow(self.decay_window)
        self.main_window.mdiarea.removeSubWindow(self.correlation_window)
        self.main_window.mdiarea.removeSubWindow(self.count_rate_window)
        self.main_window.mdiarea.removeSubWindow(self.macrotime_window)
        self.main_window.mdiarea.removeSubWindow(self.mcs_window)

        # Close and remove dock widgets
        self.main_window.removeDockWidget(self.acquisition_dock)

        # Close windows
        self.decay_window.close()
        self.correlation_window.close()
        self.count_rate_window.close()
        self.macrotime_window.close()
        self.mcs_window.close()
        self.acquisition_dock.close()

        # Clear plot controllers to default state (after windows are closed)
        self._clear_plot_controllers()

        # Clean up widget references
        try:
            if hasattr(self, 'acquisition_dock'):
                self.acquisition_dock = None
            if hasattr(self, 'decay_window'):
                self.decay_window = None
            if hasattr(self, 'correlation_window'):
                self.correlation_window = None
            if hasattr(self, 'count_rate_window'):
                self.count_rate_window = None
            if hasattr(self, 'macrotime_window'):
                self.macrotime_window = None
            if hasattr(self, 'mcs_window'):
                self.mcs_window = None
        except Exception as e:
            logger.error(f"Error cleaning up widget references: {e}")

        # Remove reference from main window
        if hasattr(self.main_window, '_acquisition_manager'):
            delattr(self.main_window, '_acquisition_manager')

        # Log the closure
        logger.info("Single-Molecule Acquisition mode closed.")

    def _decay_window_of_channel(self, channel):
        """Return the decay window holding a device routing channel, or ``None``.

        The dock's four channel spinboxes *are* the mapping — window *i* shows
        routing channel ``channel_spinboxes[i].value()`` — and the pipeline
        histograms in exactly that order.
        """
        try:
            mapping = [s.value() for s in self.acquisition_dock.channel_spinboxes]
        except (AttributeError, RuntimeError):
            return channel if 0 <= channel < len(self.decay_data) else None
        return mapping.index(channel) if channel in mapping else None

    def _microtime_axis_ns(self, n_bins):
        """Micro-time axis in nanoseconds for ``n_bins`` TAC channels.

        The axis used to be ``np.linspace(0, 100, n)`` with the comment
        "Assuming 100 ns time range" — a number no instrument here produces, so
        every live decay was drawn on a made-up abscissa. The resolution comes
        from the device when it knows it (the simulator carries ``tac_dt``);
        otherwise the axis stays in TAC channels, which is at least true.
        """
        resolution = getattr(self, "microtime_resolution_ns", None)
        if resolution:
            return np.arange(n_bins) * float(resolution)
        return np.arange(n_bins, dtype=float)

    def update_decay_plot(self):
        """Update the decay plot based on current plot controller settings."""
        logger.debug("update_decay_plot called")
        if len(self.decay_data) == 0:
            logger.debug("No decay data, returning")
            return

        # Early return if window or plot controller is not available (e.g., during cleanup)
        if not hasattr(self, 'decay_window') or self.decay_window is None:
            return
        if not hasattr(self.decay_window, 'plot_controller') or self.decay_window.plot_controller is None:
            return

        # Check update frequency
        if hasattr(self.decay_window, 'plot_controller') and hasattr(self.decay_window.plot_controller, 'update_frequency_spinbox'):
            try:
                update_frequency = self.decay_window.plot_controller.update_frequency_spinbox.value()
                self.decay_update_counter += 1
                if self.decay_update_counter < update_frequency:
                    return  # Skip update this time
                self.decay_update_counter = 0  # Reset counter
            except RuntimeError as e:
                if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                    logger.warning("Decay plot controller update_frequency_spinbox was deleted, skipping frequency check")
                else:
                    raise

        # Get log Y setting from controller
        use_log_y = False  # Default to linear scale for decays to show zeros
        try:
            if hasattr(self.decay_window, 'plot_controller') and hasattr(self.decay_window.plot_controller, 'log_y_checkbox'):
                use_log_y = self.decay_window.plot_controller.log_y_checkbox.isChecked()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Decay plot controller log_y_checkbox was deleted, using default log_y=False")
                use_log_y = False
            else:
                raise

        # Set log mode for Y axis
        try:
            self.decay_window.decay_plot_widget.set_log(y=use_log_y)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Decay plot widget was deleted, skipping log mode update")
                return
            else:
                raise

        # Get visible channels from plot controller
        visible_channels = []
        try:
            if hasattr(self.decay_window, 'plot_controller'):
                if hasattr(self.decay_window.plot_controller, 'channel_widgets'):
                    for i, (spinbox, checkbox) in enumerate(self.decay_window.plot_controller.channel_widgets):
                        try:
                            if checkbox.isChecked():
                                channel = spinbox.value()
                                if channel == -1:
                                    # Sum of every acquired window
                                    combined = np.sum(self.decay_data, axis=0)
                                    visible_channels.append((i, -1))
                                else:
                                    # A routing channel is a *device* number; which
                                    # decay window holds it is whatever the dock's
                                    # channel spinboxes say. This used to be the
                                    # hard-coded table {8: 0, 9: 1, 10: 2}, so any
                                    # other detector numbering drew the wrong
                                    # channel's decay under the right label.
                                    data_idx = self._decay_window_of_channel(channel)
                                    if data_idx is not None:
                                        visible_channels.append((i, data_idx))
                        except RuntimeError as e:
                            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                                logger.warning(f"Decay curve {i} widget was deleted, skipping")
                                continue
                            else:
                                raise
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Decay plot controller was deleted, using defaults")
                visible_channels = [(0, 0), (1, 1), (2, 2)]  # Show routing 8,9,10 on curves 0,1,2
            else:
                raise

        # Update each channel curve in the single plot
        try:
            for curve_idx, data_idx in visible_channels:
                if data_idx == -1:
                    # Combined data
                    x = self._microtime_axis_ns(len(combined))
                    self.decay_window.decay_curves[curve_idx].set_data(x, combined)
                    self.decay_window.decay_curves[curve_idx].show()
                elif data_idx < len(self.decay_data) and len(self.decay_data[data_idx]) > 0:
                    logger.debug(f"Setting decay data for curve {curve_idx} (channel data {data_idx}), length {len(self.decay_data[data_idx])}, total counts {np.sum(self.decay_data[data_idx])}")
                    x = self._microtime_axis_ns(len(self.decay_data[data_idx]))
                    self.decay_window.decay_curves[curve_idx].set_data(x, self.decay_data[data_idx])
                    self.decay_window.decay_curves[curve_idx].show()
                else:
                    logger.debug(f"Hiding decay curve {curve_idx}, no data for channel data {data_idx}")
                    self.decay_window.decay_curves[curve_idx].hide()
            # Hide unused curves
            for i in range(4):
                if i not in [c for c, d in visible_channels]:
                    self.decay_window.decay_curves[i].hide()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Decay plot curves were deleted, skipping plot update")
            else:
                raise

    def _clear_plot_controllers(self):
        """Reset plot controllers to their default states."""
        try:
            # Clear decay plot controller
            if hasattr(self, 'decay_window') and self.decay_window is not None and hasattr(self.decay_window, 'plot_controller'):
                try:
                    # Reset channel spinboxes and checkboxes
                    for i, (spinbox, checkbox) in enumerate(self.decay_window.plot_controller.channel_widgets):
                        spinbox.setValue([8, 9, 10, -1][i])
                        checkbox.setChecked(i < 3)
                    # Reset log Y checkbox to unchecked (linear scale for decays)
                    if hasattr(self.decay_window.plot_controller, 'log_y_checkbox'):
                        self.decay_window.plot_controller.log_y_checkbox.setChecked(False)
                    # Reset update frequency to default
                    self.decay_window.plot_controller.update_frequency_spinbox.setValue(1)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Decay plot controller widgets were deleted during cleanup")
                    else:
                        raise

            # Clear correlation plot controller
            if hasattr(self, 'correlation_window') and self.correlation_window is not None and hasattr(self.correlation_window, 'plot_controller'):
                try:
                    # Reset correlation spinboxes and checkboxes
                    for i, (spinbox_a, spinbox_b, checkbox) in enumerate(self.correlation_window.plot_controller.correlation_widgets):
                        spinbox_a.setValue(-1)
                        spinbox_b.setValue(-1)
                        checkbox.setChecked(i == 0)  # Enable first by default
                    # Reset update frequency to default
                    self.correlation_window.plot_controller.update_frequency_spinbox.setValue(5)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Correlation plot controller widgets were deleted during cleanup")
                    else:
                        raise

            # Clear count rate plot controller
            if hasattr(self.count_rate_window, 'plot_controller') and self.count_rate_window.plot_controller is not None:
                try:
                    # Reset channel spinboxes, checkboxes and "All"
                    for i, widget in enumerate(self.count_rate_window.plot_controller.channel_widgets):
                        if i < 4:
                            spinbox, checkbox, _ = widget
                            # Default: first curve plots sum (-1), others keep routing defaults and are disabled
                            default_channels = [-1, 9, 10, 8]
                            spinbox.setValue(default_channels[i])
                            checkbox.setChecked(i == 0)
                        # "All" curve is always shown, no checkbox to set
                    # Reset log Y checkbox to unchecked (linear scale)
                    if hasattr(self.count_rate_window.plot_controller, 'log_y_checkbox'):
                        self.count_rate_window.plot_controller.log_y_checkbox.setChecked(False)
                    # Reset rolling window settings
                    if hasattr(self.count_rate_window.plot_controller, 'rolling_window_checkbox'):
                        self.count_rate_window.plot_controller.rolling_window_checkbox.setChecked(True)  # Default enabled
                    if hasattr(self.count_rate_window.plot_controller, 'window_size_spinbox'):
                        self.count_rate_window.plot_controller.window_size_spinbox.setValue(500)
                    if hasattr(self.count_rate_window.plot_controller, 'binning_spinbox'):
                        self.count_rate_window.plot_controller.binning_spinbox.setValue(1)
                    # Reset update frequency to default (every chunk)
                    self.count_rate_window.plot_controller.update_frequency_spinbox.setValue(1)

                    # Clear any mean lines
                    for line in self.count_rate_window.mean_lines:
                        line.remove()
                    self.count_rate_window.mean_lines.clear()
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Count rate plot controller widgets were deleted during cleanup")
                    else:
                        raise

            # Clear macrotime plot controller
            if hasattr(self, 'macrotime_window') and self.macrotime_window is not None and hasattr(self.macrotime_window, 'plot_controller'):
                try:
                    # Reset checkbox to checked
                    if hasattr(self.macrotime_window.plot_controller, 'show_macrotimes_checkbox'):
                        self.macrotime_window.plot_controller.show_macrotimes_checkbox.setChecked(True)
                    # Reset update frequency to default
                    self.macrotime_window.plot_controller.update_frequency_spinbox.setValue(1)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("Macrotime plot controller widgets were deleted during cleanup")
                    else:
                        raise

            # Clear MCS plot controller
            if hasattr(self, 'mcs_window') and self.mcs_window is not None and hasattr(self.mcs_window, 'plot_controller'):
                try:
                    # Reset MCS controls to defaults
                    if hasattr(self.mcs_window.plot_controller, 'bin_width_spinbox'):
                        self.mcs_window.plot_controller.bin_width_spinbox.setValue(1.0)
                    if hasattr(self.mcs_window.plot_controller, 'rollaround_spinbox'):
                        self.mcs_window.plot_controller.rollaround_spinbox.setValue(1.0)
                    if hasattr(self.mcs_window.plot_controller, 'manual_y_range_checkbox'):
                        self.mcs_window.plot_controller.manual_y_range_checkbox.setChecked(False)
                    if hasattr(self.mcs_window.plot_controller, 'y_min_spinbox'):
                        self.mcs_window.plot_controller.y_min_spinbox.setValue(0.0)
                    if hasattr(self.mcs_window.plot_controller, 'y_max_spinbox'):
                        self.mcs_window.plot_controller.y_max_spinbox.setValue(1000.0)
                    # Reset update frequency to default
                    self.mcs_window.plot_controller.update_frequency_spinbox.setValue(5)
                except RuntimeError as e:
                    if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                        logger.debug("MCS plot controller widgets were deleted during cleanup")
                    else:
                        raise

            logger.debug("Plot controllers cleared to default state")

        except Exception as e:
            logger.warning(f"Error clearing plot controllers: {e}")

    def save_settings_json(self):
        """Save current acquisition settings to JSON file."""
        filename, _ = QFileDialog.getSaveFileName(
            self.main_window, "Save Acquisition Settings", "", "JSON files (*.json);;All files (*)"
        )
        if filename:
            try:
                settings = self._get_current_settings()
                json_str = json.dumps(settings, indent=2)
                with open(filename, 'w') as f:
                    f.write(json_str)
                dialogs.information(self.main_window, "Save Successful", "Settings saved to JSON file.")
            except Exception as e:
                dialogs.warning(self.main_window, "Save Error", f"Failed to save JSON file: {e}")

    def load_settings_json(self):
        """Load acquisition settings from JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self.main_window, "Load Acquisition Settings", "", "JSON files (*.json);;All files (*)"
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    settings = json.load(f)
                self._apply_settings(settings)
                dialogs.information(self.main_window, "Load Successful", "Settings loaded from JSON file.")
            except Exception as e:
                dialogs.warning(self.main_window, "Load Error", f"Failed to load JSON file: {e}")

    def _get_current_settings(self):
        """Get current acquisition settings as dictionary."""
        settings = {
            'device_type': self.acquisition_dock.device_type_combo.currentText(),
            'simulation_mode': getattr(self, 'simulation_mode', True),
            'duration': self.acquisition_dock.duration,
            'photon_limit': self.acquisition_dock.photon_limit,
            'chunk_size': self.acquisition_dock.chunk_size,
            'output_path': self.acquisition_dock.output_path,
            'channel_spinboxes': [spin.value() for spin in self.acquisition_dock.channel_spinboxes],
            'show_windows': {
                'decay': self.acquisition_dock.show_decay,
                'correlation': self.acquisition_dock.show_correlation,
                'count_rate': self.acquisition_dock.show_count_rate,
                'macrotime': self.acquisition_dock.show_macrotime,
                'mcs': self.acquisition_dock.show_mcs,
            }
        }

        # Add device-specific settings
        try:
            if hasattr(self.device, 'simulation_params') and self.device.simulation_params:
                settings['simulation_params'] = copy.deepcopy(self.device.simulation_params)
        except AttributeError:
            pass

        # Add plot controller settings
        plot_controllers = {}
        if hasattr(self, 'decay_window') and self.decay_window and hasattr(self.decay_window, 'plot_controller'):
            plot_controllers['decay'] = {
                'channels': [w[0].value() for w in self.decay_window.plot_controller.channel_widgets],
                'enabled': [w[1].isChecked() for w in self.decay_window.plot_controller.channel_widgets],
                'log_y': self.decay_window.plot_controller.log_y_checkbox.isChecked(),
                'update_frequency': self.decay_window.plot_controller.update_frequency_spinbox.value(),
            }
        if hasattr(self, 'count_rate_window') and self.count_rate_window and hasattr(self.count_rate_window, 'plot_controller'):
            plot_controllers['count_rate'] = {
                'channels': [w[0].value() if w[0] else None for w in self.count_rate_window.plot_controller.channel_widgets[:4]],
                'enabled': [w[1].isChecked() if w[1] else None for w in self.count_rate_window.plot_controller.channel_widgets[:4]],
                'log_y': self.count_rate_window.plot_controller.log_y_checkbox.isChecked(),
                'rolling_window': self.count_rate_window.plot_controller.rolling_window_checkbox.isChecked(),
                'window_size': self.count_rate_window.plot_controller.window_size_spinbox.value(),
                'binning': self.count_rate_window.plot_controller.binning_spinbox.value(),
                'update_frequency': self.count_rate_window.plot_controller.update_frequency_spinbox.value(),
            }
        if hasattr(self, 'correlation_window') and self.correlation_window and hasattr(self.correlation_window, 'plot_controller'):
            plot_controllers['correlation'] = {
                'curves': [{'ch_a': w[0].value(), 'ch_b': w[1].value(), 'enabled': w[2].isChecked()} for w in self.correlation_window.plot_controller.correlation_widgets],
                'update_frequency': self.correlation_window.plot_controller.update_frequency_spinbox.value(),
            }
        if hasattr(self, 'mcs_window') and self.mcs_window and hasattr(self.mcs_window, 'plot_controller'):
            plot_controllers['mcs'] = {
                'bin_width': self.mcs_window.plot_controller.bin_width_spinbox.value(),
                'rollaround': self.mcs_window.plot_controller.rollaround_spinbox.value(),
                'manual_y_range': self.mcs_window.plot_controller.manual_y_range_checkbox.isChecked(),
                'y_min': self.mcs_window.plot_controller.y_min_spinbox.value(),
                'y_max': self.mcs_window.plot_controller.y_max_spinbox.value(),
                'update_frequency': self.mcs_window.plot_controller.update_frequency_spinbox.value(),
            }
        if hasattr(self, 'macrotime_window') and self.macrotime_window and hasattr(self.macrotime_window, 'plot_controller'):
            plot_controllers['macrotime'] = {
                'show_macrotimes': self.macrotime_window.plot_controller.show_macrotimes_checkbox.isChecked(),
                'plot_type': self.macrotime_window.plot_controller.plot_type_combo.currentText(),
                'update_frequency': self.macrotime_window.plot_controller.update_frequency_spinbox.value(),
            }
        settings['plot_controllers'] = plot_controllers

        return settings

    def _apply_settings(self, settings):
        """Apply loaded settings to the UI and device."""
        # Update device type
        device_type = settings.get('device_type', 'Simulation')
        device_index = self.acquisition_dock.device_type_combo.findText(device_type)
        if device_index >= 0:
            self.acquisition_dock.device_type_combo.setCurrentIndex(device_index)
            self.on_device_type_changed(device_type)

        # Update simulation mode
        if 'simulation_mode' in settings:
            self.simulation_mode = settings['simulation_mode']

        # Update acquisition parameters
        if 'duration' in settings:
            self.acquisition_dock.duration = settings['duration']
        if 'photon_limit' in settings:
            self.acquisition_dock.photon_limit = settings['photon_limit']
        if 'chunk_size' in settings:
            self.acquisition_dock.chunk_size = settings['chunk_size']
        if 'output_path' in settings:
            self.acquisition_dock.output_path = settings['output_path']

        # Update channel spinboxes
        if 'channel_spinboxes' in settings:
            for i, value in enumerate(settings['channel_spinboxes']):
                if i < len(self.acquisition_dock.channel_spinboxes):
                    self.acquisition_dock.channel_spinboxes[i].setValue(value)

        # Update window visibility checkboxes
        if 'show_windows' in settings:
            show_windows = settings['show_windows']
            self.acquisition_dock.show_decay = show_windows.get('decay', True)
            self.acquisition_dock.show_correlation = show_windows.get('correlation', True)
            self.acquisition_dock.show_count_rate = show_windows.get('count_rate', True)
            self.acquisition_dock.show_macrotime = show_windows.get('macrotime', False)
            self.acquisition_dock.show_mcs = show_windows.get('mcs', False)

        # Apply simulation parameters
        if 'simulation_params' in settings:
            try:
                if hasattr(self.device, 'simulation_params'):
                    self.device.simulation_params = copy.deepcopy(settings['simulation_params'])
            except AttributeError:
                pass

        # Apply plot controller settings
        if 'plot_controllers' in settings:
            pc = settings['plot_controllers']
            if 'decay' in pc and hasattr(self, 'decay_window') and self.decay_window and hasattr(self.decay_window, 'plot_controller'):
                d = pc['decay']
                for i, w in enumerate(self.decay_window.plot_controller.channel_widgets):
                    if i < len(d['channels']):
                        w[0].setValue(d['channels'][i])
                    if i < len(d['enabled']):
                        w[1].setChecked(d['enabled'][i])
                self.decay_window.plot_controller.log_y_checkbox.setChecked(d.get('log_y', False))
                self.decay_window.plot_controller.update_frequency_spinbox.setValue(d.get('update_frequency', 1))
            if 'count_rate' in pc and hasattr(self, 'count_rate_window') and self.count_rate_window and hasattr(self.count_rate_window, 'plot_controller'):
                cr = pc['count_rate']
                for i, w in enumerate(self.count_rate_window.plot_controller.channel_widgets[:4]):
                    if w[0] and i < len(cr['channels']) and cr['channels'][i] is not None:
                        w[0].setValue(cr['channels'][i])
                    if w[1] and i < len(cr['enabled']) and cr['enabled'][i] is not None:
                        w[1].setChecked(cr['enabled'][i])
                self.count_rate_window.plot_controller.log_y_checkbox.setChecked(cr.get('log_y', False))
                self.count_rate_window.plot_controller.rolling_window_checkbox.setChecked(cr.get('rolling_window', True))
                self.count_rate_window.plot_controller.window_size_spinbox.setValue(cr.get('window_size', 500))
                self.count_rate_window.plot_controller.binning_spinbox.setValue(cr.get('binning', 1))
                self.count_rate_window.plot_controller.update_frequency_spinbox.setValue(cr.get('update_frequency', 1))
            if 'correlation' in pc and hasattr(self, 'correlation_window') and self.correlation_window and hasattr(self.correlation_window, 'plot_controller'):
                corr = pc['correlation']
                for i, w in enumerate(self.correlation_window.plot_controller.correlation_widgets):
                    if i < len(corr['curves']):
                        w[0].setValue(corr['curves'][i]['ch_a'])
                        w[1].setValue(corr['curves'][i]['ch_b'])
                        w[2].setChecked(corr['curves'][i]['enabled'])
                self.correlation_window.plot_controller.update_frequency_spinbox.setValue(corr.get('update_frequency', 5))
            if 'mcs' in pc and hasattr(self, 'mcs_window') and self.mcs_window and hasattr(self.mcs_window, 'plot_controller'):
                mcs = pc['mcs']
                self.mcs_window.plot_controller.bin_width_spinbox.setValue(mcs.get('bin_width', 1.0))
                self.mcs_window.plot_controller.rollaround_spinbox.setValue(mcs.get('rollaround', 1.0))
                self.mcs_window.plot_controller.manual_y_range_checkbox.setChecked(mcs.get('manual_y_range', False))
                self.mcs_window.plot_controller.y_min_spinbox.setValue(mcs.get('y_min', 0.0))
                self.mcs_window.plot_controller.y_max_spinbox.setValue(mcs.get('y_max', 1000.0))
                self.mcs_window.plot_controller.update_frequency_spinbox.setValue(mcs.get('update_frequency', 5))
            if 'macrotime' in pc and hasattr(self, 'macrotime_window') and self.macrotime_window and hasattr(self.macrotime_window, 'plot_controller'):
                mt = pc['macrotime']
                self.macrotime_window.plot_controller.show_macrotimes_checkbox.setChecked(mt.get('show_macrotimes', True))
                self.macrotime_window.plot_controller.plot_type_combo.setCurrentText(mt.get('plot_type', 'Time Differences (dt)'))
                self.macrotime_window.plot_controller.update_frequency_spinbox.setValue(mt.get('update_frequency', 1))

        # Update UI for device type
        self.update_ui_for_device_type()

    def update_correlation_plot(self):
        """Update the correlation plot based on current plot controller settings."""
        # Early return if window or plot controller is not available (e.g., during cleanup)
        if not hasattr(self, 'correlation_window') or self.correlation_window is None:
            return
        if not hasattr(self.correlation_window, 'plot_controller') or self.correlation_window.plot_controller is None:
            return

        # The correlation is computed per chunk; this only redraws it, so the
        # update-frequency setting throttles the redraw.
        interval = getattr(self, "correlation_redraw_interval", 1)
        if interval > 1:
            self.correlation_update_counter += 1
            if self.correlation_update_counter < interval:
                return
            self.correlation_update_counter = 0

        try:
            for i in range(4):
                if self.correlation_times[i] is not None and self.correlation_amplitudes[i] is not None:
                    self.correlation_window.correlation_curves[i].set_data(self.correlation_times[i], self.correlation_amplitudes[i])
                    self.correlation_window.correlation_curves[i].show()
                else:
                    self.correlation_window.correlation_curves[i].hide()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Correlation plot curves were deleted, skipping plot update")
            else:
                raise

    def update_count_rate_plot(self):
        """Update the count rate plot based on current plot controller settings."""
        if len(self.count_rate_times) == 0:
            return

        # Early return if window or plot controller is not available (e.g., during cleanup)
        if not hasattr(self, 'count_rate_window') or self.count_rate_window is None:
            return
        if not hasattr(self.count_rate_window, 'plot_controller') or self.count_rate_window.plot_controller is None:
            return

        # Get visible channels from plot controller
        visible_channels = []
        show_all = False
        try:
            if hasattr(self.count_rate_window, 'plot_controller'):
                for i, widget in enumerate(self.count_rate_window.plot_controller.channel_widgets):
                    try:
                        if i < 4:
                            spinbox, checkbox, _ = widget
                            if checkbox.isChecked():
                                channel = spinbox.value()
                                if channel == -1:
                                    data_idx = 4  # All channels
                                elif 0 <= channel <= 2:
                                    data_idx = channel
                                elif channel in {8, 9, 10}:
                                    data_idx = {8: 0, 9: 1, 10: 2}[channel]
                                else:
                                    data_idx = None
                                if data_idx is not None:
                                    visible_channels.append((i, data_idx))
                        elif i == 4:
                            # "All" curve is not always shown - shown when a spinbox is set to -1
                            pass
                    except RuntimeError as e:
                        if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                            logger.warning(f"Count rate curve {i} widget was deleted, skipping")
                            continue
                        else:
                            raise
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Count rate plot controller was deleted, using defaults")
                visible_channels = [(0, 0), (1, 1), (2, 2)]
            else:
                raise

        # Get log Y setting from controller
        use_log_y = False  # Default to linear scale
        try:
            if hasattr(self.count_rate_window, 'plot_controller') and hasattr(self.count_rate_window.plot_controller, 'log_y_checkbox'):
                use_log_y = self.count_rate_window.plot_controller.log_y_checkbox.isChecked()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Count rate plot controller log_y_checkbox was deleted, using default log_y=False")
                use_log_y = False
            else:
                raise

        # Set log mode for Y axis
        try:
            self.count_rate_window.count_rate_plot_widget.set_log(y=use_log_y)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Count rate plot widget was deleted, skipping log mode update")
                return
            else:
                raise

        # Update each visible curve
        try:
            for curve_idx, data_idx in visible_channels:
                if data_idx < len(self.count_rate_data) and len(self.count_rate_data[data_idx]) > 0:
                    # Pad time array to match data length
                    time_array = np.array(self.count_rate_times[:len(self.count_rate_data[data_idx])])
                    data_array = np.array(self.count_rate_data[data_idx])
                    self.count_rate_window.count_rate_curves[curve_idx].set_data(time_array, data_array)
                    self.count_rate_window.count_rate_curves[curve_idx].show()
                else:
                    self.count_rate_window.count_rate_curves[curve_idx].hide()

            # Hide curves that are not visible
            for i in range(5):
                if i not in [c for c, d in visible_channels]:
                    self.count_rate_window.count_rate_curves[i].hide()
            
            # Force plot refresh and auto-range
            try:
                self.count_rate_window.count_rate_plot_widget.autoscale()
                self.count_rate_window.count_rate_plot_widget.update()
            except Exception:
                # Swallow plot refresh errors to avoid spurious console output
                pass
                
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Count rate plot curves were deleted, skipping plot update")
            else:
                raise

    def acquisition_completed(self):
        """Handle acquisition completion."""
        logger.info("Acquisition completed")
        self._safe_set_status_text("Status: Acquisition completed")
        self._safe_set_button_enabled("start_button", True)
        self._safe_set_button_enabled("stop_button", False)

        # Clear acquisition flag
        self._acquisition_in_progress = False

        # Save data if enabled
        self._save_data()

    def acquisition_error(self, error_msg):
        """Handle acquisition error."""
        logger.error(f"Acquisition error: {error_msg}")
        self._safe_set_status_text(f"Status: Error - {error_msg}")
        self._safe_set_button_enabled("start_button", True)
        self._safe_set_button_enabled("stop_button", False)

        # Clear acquisition flag
        self._acquisition_in_progress = False

    def _save_data(self):
        """Report what the finished run left on disk — and what it did not.

        This used to be ``pass`` under a module docstring promising that data
        is "saved at the end of data acquisition". Nothing was: unless the
        device was dripping raw vendor words to a folder, the photons went to
        the display and nowhere else, and a crash or a forgotten checkbox lost
        the run with no message anywhere.

        The real fix is a photon sink written *during* the measurement — see
        :class:`~chisurf.plugins.core.acq.pipeline.PhotonSink`; it is blocked on
        the photon library's native container sink. Until then the honest thing
        is to say which of the two applied, rather than to look like saving.
        """
        output_path = (self.acquisition_dock.output_path or "").strip()
        photons = getattr(self, "total_photons", 0)
        if output_path:
            logger.info(
                "Acquisition finished: %s photons; raw device words were written "
                "to %s if the device supports the raw drip.", f"{photons:,}", output_path
            )
            self._safe_set_status_text(
                f"Status: Finished — {photons:,} photons (raw words in {output_path})"
            )
        else:
            logger.warning(
                "Acquisition finished: %s photons were NOT saved — no output "
                "folder was set and there is no photon sink yet.", f"{photons:,}"
            )
            self._safe_set_status_text(
                f"Status: Finished — {photons:,} photons, NOT saved (no output folder)"
            )

    def update_macrotime_plot(self):
        """Update the macrotime plot."""
        if not hasattr(self, 'macrotime_window') or self.macrotime_window is None:
            return

        # Check update frequency
        if hasattr(self.macrotime_window, 'plot_controller') and hasattr(self.macrotime_window.plot_controller, 'update_frequency_spinbox'):
            try:
                update_frequency = self.macrotime_window.plot_controller.update_frequency_spinbox.value()
                self.macrotime_update_counter += 1
                if self.macrotime_update_counter < update_frequency:
                    return
                self.macrotime_update_counter = 0
            except RuntimeError:
                pass

        # The MCS trace arrives with the rest of the display state — it is a
        # rolling window kept by the pipeline, not something recomputed here
        # from every photon of the run.
        self.update_mcs_plot()

        # Check if macrotime plot should be shown
        show_macrotimes = True
        try:
            if hasattr(self.macrotime_window, 'plot_controller') and hasattr(self.macrotime_window.plot_controller, 'show_macrotimes_checkbox'):
                show_macrotimes = self.macrotime_window.plot_controller.show_macrotimes_checkbox.isChecked()
        except RuntimeError:
            pass

        try:
            if show_macrotimes and len(self.macrotime_data) > 0:
                # Plot macrotime differences vs time (dt already in seconds)
                times = np.array(self.macrotime_times[-len(self.macrotime_data):])
                dts = np.array(self.macrotime_data)
                self.macrotime_window.macrotime_curve.set_data(times, dts)
                self.macrotime_window.macrotime_plot_widget.set_labels(
                    left='Macrotime Difference (s)', bottom='Time (s)')

            self.macrotime_window.macrotime_curve.show()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("Macrotime plot curve was deleted, skipping plot update")
            else:
                raise

    def update_mcs_plot(self):
        """Update the MCS trace plot."""
        if self.mcs_trace is None:
            return

        # Early return if window is not available (e.g., during cleanup)
        if not hasattr(self, 'mcs_window') or self.mcs_window is None:
            return

        # Update MCS trace display if available
        try:
            if self.mcs_trace is not None:
                bin_centers, hist_counts = self.mcs_trace
                self.mcs_window.mcs_curve.set_data(bin_centers, hist_counts)
                self.mcs_window.mcs_curve.show()

                # Apply Y range if manual range is enabled
                if hasattr(self.mcs_window, 'plot_controller') and hasattr(self.mcs_window.plot_controller, 'manual_y_range_checkbox'):
                    if self.mcs_window.plot_controller.manual_y_range_checkbox.isChecked():
                        y_min = self.mcs_window.plot_controller.y_min_spinbox.value()
                        y_max = self.mcs_window.plot_controller.y_max_spinbox.value()
                        self.mcs_window.mcs_plot_widget.set_ylim(y_min, y_max)
                    else:
                        self.mcs_window.mcs_plot_widget.autoscale(x=False, y=True)
            else:
                self.mcs_window.mcs_curve.hide()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e) and "has been deleted" in str(e):
                logger.warning("MCS plot curve was deleted, skipping MCS plot update")
            else:
                raise

    def add_count_rate_mean_line(self, curve_index, mean_value):
        """Add a horizontal mean line to the count rate plot."""
        if not hasattr(self, 'count_rate_window') or self.count_rate_window is None:
            return

        try:
            curve_name = f"Curve{curve_index}" if curve_index < 4 else "All"
            mean_line = self.count_rate_window.count_rate_plot_widget.hline(
                mean_value,
                pen=chiplot.to_pen("r", width=2, style="dash"),
                label=f"{curve_name} Mean: {mean_value:.1f}",
            )
            self.count_rate_window.mean_lines.append(mean_line)

        except Exception as e:
            logger.warning(f"Could not add mean line for curve {curve_index}: {e}")

    # More methods would be added here...
