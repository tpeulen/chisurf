"""Tetris Game Plugin

Classic single-player Tetris game with line clearing and next-piece preview.
"""

from __future__ import annotations

import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Games:Tetris"

def __getattr__(attribute):
    if attribute == "Tetris":
        from .tetris import Tetris
        return Tetris
    raise AttributeError(attribute)


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    from .tetris import Tetris
    app = QApplication(sys.argv)
    game = Tetris()
    game.show()
    sys.exit(app.exec())

if __name__ == "plugin":
    from .tetris import Tetris
    game = Tetris()
    game.show()
