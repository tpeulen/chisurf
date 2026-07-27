"""Combined FRET / HomoFRET Calculator Plugin.

Provides heteroFRET and homoFRET parameter calculations in a single tabbed
window, backed by the new client-server architecture.

The Qt tool is resolved lazily (PEP 562), so importing this package — and with it
the ``api`` / ``core`` / ``backend`` layers — needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Main:Tools:FRET-Calculator"

__all__ = ["FretCalculatorTool"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt tool on first access (PEP 562 lazy import)."""
    if attribute == "FretCalculatorTool":
        from .gui.tool import FretCalculatorTool

        return FretCalculatorTool
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


if __name__ == "plugin":
    from .gui.tool import FretCalculatorTool

    window = FretCalculatorTool()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
    try:
        window.raise_()
        window.activateWindow()
    except Exception:
        pass
