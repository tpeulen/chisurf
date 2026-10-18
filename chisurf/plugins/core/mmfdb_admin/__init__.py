"""mmfdb-admin: Multiparametric Fluorescence Database management.

The window is the native emtk app (``gui/app.py``, ``entrypoints.emtk`` in the
manifest); the shell opens it. Importing the package imports no GUI toolkit.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:System:MMFDB Admin"

__all__ = ["name"]


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "mmfdb_admin"])
