"""EMTK-based FitPlotsArea widget for FitSubWindow.

Replaces the legacy PyQt DockArea in FitSubWindow with an EMTK tab bar
and clean page management.
"""

from __future__ import annotations

from typing import Any, Callable

from emtk.qt_host import ControlHost
from qtpy import QtCore, QtWidgets


class FitTabBarControl:
    """EMTK Tab bar control for fit plots."""

    def __init__(self, on_change: Callable[[int], None] | None = None) -> None:
        self.tabs: list[str] = []
        self.current_index: int = 0
        self.hovered_index: int | None = None
        self.on_change = on_change
        self._tab_rects: list[tuple[float, float, float, float]] = []

    def set_tabs(self, tabs: list[str]) -> None:
        self.tabs = list(tabs)

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        painter.fill_rect(x, y, w, h, (30, 32, 38))
        # Divider line at bottom
        painter.fill_rect(x, y + h - 1.0, w, 1.0, (48, 52, 62))

        tx = x + 4.0
        ty = y + 2.0
        th = h - 3.0
        self._tab_rects = []

        line_h = painter.line_height()
        for i, name in enumerate(self.tabs):
            tw = painter.text_width(name) + 24.0
            is_active = i == self.current_index
            is_hovered = i == self.hovered_index

            self._tab_rects.append((tx, ty, tw, th))

            if is_active:
                painter.fill_rect(tx, ty, tw, th, (42, 48, 60))
                # Active bottom accent bar
                painter.fill_rect(tx, ty + th - 2.0, tw, 2.0, (50, 130, 240))
                txt_color = (255, 255, 255)
            elif is_hovered:
                painter.fill_rect(tx, ty, tw, th, (36, 40, 48))
                txt_color = (220, 225, 235)
            else:
                txt_color = (160, 165, 175)

            string_w = painter.text_width(name)
            str_x = tx + (tw - string_w) / 2.0
            str_y = ty + (th - line_h) / 2.0 + 1.0
            painter.text(str_x, str_y, string_w, line_h, 0, name, txt_color, is_active)

            tx += tw + 2.0

    def press(self, px: float, py: float, *args: Any) -> None:
        for i, (rx, ry, rw, rh) in enumerate(self._tab_rects):
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                if i != self.current_index:
                    self.current_index = i
                    if callable(self.on_change):
                        self.on_change(i)
                break

    def hover(self, px: float, py: float, *args: Any) -> None:
        self.hovered_index = None
        for i, (rx, ry, rw, rh) in enumerate(self._tab_rects):
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                self.hovered_index = i
                break


