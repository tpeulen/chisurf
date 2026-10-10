"""Capture the populated retained Qt GPU widget before native migration."""

from pathlib import Path

from qtpy.QtWidgets import QApplication

from ..gui.tool import NumberQuestWidget


def populate(view):
    view.game.reset(target=37)
    for value in (50, 25):
        view.estimate = value
        view.submit()
    view.estimate = 37


def main():
    app = QApplication.instance() or QApplication([])
    window = NumberQuestWidget()
    window.show()
    app.processEvents()
    populate(window.game)
    window.host.ctx.canvas.force_draw()
    app.processEvents()
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    window.grab().save(str(out / "qt-widget-reference.png"))
    window.host.close()
    window.close()


if __name__ == "__main__":
    main()
