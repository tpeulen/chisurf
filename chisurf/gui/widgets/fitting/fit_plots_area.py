"""EMTK-based FitPlotsArea widget for FitSubWindow.

Inherits DockArea to support dragging tabs and dropping them into different
regions of the window (left, right, top, bottom, center splitters) while
providing EMTK dark theme styling, tab overflow scroll navigation buttons, and
backward-compatible layout state serialization.
"""

from __future__ import annotations

from typing import Any, Callable

from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.dock_area.dock_area import DockArea


class FitTabBarControl:
    """EMTK Tab bar control for fit plots with overflow scroll navigation."""

    def __init__(self, on_change: Callable[[int], None] | None = None) -> None:
        self.tabs: list[str] = []
        self.current_index: int = 0
        self.hovered_index: int | None = None
        self.hovered_arrow: str | None = None  # "left", "right", or None
        self.on_change = on_change
        self.scroll_offset: float = 0.0
        self._tab_rects: list[tuple[float, float, float, float]] = []
        self._left_arrow_rect: tuple[float, float, float, float] | None = None
        self._right_arrow_rect: tuple[float, float, float, float] | None = None
        self._can_scroll_left: bool = False
        self._can_scroll_right: bool = False

    def set_tabs(self, tabs: list[str]) -> None:
        self.tabs = list(tabs)

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        painter.fill_rect(x, y, w, h, (30, 32, 38))
        # Divider line at bottom
        painter.fill_rect(x, y + h - 1.0, w, 1.0, (48, 52, 62))

        # Measure all tabs
        tab_widths = [painter.text_width(name) + 24.0 for name in self.tabs]
        total_tabs_w = sum(tab_widths) + max(0, len(self.tabs) - 1) * 2.0 + 8.0

        needs_scroll = total_tabs_w > w
        arrow_w = 20.0
        nav_w = (arrow_w * 2.0 + 4.0) if needs_scroll else 0.0
        visible_tabs_w = w - nav_w

        max_scroll = max(0.0, total_tabs_w - visible_tabs_w) if needs_scroll else 0.0
        self.scroll_offset = max(0.0, min(self.scroll_offset, max_scroll))
        self._can_scroll_left = needs_scroll and self.scroll_offset > 0.0
        self._can_scroll_right = needs_scroll and self.scroll_offset < max_scroll

        tx = x + 4.0 - (self.scroll_offset if needs_scroll else 0.0)
        ty = y + 2.0
        th = h - 3.0
        self._tab_rects = []

        line_h = painter.line_height()
        for i, (name, tw) in enumerate(zip(self.tabs, tab_widths)):
            is_active = i == self.current_index
            is_hovered = i == self.hovered_index

            tab_r = (tx, ty, tw, th)
            self._tab_rects.append(tab_r)

            # Draw tab if in visible region
            if tx + tw > x and tx < x + visible_tabs_w:
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

        if needs_scroll:
            # Background for navigation scroll arrows
            nav_x = x + visible_tabs_w
            painter.fill_rect(nav_x, y, nav_w, h, (30, 32, 38))
            painter.fill_rect(nav_x, y + h - 1.0, nav_w, 1.0, (48, 52, 62))

            lx = nav_x + 2.0
            rx = lx + arrow_w
            self._left_arrow_rect = (lx, ty, arrow_w - 2.0, th)
            self._right_arrow_rect = (rx, ty, arrow_w - 2.0, th)

            # Left arrow
            l_bg = (
                (36, 40, 48)
                if (self.hovered_arrow == "left" and self._can_scroll_left)
                else (30, 32, 38)
            )
            painter.fill_rect(lx, ty, arrow_w - 2.0, th, l_bg)
            l_col = (220, 225, 235) if self._can_scroll_left else (80, 85, 95)
            lw = painter.text_width("◀")
            painter.text(
                lx + (arrow_w - 2.0 - lw) / 2.0,
                ty + (th - line_h) / 2.0 + 1.0,
                lw,
                line_h,
                0,
                "◀",
                l_col,
                False,
            )

            # Right arrow
            r_bg = (
                (36, 40, 48)
                if (self.hovered_arrow == "right" and self._can_scroll_right)
                else (30, 32, 38)
            )
            painter.fill_rect(rx, ty, arrow_w - 2.0, th, r_bg)
            r_col = (220, 225, 235) if self._can_scroll_right else (80, 85, 95)
            rw = painter.text_width("▶")
            painter.text(
                rx + (arrow_w - 2.0 - rw) / 2.0,
                ty + (th - line_h) / 2.0 + 1.0,
                rw,
                line_h,
                0,
                "▶",
                r_col,
                False,
            )
        else:
            self._left_arrow_rect = None
            self._right_arrow_rect = None

    def press(self, px: float, py: float, *args: Any) -> None:
        if self._left_arrow_rect and self._can_scroll_left:
            lx, ly, lw, lh = self._left_arrow_rect
            if lx <= px <= lx + lw and ly <= py <= ly + lh:
                self.scroll_offset = max(0.0, self.scroll_offset - 60.0)
                return

        if self._right_arrow_rect and self._can_scroll_right:
            rx, ry, rw, rh = self._right_arrow_rect
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                self.scroll_offset += 60.0
                return

        for i, (rx, ry, rw, rh) in enumerate(self._tab_rects):
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                if i != self.current_index:
                    self.current_index = i
                    if callable(self.on_change):
                        self.on_change(i)
                break

    def hover(self, px: float, py: float, *args: Any) -> None:
        self.hovered_index = None
        self.hovered_arrow = None
        if self._left_arrow_rect:
            lx, ly, lw, lh = self._left_arrow_rect
            if lx <= px <= lx + lw and ly <= py <= ly + lh:
                self.hovered_arrow = "left"
                return
        if self._right_arrow_rect:
            rx, ry, rw, rh = self._right_arrow_rect
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                self.hovered_arrow = "right"
                return

        for i, (rx, ry, rw, rh) in enumerate(self._tab_rects):
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                self.hovered_index = i
                break


