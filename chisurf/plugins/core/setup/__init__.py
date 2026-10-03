"""Unified settings package with lazy legacy Qt compatibility."""

name = "Setup:Settings"
description = "Unified Settings Dialog for ChiSurf"
icon = "⚙️"


def __getattr__(key):
    if key == "UnifiedSettingsTool":
        from .gui.tool import UnifiedSettingsTool

        return UnifiedSettingsTool
    raise AttributeError(key)


def load():
    from .gui.tool import UnifiedSettingsTool

    return UnifiedSettingsTool()


__all__ = ["UnifiedSettingsTool", "load", "name", "description", "icon"]

if __name__ == "plugin":
    from pathlib import Path

    import chisurf as cs
    from chisurf.core.plugin import load_manifest
    from chisurf.core.plugin.registry import apply_manifest_statefulness

    window = load()
    manifest = load_manifest(Path(__file__).with_name("manifest.json"))
    if manifest is not None:
        apply_manifest_statefulness(window, manifest)
    window.show()
    window.raise_()
    window.activateWindow()
