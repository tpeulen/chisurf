"""
Trace Browser Plugin

A simple two-page plugin to browse intensity traces from PTU/TTTR files in a folder.
Page 0: Setup definition using DetectorWizardPage (TTTR channel setup).
Page 1: Trace browser with folder selection, file list, star quality rating (0-3),
        annotation text, filter by rating, preview plot, and export selected files.

Metadata (ratings and annotations) are stored in a JSON file in the same folder
as the traces: .trace_browser_meta.json

The Qt workspace (:class:`TraceBrowser` and its helper widgets) lives in
:mod:`.widget` and is resolved lazily (PEP 562), so importing this package -- and
with it the Qt-free ``core`` / ``api`` / ``backend`` / ``cli`` layers and
:mod:`.gui.model` -- needs no Qt binding.  ``from ...trace_browser import
TraceBrowser`` keeps working.
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

#: Names that live in the Qt module :mod:`.widget` and are loaded on first access.
_WIDGET_NAMES = ("TraceBrowser", "StarCombo", "StarRatingWidget", "NoHoverSelectTable")

__all__ = [*_WIDGET_NAMES, "META_FILENAME", "get_tttr_supported_exts"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt widgets and Qt-free helpers on first access (PEP 562)."""
    if attribute in _WIDGET_NAMES:
        from . import widget

        return getattr(widget, attribute)
    if attribute == "META_FILENAME":
        from .core.metadata import META_FILENAME

        return META_FILENAME
    if attribute == "get_tttr_supported_exts":
        from .gui.model import get_tttr_supported_exts

        return get_tttr_supported_exts
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


# When the plugin is loaded as a module with __name__ == "plugin",
# this code will be executed by the Plugin Manager
if __name__ == "plugin":
    from chisurf.plugins.tttr.trace_browser.gui.tool import TraceBrowserTool

    window = TraceBrowserTool()
    window.show()
    window.raise_()
    window.activateWindow()
