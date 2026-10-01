"""Capture a populated retained Qt LFCS widget for visual comparison."""

from pathlib import Path

from qtpy.QtWidgets import QApplication

from ..gui.tool import LifetimeFcsSimWidget


def _datasets():
    x = [1e-3, 1e-2, 1e-1, 1.0]
    return [
        {"x": x, "y": [2.0, 1.6, 1.2, 1.0], "species_a": 0, "species_b": 0, "name": "τ=1 ns"},
        {"x": x, "y": [2.4, 1.8, 1.25, 1.0], "species_a": 1, "species_b": 1, "name": "τ=4 ns"},
        {"x": x, "y": [1.7, 1.4, 1.15, 1.0], "species_a": 0, "species_b": 1, "name": "cross"},
    ]


def main() -> None:
    app = QApplication.instance() or QApplication([])
    widget = LifetimeFcsSimWidget()
    widget.resize(980, 700)
    widget.show()
    widget._refresh_plot(_datasets())
    app.processEvents()
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    widget.grab().save(str(out / "qt-populated.png"))
    widget.close()


if __name__ == "__main__":
    main()

