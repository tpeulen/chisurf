"""Capture the retained Qt GPU view, including a populated rally."""
from pathlib import Path

from qtpy.QtWidgets import QApplication

from ..breakout import Breakout
from .capture_native import populate


def main():
    app = QApplication.instance() or QApplication([])
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    for mode in ("serve", "rally"):
        window = Breakout()
        window.show()
        app.processEvents()
        if mode != "serve":
            populate(window, mode)
        window.host.ctx.canvas.force_draw()
        app.processEvents()
        window.grab().save(str(out/f"qt-widget-{mode}.png"))
        window.host.close()
        window.close()


if __name__ == "__main__":
    main()
