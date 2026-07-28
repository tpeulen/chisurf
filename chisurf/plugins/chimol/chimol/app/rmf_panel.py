"""RMF inspection dock for Chimol."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui import dialogs

from ..io import RmfNotAvailableError, load_structure_payload


class RmfPlotWidget(QtWidgets.QWidget):
    """Small dependency-free line plot for RMF frame series."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Create the RMF plot widget."""
        super().__init__(parent)
        self.values = np.asarray([], dtype=float)
        self.current_frame = 0
        self.setMinimumHeight(160)

    def set_data(self, values: object, current_frame: int = 0) -> None:
        """Set plottable values and the active frame index."""
        self.values = np.asarray(values, dtype=float)
        self.current_frame = int(current_frame)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 - Qt API
        """Paint the series, axes, and current-frame marker."""
        del event
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(255, 255, 255))

        rect = self.rect().adjusted(38, 12, 12, 28)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            painter.setPen(QtGui.QColor(120, 120, 120))
            painter.drawText(rect, QtCore.Qt.AlignCenter, "No numeric RMF frame series")
            return

        y_min = float(np.min(finite))
        y_max = float(np.max(finite))
        if y_max == y_min:
            y_max += 1.0
            y_min -= 1.0

        def to_point(index: int, value: float) -> QtCore.QPoint:
            x = rect.left() + (index / max(1, len(self.values) - 1)) * rect.width()
            y = rect.bottom() - ((value - y_min) / (y_max - y_min)) * rect.height()
            return QtCore.QPoint(int(round(x)), int(round(y)))

        painter.setPen(QtGui.QColor(210, 210, 210))
        painter.drawRect(rect)
        painter.setPen(QtGui.QColor(160, 160, 160))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())

        painter.setPen(QtGui.QColor(40, 90, 180))
        path = QtGui.QPainterPath()
        first = True
        for index, value in enumerate(self.values):
            if not np.isfinite(value):
                first = True
                continue
            point = to_point(index, float(value))
            if first:
                path.moveTo(point)
                first = False
            else:
                path.lineTo(point)
        painter.drawPath(path)

        frame = max(0, min(int(self.current_frame), max(0, len(self.values) - 1)))
        if len(self.values) > 0:
            marker_x = rect.left() + (frame / max(1, len(self.values) - 1)) * rect.width()
            painter.setPen(QtGui.QPen(QtGui.QColor(220, 40, 40), 2))
            painter.drawLine(int(marker_x), rect.top(), int(marker_x), rect.bottom())
            painter.drawText(
                rect.adjusted(0, 0, 0, -4),
                QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom,
                str(frame + 1),
            )


