"""A compact collection of games for ChiSurf."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🎮"

import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Games"


def load():
    """Return the Games hub widget."""
    from .gui.tool import GamesWidget

    return GamesWidget()


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = load()
    window.show()
    sys.exit(app.exec())


if __name__ == "plugin":
    window = load()
    window.show()
