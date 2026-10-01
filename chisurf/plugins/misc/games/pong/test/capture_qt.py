"""Capture the retained Qt view with its genuine GPU canvas populated."""
from pathlib import Path

from qtpy.QtWidgets import QApplication

from ..pong import Pong


def main():
    app = QApplication.instance() or QApplication([])
    window = Pong()
    window.show()
    app.processEvents()
    window.host.ctx.canvas.force_draw()
    app.processEvents()
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    window.grab().save(str(out / "qt-widget-reference.png"))
    window.host.close()
    window.close()


if __name__ == "__main__":
    main()
