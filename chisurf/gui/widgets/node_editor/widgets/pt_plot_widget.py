from __future__ import annotations

from typing import Sequence

from qtpy import QtCore, QtWidgets

from chisurf.gui import chiplot as cp

from ..theme import color as theme_color, metric as theme_metric


def _plotting_available() -> bool:
    """Whether a chiplot backend is usable (pyqtgraph installed)."""
    try:
        cp.get_backend()
        return True
    except Exception:  # pragma: no cover - fallback when the backend is missing
        return False


class PtPlotWidget(QtWidgets.QWidget):
    """Small 2D plot widget for PT graphs, drawn through chiplot when available.

    The surrounding node is expected to call :meth:`set_data` with matching
    x/y sequences. When no plotting backend is available, a simple text
    placeholder is shown instead so the node editor still functions.
    """

    def __init__(self, title: str = "Damped sine", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._title_label = QtWidgets.QLabel(title, self)
        self._title_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        layout.addWidget(self._title_label)

        self._plot_widget = None
        self._curve = None

        if _plotting_available():
            w = cp.Plot(self)

            # Make the widget itself transparent so only the plot area draws.
            try:
                w.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
                w.setAutoFillBackground(False)
            except Exception:
                pass

            # Background and line/axis colors driven by theme so the plot
            # integrates with the node editor's dark UI.
            fg = theme_color("plot_foreground", (235, 235, 235))
            bg_base = theme_color("plot_background", (0, 0, 0))
            try:
                opacity = float(theme_metric("plot_background_opacity", 0.0))
            except Exception:
                opacity = 0.0

            # Inner plot background: an explicit RGBA with configurable alpha so
            # the plot area can be fully transparent over the node background.
            try:
                alpha_bg = int(max(0.0, min(1.0, opacity)) * 255.0)
                w.set_background(cp.to_color(bg_base).with_alpha(alpha_bg))
            except Exception:
                pass

            # Thin, themed plot line and axes.
            try:
                line_width = float(theme_metric("plot_line_width", 1.5))
            except Exception:
                line_width = 1.5
            if line_width <= 0.0:
                line_width = 1.0

            try:
                w.grid(x=True, y=True, alpha=0.2)
            except Exception:
                pass

            self._curve = w.line([], [], pen=fg, width=line_width)

            # Axis lines and tick labels in the same foreground color — a
            # pyqtgraph-specific axis-theming detail reached via the backend
            # escape hatch (chiplot has no native axis-pen verb yet).
            try:
                axis_pen = cp.get_backend().raw_module().mkPen(fg)
                for name in ("bottom", "left"):
                    ax = w.native.getAxis(name)
                    ax.setPen(axis_pen)
                    ax.setTextPen(axis_pen)
            except Exception:
                pass

            self._plot_widget = w
            layout.addWidget(w, 1)
        else:
            placeholder = QtWidgets.QLabel("plotting backend not available", self)
            placeholder.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(placeholder, 1)

    # ----- API -----------------------------------------------------------
    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_data(self, x: Sequence[float] | None, y: Sequence[float] | None) -> None:
        if self._curve is None or x is None or y is None:
            return
        try:
            self._curve.set_data(list(x), list(y))
        except Exception:
            pass

    def clear(self) -> None:
        if self._curve is None:
            return
        try:
            self._curve.set_data([], [])
        except Exception:
            pass