class RmfPanel(QtCore.QObject):
    """Panel for RMF features and frame-score plotting (no outer QDockWidget)."""

    def __init__(self, parent: QtWidgets.QMainWindow, viewer: object) -> None:
        """Create the RMF panel attached to *viewer*."""
        super().__init__(parent)
        self.parent_window = parent
        self.viewer = viewer

        self._widget = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # The resolution chooser sits above the frame series because it decides
        # *what you are looking at*, where the series only decides what is
        # plotted. It hides itself entirely for a file that states one
        # representation, which is almost all of them -- a chooser offering one
        # choice is worse than no chooser.
        self.resolution_row = QtWidgets.QWidget(self._widget)
        resolution_layout = QtWidgets.QHBoxLayout(self.resolution_row)
        resolution_layout.setContentsMargins(0, 0, 0, 0)
        resolution_label = QtWidgets.QLabel("Resolution", self.resolution_row)
        resolution_label.setStyleSheet("font-weight: bold;")
        resolution_layout.addWidget(resolution_label)
        self.resolution_combo = QtWidgets.QComboBox(self.resolution_row)
        self.resolution_combo.setToolTip(
            "Which depiction of this model to draw. IMP resolution is residues "
            "per bead, so a larger number is coarser. Choosing one does not "
            "disturb what you switched off in the hierarchy."
        )
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)
        resolution_layout.addWidget(self.resolution_combo, stretch=1)
        layout.addWidget(self.resolution_row)
        self.resolution_row.setVisible(False)

        header = QtWidgets.QLabel("RMF frame series")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.series_combo = QtWidgets.QComboBox(self._widget)
        self.series_combo.currentIndexChanged.connect(self._on_series_changed)
        layout.addWidget(self.series_combo)

        self.plot = RmfPlotWidget(self._widget)
        layout.addWidget(self.plot, stretch=1)

        self.value_label = QtWidgets.QLabel("Current: --")
        layout.addWidget(self.value_label)

        button_row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh RMF", self._widget)
        self.refresh_button.clicked.connect(self.refresh_active_rmf)
        button_row.addWidget(self.refresh_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    @property
    def widget(self) -> QtWidgets.QWidget:
        """Return the content widget."""
        return self._widget

    #: What the chooser calls "show every representation at once". Superimposing
    #: them is occasionally wanted for comparison and is never a useful default.
    ALL_RESOLUTIONS = "all (superimposed)"

    def set_state(self, state: object | None) -> None:
        """Update the panel for the active Chimol object state."""
        self._refresh_resolutions(state)

        series = getattr(state, "rmf_frame_series", {}) if state is not None else {}
        if not isinstance(series, dict):
            series = {}

        current = self.series_combo.currentText()
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        names = [name for name, values in series.items() if _has_numeric_values(values)]
        self.series_combo.addItems(names)
        if current in names:
            self.series_combo.setCurrentText(current)
        self.series_combo.blockSignals(False)
        self._update_plot()

    def _refresh_resolutions(self, state: object | None) -> None:
        """Offer the resolutions this object holds, or nothing at all.

        Parameters
        ----------
        state : object or None
            The active object's render state.
        """
        available = list(getattr(state, "rmf_resolutions", []) or [])
        self.resolution_row.setVisible(bool(available))
        if not available:
            return

        # What is *currently* drawn, so the box shows the truth rather than
        # resetting the user's choice every time the panel is refreshed.
        current = None
        resolutions = getattr(state, "resolutions", None)
        chosen = getattr(state, "representation_mask", None)
        if resolutions is not None and chosen is not None:
            shown = {
                float(v)
                for v in np.unique(np.asarray(resolutions)[np.asarray(chosen, bool)])
                if np.isfinite(v)
            }
            if len(shown) == 1:
                current = f"{shown.pop():g}"
            elif len(shown) > 1:
                current = self.ALL_RESOLUTIONS

        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()
        self.resolution_combo.addItems([f"{value:g}" for value in available])
        self.resolution_combo.addItem(self.ALL_RESOLUTIONS)
        if current is not None:
            self.resolution_combo.setCurrentText(current)
        self.resolution_combo.blockSignals(False)

    def _on_resolution_changed(self, index: int) -> None:
        """Draw the chosen representation."""
        del index
        text = self.resolution_combo.currentText()
        if not text:
            return
        try:
            wanted = None if text == self.ALL_RESOLUTIONS else [float(text)]
        except ValueError:
            return
        self.viewer.set_visible_resolutions(wanted)

    def _on_series_changed(self, index: int) -> None:
        """Refresh the plot when the selected series changes."""
        del index
        self._update_plot()

    def _update_plot(self) -> None:
        """Draw the selected frame series."""
        state = _active_state(self.viewer)
        series = getattr(state, "rmf_frame_series", {}) if state is not None else {}
        if not isinstance(series, dict):
            series = {}

        name = self.series_combo.currentText()
        values = series.get(name, []) if name else []
        current = getattr(state, "active_frame", None)
        if current is None:
            try:
                current = self.viewer.get_current_frame()
            except Exception:
                current = 0

        self.plot.set_data(values, int(current or 0))
        arr = np.asarray(values, dtype=float)
        if arr.size == 0 or not np.isfinite(arr).any():
            self.value_label.setText("Current: --")
            return
        frame = max(0, min(int(current or 0), arr.size - 1))
        self.value_label.setText(
            f"{name}: {arr[frame]:.6g}  min={np.nanmin(arr):.6g} max={np.nanmax(arr):.6g}"
        )

    def refresh_active_rmf(self) -> None:
        """Reload the active RMF file from disk."""
        object_id = self.viewer.get_active_object_id()
        if object_id is None:
            return
        store = getattr(self.parent_window, "_object_store", {})
        entry = store.get(object_id, {})
        path = entry.get("path")
        if not path:
            return

        old_frame = 0
        try:
            old_frame = int(self.viewer.get_current_frame())
        except Exception:
            old_frame = 0

        # The same reader the file went through when it was opened, so a refresh
        # cannot produce an object shaped differently from a freshly loaded one.
        try:
            _structure, payload = load_structure_payload(Path(path))
        except RmfNotAvailableError as exc:
            dialogs.warning(self._widget, "RMF Not Available", str(exc))
            return
        except Exception as exc:
            dialogs.warning(self._widget, "RMF Refresh Failed", f"{exc}")
            return

        if payload is None:
            dialogs.warning(
                self._widget, "RMF Refresh Failed", f"Nothing could be read from {path}"
            )
            return

        try:
            self.viewer.apply_payload(payload, object_id=object_id)
            state = _active_state(self.viewer)
            n_frames = getattr(getattr(state, "frames", None), "shape", (0,))[0]
            if n_frames > 0:
                self.viewer.set_current_frame(min(old_frame, n_frames - 1))
            self.set_state(state)
        except Exception as exc:
            dialogs.warning(self._widget, "RMF Refresh Failed", f"{exc}")


def _active_state(viewer: object) -> object | None:
    """Return the active viewer state, or None if unavailable."""
    try:
        return viewer._get_active_state()
    except Exception:
        return None


def _has_numeric_values(values: object) -> bool:
    """Return True when values contain at least one finite numeric value."""
    try:
        arr = np.asarray(values, dtype=float)
    except Exception:
        return False
    return arr.size > 0 and bool(np.isfinite(arr).any())


__all__ = ["RmfPanel", "RmfPlotWidget"]
