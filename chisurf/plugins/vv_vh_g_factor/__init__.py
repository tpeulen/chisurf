"""VV/VH G-Factor Calculator Plugin.

Exposes the VV/VH G-factor GUI tool and registers backend services.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Spectroscopy:Fluorescence decay:VV/VH G-Factor Calculator"
    cli_entrypoint = ""

__all__ = ["GFactorApp", "create_app", "create_host"]


def __getattr__(name):
    """Resolve native factories without importing a toolkit during discovery."""
    if name in __all__:
        from .gui import app

        return getattr(app, name)
    raise AttributeError(name)


if __name__ == "plugin":
    from .__main__ import main

    main()