class FitPlotsArea(DockArea):
    """EMTK-styled DockArea for fit plots in FitSubWindow.

    Inherits DockArea to support dragging tabs and dropping them into different
    regions of the subwindow (left, right, top, bottom, center splitters), while
    providing EMTK dark styling, tab overflow navigation scroll buttons, and
    backward-compatible layout state serialization.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setStyleSheet("""
            FitPlotsArea {
                background-color: #1e2026;
            }
        """)

    def set_layout_state(
        self,
        state: dict,
        key_func: Callable[[QtWidgets.QWidget], str] | None = None,
        emit_change: bool = True,
    ) -> bool:
        if not isinstance(state, dict):
            return False
        # If legacy state from early emtk_fit_plots_area format without full dock tree
        if (
            state.get("type") == "emtk_fit_plots_area"
            and "tabs" in state
            and "root" in state
            and isinstance(state["root"], dict)
            and state["root"].get("type") == "tab"
            and "widget_key" in (state.get("tabs", [{}])[0] if state.get("tabs") else {})
        ):
            # Check if this can be restored via super()
            res = super().set_layout_state(state, key_func=key_func, emit_change=emit_change)
            if res:
                return True
            current_idx = state.get("current_index")
            if isinstance(current_idx, int) and 0 <= current_idx < self.count():
                if emit_change:
                    self.setCurrentIndex(current_idx)
                else:
                    super().setCurrentIndex(current_idx)
                return True
        return super().set_layout_state(state, key_func=key_func, emit_change=emit_change)

    def get_layout_state(self, key_func: Callable[[QtWidgets.QWidget], str] | None = None) -> dict:
        state = super().get_layout_state(key_func=key_func)
        state["type"] = "emtk_fit_plots_area"
        return state

    def update(self, *args: Any) -> None:
        super().update(*args)
        w = self.currentWidget()
        if w is not None and hasattr(w, "update"):
            try:
                w.update(*args)
            except TypeError:
                w.update()
