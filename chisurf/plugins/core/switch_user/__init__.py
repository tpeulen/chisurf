"""Core plugin for switching the active MMFDB user.

The window is the native emtk app in :mod:`.app`; importing this package needs no Qt binding.
The shell's own start-up sign-in is a shell dialog.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Setup:Switch User"

__all__ = ["name"]
