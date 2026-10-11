"""
Trace Browser Plugin

A simple two-page plugin to browse intensity traces from PTU/TTTR files in a folder.
Page 0: Setup definition using DetectorWizardPage (TTTR channel setup).
Page 1: Trace browser with folder selection, file list, star quality rating (0-3),
        annotation text, filter by rating, preview plot, and export selected files.

Metadata (ratings and annotations) are stored in a JSON file in the same folder
as the traces: .trace_browser_meta.json

The window is the native emtk app :mod:`.gui.app`; its state is :mod:`.gui.model`, so importing this
package -- and with it the Qt-free ``core`` / ``api`` / ``backend`` / ``cli`` layers -- needs no Qt binding.
(The Qt workspace, ``TraceBrowser``, was retired with the pyqtgraph dependency.)
"""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(pathlib.Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Spectroscopy:Single-Molecule:Trace Browser"
    cli_entrypoint = ""

__all__ = ["META_FILENAME", "get_tttr_supported_exts"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt-free helpers on first access (PEP 562)."""
    if attribute == "META_FILENAME":
        from .core.metadata import META_FILENAME

        return META_FILENAME
    if attribute == "get_tttr_supported_exts":
        from .gui.model import get_tttr_supported_exts

        return get_tttr_supported_exts
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


# When the plugin is loaded as a module with __name__ == "plugin",
# this code will be executed by the Plugin Manager
if (
    __name__ == "plugin"
):  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.tttr.trace_browser.gui.app import make_app

    window = ControlHost(make_app())
    window.show()
