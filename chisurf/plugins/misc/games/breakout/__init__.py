"""Breakout Game Plugin

Classic Breakout game with progressive difficulty, multiple brick types,
mouse/keyboard control, and particle effects.
"""

from __future__ import annotations

import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Games:Breakout"


def __getattr__(attribute):
    if attribute == "Breakout":
        from .breakout import Breakout

        return Breakout
    raise AttributeError(attribute)


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    from .breakout import Breakout

    app = QApplication(sys.argv)
    game = Breakout()
    game.show()
    sys.exit(app.exec())

if __name__ == "plugin":
    from .breakout import Breakout

    game = Breakout()
    game.show()
