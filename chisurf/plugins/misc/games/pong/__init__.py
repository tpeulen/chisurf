"""Pong Game Plugin

Classic Pong game with CPU opponent, score tracking, and particle effects.
"""

from __future__ import annotations

import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Games:Pong"

def __getattr__(attribute):
    if attribute == "Pong":
        from .pong import Pong
        return Pong
    raise AttributeError(attribute)


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    from .pong import Pong
    app = QApplication(sys.argv)
    game = Pong()
    game.show()
    sys.exit(app.exec())

if __name__ == "plugin":
    from .pong import Pong
    game = Pong()
    game.show()
