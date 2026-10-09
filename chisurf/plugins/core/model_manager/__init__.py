from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Models"

description = "Model Manager Plugin for ChiSurf"
icon = "⚙️"


def load():
    """Return the model manager widget."""
    from chisurf.plugins.core.model_manager.gui.tool import ModelManagerWidget

    return ModelManagerWidget()


__all__ = [
    "ModelManagerWidget",
    "load",
    "name",
    "description",
    "icon",
]


def __getattr__(attribute):
    if attribute == "ModelManagerWidget":
        from chisurf.plugins.core.model_manager.gui.tool import ModelManagerWidget

        return ModelManagerWidget
    raise AttributeError(attribute)


if __name__ == "plugin":
    try:
        import chisurf as cs
        from chisurf.core.plugin.registry import apply_manifest_statefulness

        ModelManagerWidget = __getattr__("ModelManagerWidget")
        parent = getattr(cs, "cs", None)
        window = ModelManagerWidget(parent=parent)
        if _manifest is not None:
            apply_manifest_statefulness(window, _manifest)
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception as exc:
        print(f"Failed to open Model Manager: {exc}")
        import traceback

        traceback.print_exc()
