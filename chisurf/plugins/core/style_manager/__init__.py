from __future__ import annotations

from pathlib import Path

import chisurf as cs
from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness


def __getattr__(name):
    if name == "StyleManagerWidget":
        from .gui.tool import StyleManagerWidget

        return StyleManagerWidget
    raise AttributeError(name)


_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Styles"

description = "Style Manager Plugin for ChiSurf"
icon = "🎨"


def load():
    """Return the style manager widget."""
    from .gui.tool import StyleManagerWidget

    return StyleManagerWidget()


__all__ = [
    "StyleManagerWidget",
    "load",
    "name",
    "description",
    "icon",
]

if __name__ == "plugin":
    try:
        from .gui.tool import StyleManagerWidget

        parent = getattr(cs, "cs", None)
        window = StyleManagerWidget(parent=parent)
        if _manifest is not None:
            apply_manifest_statefulness(window, _manifest)
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception as exc:
        print(f"Failed to open Style Manager: {exc}")
        import traceback

        traceback.print_exc()
