"""2D Fluorescence Lifetime Correlation Spectroscopy (2D-FLCS) plugin.

Build 2D fluorescence-decay correlation maps from TTTR photon streams, resolve the
fluorescence-lifetime species by inverse-Laplace analysis (fast Tikhonov / NNLS or
faithful maximum-entropy), and read out their interconversion as a lifetime-filtered
(species-resolved) correlation.

The Qt-free pipeline lives in :mod:`chisurf.plugins.fcs.flc_2d.api`; the GUI is the
declarative AutoForm tool :class:`chisurf.plugins.fcs.flc_2d.gui.tool.FlcTwoDTool`.
Method: Ishii & Tahara, J. Phys. Chem. B 117(39), 11414ff (2013),
doi:10.1021/jp406861u, doi:10.1021/jp406864e; application: Kondo et al., PNAS
116(23), 11247-11252 (2019), doi:10.1073/pnas.1821207116. Based on the MATLAB
code by T. Kondo (Schlau-Cohen Lab): ``TK_Create2DFDC_04``,
``TK_FitF_2DMEM_07`` et al.
"""

import logging
from pathlib import Path
from typing import Any

name = "Spectroscopy:Fluorescence Correlation Spectroscopy:2D-FLCS"

# Hidden from the menu: surfaced inside the FCS Toolbox meta tool.
menu_hidden = True

# The Qt classes are built on first access (PEP 562), so importing this package -- and
# with it ``gui.app``, ``gui.model``, ``api`` and ``backend`` -- needs no Qt binding.
_LAZY = ("FlcTwoDTool", "TwoDFLCPlugin", "TwoDFCSPlugin", "icon", "window")


def _build() -> None:
    """Create the Qt plugin window class, icon and aliases (needs a Qt binding)."""
    from qtpy.QtGui import QIcon
    from qtpy.QtWidgets import QWidget

    try:
        from chisurf.gui.misc_helpers import persist_plugin_state
    except ImportError:
        persist_plugin_state = lambda n: lambda c: c  # noqa: E731

    try:
        from chisurf.plugins.fcs.flc_2d.gui import FlcTwoDTool
    except Exception:  # noqa: BLE001 - fall back so discovery never hard-fails
        FlcTwoDTool = None

    try:
        _png = Path(__file__).parent / "icon.png"
        icon = QIcon(str(_png)) if _png.exists() else QIcon()
    except Exception:  # noqa: BLE001
        icon = QIcon()

    if FlcTwoDTool is not None:

        @persist_plugin_state("flc_2d")
        class TwoDFLCPlugin(FlcTwoDTool):
            """Main 2D-FLC plugin window."""

            def __init__(self):
                super().__init__()
                self.setWindowTitle("2D-FLCS Analysis")
                try:
                    self.setWindowIcon(icon)
                except Exception:  # noqa: BLE001
                    pass
                logging.getLogger(__name__).info("2D-FLCS plugin initialized")

    else:

        class TwoDFLCPlugin(QWidget):
            """Fallback widget when the GUI dependencies are missing."""

            def __init__(self):
                super().__init__()
                self.setWindowTitle("2D-FLCS Plugin — import error")
                logging.getLogger(__name__).error("Failed to import FlcTwoDTool")

    globals().update(
        FlcTwoDTool=FlcTwoDTool,
        icon=icon,
        TwoDFLCPlugin=TwoDFLCPlugin,
        # Backwards-compatible alias for older callers / the FCS Toolbox.
        TwoDFCSPlugin=TwoDFLCPlugin,
        window=TwoDFLCPlugin,
    )


def __getattr__(attribute: str) -> Any:
    """Build the Qt half on first access of one of its names."""
    if attribute in _LAZY:
        _build()
        return globals()[attribute]
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


if __name__ == "plugin":
    window = __getattr__("window")()
    window.show()
