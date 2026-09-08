"""ALEX Suite — the classic ALEX-Suite workflow, as a ChiSurf pipeline.

The plugin is a *shell*: every analysis step embeds a tool that already exists
(ALEX Creator, Burst Selection, Background, Accurate FRET, ndX, Burst Browser,
BVA, Trace Browser). What it adds is the **order** those tools are used in, the
names the old program used for them, and the two things the old program had that
ChiSurf did not: a titration / stack-plot analysis and an export that writes the
CSV files ALEX-Suite wrote.
"""

from __future__ import annotations

from pathlib import Path

import chisurf as cs
from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

#: Plugin brand icon (unified emoji set).
icon = "🚦"

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Single-Molecule:ALEX Suite"
description = "The ALEX-Suite workflow, as a linear ChiSurf pipeline."


def load():
    """Return the ALEX Suite window."""
    from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool

    return AlexSuiteTool()


__all__ = ["AlexSuiteTool", "load", "name", "description", "icon"]


def __getattr__(attr_name: str):
    """Expose the Qt window lazily, so importing the package stays Qt-free."""
    if attr_name == "AlexSuiteTool":
        from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool

        return AlexSuiteTool
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


# The plugin *menu* opens a plugin by executing this file with ``__name__`` set
# to ``"plugin"`` -- the legacy macro path. A plugin whose ``__init__`` only
# imports and documents therefore has a dead menu entry, silently: the launcher
# runs the file, nothing happens, and nothing is logged.
if __name__ == "plugin":
    try:
        from chisurf.plugins.burst.alex_suite.gui.tool import AlexSuiteTool

        window = AlexSuiteTool(parent=getattr(cs, "cs", None))
        if _manifest is not None:
            apply_manifest_statefulness(window, _manifest)
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception as exc:  # pragma: no cover - GUI launch path
        print(f"Failed to open the ALEX Suite: {exc}")
        import traceback

        traceback.print_exc()
