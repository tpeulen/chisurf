"""Number Quest, a compact guessing-game plugin for ChiSurf."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🔢"

import sys
from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Miscellaneous:Number Quest"


if __name__ == "__main__":
    from qtpy.QtWidgets import QApplication

    from .gui.tool import NumberQuestWidget

    app = QApplication(sys.argv)
    window = NumberQuestWidget()
    window.show()
    sys.exit(app.exec())


if __name__ == "plugin":
    from .gui.tool import NumberQuestWidget

    window = NumberQuestWidget()
    window.show()
