"""A distribution with thresholds dragged along it — the shared level editor.

Picking a threshold is an act of *looking at the data*. Nobody knows in advance
what level shows a density, separates a burst population, or cuts a photon-count
image: the scales differ by orders of magnitude between one dataset and the next,
so a number typed blind is a guess followed by a re-render. Drawing the value
distribution and letting the level be dragged along it replaces that with one
continuous motion, with the data visible underneath while it happens.

Every tool that needs this was going to hand-roll it, so it lives here and is
reachable from any ``.view.json`` through the ``level_histogram`` section.

Interaction
-----------
* **drag** a marker to move its level;
* **click** empty histogram to add one there;
* **right-click** a marker to remove it;
* a value can still be typed, for when it is known exactly.

Counts are drawn on a log scale by default. Most real distributions here are
overwhelmingly background — the interesting fraction of a per cent is a flat
line at zero on a linear axis, which defeats the point of drawing it.
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

#: How close to a marker a click counts as being on it, in pixels.
GRAB_PIXELS = 6


class LevelHistogramView(QtWidgets.QWidget):
    """Bare histogram canvas with draggable markers, free of any model.

    Usable on its own by non-AutoForm code; :class:`LevelHistogramWidget` is the
    model-bound wrapper.
    """

    levelMoved = QtCore.Signal(int, float)
    levelAdded = QtCore.Signal(float)
    levelRemoved = QtCore.Signal(int)
    levelSelected = QtCore.Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        log_counts: bool = True,
        allow_add: bool = True,
        allow_remove: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self._log_counts = bool(log_counts)
        self._allow_add = bool(allow_add)
        self._allow_remove = bool(allow_remove)
        self._counts: np.ndarray | None = None
        self._edges: np.ndarray | None = None
        self._levels: list[dict] = []
        self._dragging: int | None = None
        self._selected: int | None = None
        self._placeholder = "no data"

    # ------------------------------------------------------------------ #
    def set_histogram(self, counts, edges) -> None:
        """Set the distribution to draw; ``None`` clears it."""
        self._counts = None if counts is None else np.asarray(counts, dtype=float)
        self._edges = None if edges is None else np.asarray(edges, dtype=float)
        self.update()

    def set_levels(self, levels) -> None:
        """Set the markers. Each is a dict with at least ``level``."""
        self._levels = [dict(entry) for entry in (levels or [])]
        if self._selected is not None and self._selected >= len(self._levels):
            self._selected = None
        self.update()

    def set_placeholder(self, text: str) -> None:
        """What to show when there is no distribution."""
        self._placeholder = text
        self.update()

    def selected_index(self) -> int | None:
        """Which marker the surrounding controls act on."""
        return self._selected

    def select(self, index: int | None) -> None:
        """Pick a marker without the mouse."""
        self._selected = index
        self.update()

    def clear(self) -> None:
        self._counts = self._edges = None
        self._levels = []
        self._selected = self._dragging = None
        self.update()

    # ------------------------------------------------------------------ #
    def _value_range(self):
        if self._edges is None or self._edges.size < 2:
            return None
        return float(self._edges[0]), float(self._edges[-1])

    def value_to_x(self, value: float) -> float:
        span = self._value_range()
        if span is None:
            return 0.0
        low, high = span
        if high <= low:
            return 0.0
        return (value - low) / (high - low) * max(self.width() - 1, 1)

    def x_to_value(self, x: float) -> float:
        span = self._value_range()
        if span is None:
            return 0.0
        low, high = span
        fraction = min(max(x / max(self.width() - 1, 1), 0.0), 1.0)
        return low + fraction * (high - low)

    def _marker_at(self, x: float) -> int | None:
        best, best_distance = None, float(GRAB_PIXELS)
        for index, entry in enumerate(self._levels):
            try:
                distance = abs(self.value_to_x(float(entry["level"])) - x)
            except (KeyError, TypeError, ValueError):
                continue
            if distance <= best_distance:
                best, best_distance = index, distance
        return best

    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        if self._counts is None or self._edges is None or self._counts.size == 0:
            painter.setPen(self.palette().mid().color())
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self._placeholder)
            return

        height, width = self.height(), max(self.width(), 1)
        scaled = np.log1p(self._counts) if self._log_counts else self._counts
        peak = float(scaled.max()) if scaled.size else 0.0
        if peak > 0:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(self.palette().mid())
            columns = np.linspace(0, width, self._counts.size + 1)
            for index in range(self._counts.size):
                bar = scaled[index] / peak * (height - 4)
                if bar <= 0:
                    continue
                left = columns[index]
                painter.drawRect(
                    QtCore.QRectF(
                        left,
                        height - bar,
                        max(columns[index + 1] - left, 1.0),
                        bar,
                    )
                )

        for index, entry in enumerate(self._levels):
            try:
                level = float(entry["level"])
            except (KeyError, TypeError, ValueError):
                continue
            x = self.value_to_x(level)
            colour = entry.get("color", (1.0, 1.0, 1.0, 1.0))
            try:
                pen_colour = QtGui.QColor.fromRgbF(
                    *[min(max(float(c), 0.0), 1.0) for c in list(colour)[:3]]
                )
            except Exception:
                pen_colour = self.palette().highlight().color()
            selected = index == self._selected
            painter.setPen(QtGui.QPen(pen_colour, 3 if selected else 1))
            painter.drawLine(QtCore.QPointF(x, 0.0), QtCore.QPointF(x, float(height)))
            # A grab handle, so a marker can be caught without hitting a 1px line.
            painter.setBrush(pen_colour)
            size = 5.0 if selected else 4.0
            painter.drawRect(QtCore.QRectF(x - size, 0.0, size * 2.0, size * 2.0))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _event_x(event) -> float:
        position = getattr(event, "position", None)
        return float(position().x()) if callable(position) else float(event.x())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._edges is None:
            return
        x = self._event_x(event)
        index = self._marker_at(x)
        if event.button() == QtCore.Qt.RightButton:
            if index is not None and self._allow_remove:
                self.levelRemoved.emit(index)
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        if index is None:
            if self._allow_add:
                self.levelAdded.emit(self.x_to_value(x))
            return
        self._dragging = index
        self._selected = index
        self.levelSelected.emit(index)
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        x = self._event_x(event)
        if self._dragging is None:
            near = self._edges is not None and self._marker_at(x) is not None
            self.setCursor(QtCore.Qt.SizeHorCursor if near else QtCore.Qt.ArrowCursor)
            return
        self.levelMoved.emit(self._dragging, self.x_to_value(x))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._dragging = None


class LevelHistogramWidget(QtWidgets.QWidget):
    """Model-bound level editor: the histogram plus its value/colour controls.

    The model owns the levels; this is a view of them. Nothing is cached here,
    so the widget and the model cannot drift -- every edit is written through
    and then re-read.

    Parameters
    ----------
    model : object
        The view-model.
    target : str
        Attribute holding the levels: a list of dicts with ``level`` and
        optionally ``color`` and ``style``. A bare list of numbers is accepted
        and normalised.
    source : str
        Name of a **method** returning ``(counts, edges)``. It must be a method,
        not a property -- AutoForm resolves sources by call, and a property
        leaves the section blank with no error.
    range_source : str, optional
        Method returning ``(low, high)``, used to clamp typed and dragged
        values. Falls back to the histogram edges.
    on_change : str, optional
        Method called after every edit, so the model can redraw.
    styles : list of str, optional
        Offered in a style menu per level; omitted means no style control.
    log_counts, allow_add, allow_remove : bool
        See :class:`LevelHistogramView`.
    """

    #: AutoForm refreshes widgets carrying this flag through ``sync_fields``
    #: and ``refresh_plots``; the level editor has to follow the model like any
    #: plot does, or a map loaded after the panel was built shows nothing.
    AUTOFORM_REFRESH = True

    def __init__(
        self,
        model,
        target: str,
        *,
        source: str = "",
        range_source: str = "",
        on_change: str = "",
        styles=None,
        log_counts: bool = True,
        allow_add: bool = True,
        allow_remove: bool = True,
        placeholder: str = "no data",
        **_ignored,
    ) -> None:
        super().__init__()
        self._model = model
        self._target = target
        self._source = source
        self._range_source = range_source
        self._on_change = on_change

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(QtWidgets.QLabel("Level", self))
        self._value = QtWidgets.QLineEdit(self)
        self._value.setMaximumWidth(100)
        self._value.setToolTip(
            "Exact value for the selected level. Dragging its marker does the same thing by eye."
        )
        self._value.returnPressed.connect(self._value_typed)
        controls.addWidget(self._value)

        self._range = QtWidgets.QLabel("", self)
        self._range.setToolTip("The values the data actually spans")
        controls.addWidget(self._range)

        self._styles = list(styles or [])
        self._style = QtWidgets.QComboBox(self)
        if self._styles:
            self._style.addItems(self._styles)
            self._style.currentTextChanged.connect(self._style_changed)
            controls.addWidget(self._style)
        else:
            self._style.hide()

        self._colour = QtWidgets.QToolButton(self)
        self._colour.setText("🎨")
        self._colour.setToolTip("Colour of the selected level")
        self._colour.clicked.connect(self._pick_colour)
        controls.addWidget(self._colour)

        remove = QtWidgets.QToolButton(self)
        remove.setText("➖")
        remove.setToolTip("Remove the selected level (or right-click its marker)")
        remove.clicked.connect(self._remove_selected)
        controls.addWidget(remove)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.view = LevelHistogramView(
            self,
            log_counts=log_counts,
            allow_add=allow_add,
            allow_remove=allow_remove,
        )
        self.view.set_placeholder(placeholder)
        self.view.levelMoved.connect(self._level_moved)
        self.view.levelAdded.connect(self._level_added)
        self.view.levelRemoved.connect(self._level_removed)
        self.view.levelSelected.connect(lambda _index: self._sync_controls())
        layout.addWidget(self.view, 1)

        hint = QtWidgets.QLabel(
            "drag a marker to move a level · click to add one · right-click a marker to remove it",
            self,
        )
        hint.setWordWrap(True)
        font = hint.font()
        font.setPointSizeF(max(font.pointSizeF() - 1.0, 8.0))
        hint.setFont(font)
        layout.addWidget(hint)

        self.refresh()

    # ------------------------------------------------------------------ #
    # Reading the model
    # ------------------------------------------------------------------ #
    def _call(self, name: str):
        """Call a named model method, or return ``None``."""
        if not name:
            return None
        function = getattr(self._model, name, None)
        if not callable(function):
            if function is not None:
                logger.warning(
                    "level_histogram: %r is not callable on %s; a source must be "
                    "a method, not a property",
                    name,
                    type(self._model).__name__,
                )
            return None
        try:
            return function()
        except Exception:
            logger.warning("level_histogram: %s() failed", name, exc_info=True)
            return None

    def _levels(self) -> list[dict]:
        raw = getattr(self._model, self._target, None) or []
        levels = []
        for entry in raw:
            if isinstance(entry, dict):
                levels.append(dict(entry))
            else:
                try:
                    levels.append({"level": float(entry)})
                except (TypeError, ValueError):
                    continue
        return levels

    def _bounds(self):
        span = self._call(self._range_source)
        if span is not None:
            try:
                low, high = float(span[0]), float(span[1])
                if high > low:
                    return low, high
            except (TypeError, ValueError, IndexError):
                pass
        histogram = self._call(self._source)
        if histogram is not None:
            try:
                edges = np.asarray(histogram[1], dtype=float)
                if edges.size >= 2 and edges[-1] > edges[0]:
                    return float(edges[0]), float(edges[-1])
            except Exception:
                pass
        return None

    def refresh(self) -> None:
        """Re-read everything from the model. AutoForm's refresh entry point.

        Named ``refresh`` because that is what ``AutoForm.sync_fields`` looks
        for, alongside ``sync``.
        """
        histogram = self._call(self._source)
        if histogram is None:
            self.view.clear()
            self._range.setText("")
            self._value.setText("")
            self.setEnabled(False)
            return
        self.setEnabled(True)
        try:
            counts, edges = histogram
        except (TypeError, ValueError):
            self.view.clear()
            return
        self.view.set_histogram(counts, edges)
        self.view.set_levels(self._levels())
        bounds = self._bounds()
        self._range.setText("" if bounds is None else f"{bounds[0]:.4g} … {bounds[1]:.4g}")
        self._sync_controls()

    # ------------------------------------------------------------------ #
    # Writing to the model
    # ------------------------------------------------------------------ #
    def _apply(self, levels) -> None:
        setattr(self._model, self._target, levels)
        self._call(self._on_change)
        self.view.set_levels(self._levels())
        self._sync_controls()

    def _clamped(self, value: float) -> float | None:
        bounds = self._bounds()
        if bounds is None or not np.isfinite(value):
            return None
        low, high = bounds
        # Held just inside the range: a level exactly at an extreme selects
        # everything or nothing, and arriving there by dragging is confusing.
        margin = (high - low) * 1e-4
        return float(min(max(value, low + margin), high - margin))

    def _index(self) -> int | None:
        index = self.view.selected_index()
        levels = self._levels()
        if index is None or index >= len(levels):
            return 0 if levels else None
        return index

    def _sync_controls(self) -> None:
        levels = self._levels()
        index = self._index()
        if index is None:
            self._value.setText("")
            return
        entry = levels[index]
        self._value.setText(f"{float(entry.get('level', 0.0)):.6g}")
        style = str(entry.get("style", ""))
        if self._styles and style in self._styles:
            self._style.blockSignals(True)
            self._style.setCurrentText(style)
            self._style.blockSignals(False)
        colour = entry.get("color", (1.0, 1.0, 1.0, 1.0))
        try:
            self._colour.setStyleSheet(
                "QToolButton { background-color: rgb(%d,%d,%d); }"
                % tuple(int(min(max(float(c), 0.0), 1.0) * 255) for c in list(colour)[:3])
            )
        except Exception:
            pass

    def _level_moved(self, index: int, value: float) -> None:
        levels = self._levels()
        clamped = self._clamped(value)
        if index >= len(levels) or clamped is None:
            return
        levels[index] = dict(levels[index], level=clamped)
        self._apply(levels)

    def _level_added(self, value: float) -> None:
        clamped = self._clamped(value)
        if clamped is None:
            return
        levels = self._levels()
        template = levels[-1] if levels else {}
        entry = {"level": clamped, "color": template.get("color", (0.5, 0.7, 1.0, 1.0))}
        if self._styles:
            entry["style"] = self._style.currentText()
        levels.append(entry)
        self._apply(levels)

    def _level_removed(self, index: int) -> None:
        levels = self._levels()
        if index >= len(levels):
            return
        del levels[index]
        self.view.select(None)
        self._apply(levels)

    def _remove_selected(self) -> None:
        index = self._index()
        if index is not None:
            self._level_removed(index)

    def _value_typed(self) -> None:
        try:
            value = float(self._value.text())
        except ValueError:
            self._sync_controls()
            return
        index = self._index()
        if index is None:
            self._level_added(value)
        else:
            self._level_moved(index, value)

    def _style_changed(self, style: str) -> None:
        index = self._index()
        levels = self._levels()
        if index is None or index >= len(levels):
            return
        levels[index] = dict(levels[index], style=style)
        self._apply(levels)

    def _pick_colour(self) -> None:
        index = self._index()
        levels = self._levels()
        if index is None or index >= len(levels):
            return
        current = levels[index].get("color", (1.0, 1.0, 1.0, 1.0))
        try:
            initial = QtGui.QColor.fromRgbF(
                *[min(max(float(c), 0.0), 1.0) for c in list(current)[:4]]
            )
        except Exception:
            initial = QtGui.QColor(255, 255, 255)
        chosen = QtWidgets.QColorDialog.getColor(
            initial, self, "Level colour", QtWidgets.QColorDialog.ShowAlphaChannel
        )
        if not chosen.isValid():
            return
        levels[index] = dict(
            levels[index],
            color=(chosen.redF(), chosen.greenF(), chosen.blueF(), chosen.alphaF()),
        )
        self._apply(levels)


__all__ = ["LevelHistogramView", "LevelHistogramWidget"]