class FitPlotsArea(QtWidgets.QWidget):
    """EMTK-powered tabbed area for fit plots in FitSubWindow.

    Implements the plot_tab_widget contract expected by FitSubWindow,
    Main window, and project persistence.
    """

    currentChanged = QtCore.Signal(int)
    layoutChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[tuple[QtWidgets.QWidget, str]] = []
        self._current_index: int = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar_control = FitTabBarControl(on_change=self.setCurrentIndex)
        self._tab_bar_host = ControlHost(self._tab_bar_control, background=(30, 32, 38))
        self._tab_bar_host.setFixedHeight(28)
        self._tab_bar_host.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        layout.addWidget(self._tab_bar_host)

        self._stack = QtWidgets.QStackedWidget(self)
        layout.addWidget(self._stack)

    # -- Tab management ---------------------------------------------------- #

    def count(self) -> int:
        return len(self._tabs)

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, idx: int) -> None:
        if not (0 <= idx < len(self._tabs)):
            return
        if idx == self._current_index and self._stack.currentIndex() == idx:
            return
        self._current_index = idx
        self._tab_bar_control.current_index = idx
        self._tab_bar_host.update()
        self._stack.setCurrentIndex(idx)
        self.currentChanged.emit(idx)
        self.layoutChanged.emit()

    def currentWidget(self) -> QtWidgets.QWidget | None:
        if 0 <= self._current_index < len(self._tabs):
            return self._tabs[self._current_index][0]
        return None

    def setCurrentWidget(self, widget: QtWidgets.QWidget) -> None:
        idx = self.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def indexOf(self, widget: QtWidgets.QWidget) -> int:
        for i, (w, _) in enumerate(self._tabs):
            if w is widget:
                return i
        return -1

    def widget(self, idx: int) -> QtWidgets.QWidget | None:
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx][0]
        return None

    def tabText(self, idx: int) -> str:
        if 0 <= idx < len(self._tabs):
            return self._tabs[idx][1]
        return ""

    def setTabText(self, idx: int, text: str) -> None:
        if 0 <= idx < len(self._tabs):
            self._tabs[idx] = (self._tabs[idx][0], text)
            self._tab_bar_control.set_tabs([t[1] for t in self._tabs])
            self._tab_bar_host.update()

    def addTab(self, widget: QtWidgets.QWidget, label: str) -> int:
        self._tabs.append((widget, label))
        self._stack.addWidget(widget)
        self._tab_bar_control.set_tabs([t[1] for t in self._tabs])
        self._tab_bar_host.update()
        idx = len(self._tabs) - 1
        if len(self._tabs) == 1:
            self.setCurrentIndex(0)
        return idx

    def removeTab(self, idx: int) -> None:
        if 0 <= idx < len(self._tabs):
            w, _ = self._tabs.pop(idx)
            self._stack.removeWidget(w)
            self._tab_bar_control.set_tabs([t[1] for t in self._tabs])
            if self._current_index >= len(self._tabs):
                self._current_index = max(0, len(self._tabs) - 1)
            self._tab_bar_control.current_index = self._current_index
            self._tab_bar_host.update()
            self._stack.setCurrentIndex(self._current_index)
            self.currentChanged.emit(self._current_index)
            self.layoutChanged.emit()

    def setNewTabButtonVisible(self, visible: bool) -> None:
        pass  # Compatibility no-op

    def showTab(self, idx: int) -> None:
        if 0 <= idx < len(self._tabs):
            self.setCurrentIndex(idx)

    def hideTab(self, idx: int) -> None:
        pass  # Compatibility

    def update(self, *args: Any) -> None:
        super().update(*args)
        self._tab_bar_host.update()
        w = self.currentWidget()
        if w is not None and hasattr(w, "update"):
            try:
                w.update(*args)
            except TypeError:
                w.update()

    # -- Layout state persistence ------------------------------------------ #

    def get_layout_state(self, key_func: Callable[[QtWidgets.QWidget], str] | None = None) -> dict:
        tabs_state = []
        for i, (w, name) in enumerate(self._tabs):
            key = key_func(w) if callable(key_func) else str(i)
            tabs_state.append({"index": i, "name": name, "widget_key": key})
        return {
            "version": 1,
            "type": "emtk_fit_plots_area",
            "current_index": self.currentIndex(),
            "tabs": tabs_state,
            "root": {"type": "tab", "tabs": tabs_state, "current_index": self.currentIndex()},
        }

    def set_layout_state(
        self,
        state: dict,
        key_func: Callable[[QtWidgets.QWidget], str] | None = None,
        emit_change: bool = True,
    ) -> bool:
        if not isinstance(state, dict):
            return False
        applied = False
        current_idx = state.get("current_index")
        if isinstance(current_idx, int) and 0 <= current_idx < self.count():
            if emit_change:
                self.setCurrentIndex(current_idx)
            else:
                self._current_index = current_idx
                self._tab_bar_control.current_index = current_idx
                self._tab_bar_host.update()
                self._stack.setCurrentIndex(current_idx)
            applied = True
        return applied

    # -- Compatibility with DockArea interface ---------------------------- #

    @property
    def _root_widget(self) -> FitPlotsArea:
        return self

    def find_main_tab_widget(self) -> FitPlotsArea:
        return self
