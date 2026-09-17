"""
Single-Molecule Acquisition

This plugin provides tools for acquiring single molecule data using various TCSPC hardware.
It displays fluorescence decays of user-defined channels (up to 4) and correlation curves.
Data is acquired into RAM and saved at the end of data acquisition.

Supported hardware:
- Becker & Hickl SPC 830/150/160/180 devices
- PicoQuant devices (using snAPI)

Features:
- Acquisition of time-tagged time-resolved (TTTR) data
- Display of fluorescence decays for up to 4 user-defined channels
- Display of correlation curves
- Configurable acquisition time
- RAM usage monitoring
- Data saving at the end of acquisition

The plugin is designed for single-molecule experiments where real-time monitoring of
fluorescence decays and correlation curves is essential for data quality assessment
and experimental optimization.
"""

name = "Main:Tools:Acquisition"

import logging as _py_logging
import os
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Optional GUI / plugin imports
# ---------------------------------------------------------------------------

GUI_AVAILABLE = False

try:
    from qtpy.QtCore import Qt, QThread, QTimer, Signal
    from qtpy.QtWidgets import (
        QAction,
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
        QMdiSubWindow,
        QMenuBar,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    from chisurf.gui import chiplot

    GUI_AVAILABLE = True
except Exception:  # Qt stack not available – CLI-only use is still allowed
    GUI_AVAILABLE = False


if GUI_AVAILABLE:
    # Import the BH SPC wrapper from the BH-specific subpackage
    # Import tttrlib for correlation
    import tttrlib

    import chisurf
    from chisurf import logging

    # Import for saving data
    from chisurf.core.fio.ascii import save_xy
    from chisurf.core.fio.fluorescence.fcs.kristine import write_kristine

    # Import controller classes
    from .gui.controllers import *  # noqa: F401,F403

    # Import main classes
    from .gui.tool import AcquisitionThread, SMAcquisitionManager

    # Import window classes
    from .gui.windows import *  # noqa: F401,F403

    # Use the tcspc_devices for the generic TCSPCDevice factory
    from .tcspc_devices import TCSPCDevice
    from .tcspc_devices.bh_spc import (
        BHSPC,
        BHSPCCardSetupDialog,
        DLLOperationMode,
        InitStatus,
        ParID,
        SPCMError,
        ini_file,
        minimal_spcm_ini,
    )

    # Module-level logger for this file (chisurf logging)
    logger = logging.getLogger(__name__)
else:
    # Fallback logger when GUI/plugin stack is not available
    logger = _py_logging.getLogger(__name__)
# Initialize the plugin when loaded (only when GUI stack is available)
if __name__ == "plugin" and GUI_AVAILABLE:
    logger.info("Loading SM Acquisition plugin...")
    acquisition_manager = SMAcquisitionManager()
