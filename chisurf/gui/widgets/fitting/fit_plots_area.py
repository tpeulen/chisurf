"""The fit window's content: one emtk surface.

Everything inside a fit window -- the plot pages, their tabs and dock regions,
the data table, the report, the Code face -- is drawn by emtk on a single
surface. Qt only *hosts* it: the MDI sub-window and its title bar are Qt, and
inside them is one :func:`emtk.qt_host.ControlHost`.

The surface is :class:`chisurf.emtk.fit_pages.surface.FitWindowSurface`, an
:class:`emtk.app.ImApp` (Qt-free, so the emtk shell draws the same surface
without Qt).

:class:`FitPlotsArea` is the Qt-facing shim: the call surface the rest of
ChiSurf has always used for ``FitSubWindow.plot_tab_widget`` (``addTab``,
``count``, ``currentIndex``, ``setCurrentIndex``, ``widget``, ``tabText``, the
``currentChanged``/``layoutChanged`` signals, ``get_layout_state`` /
``set_layout_state``), now answered from the surface.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from qtpy import QtCore, QtWidgets

from chisurf.emtk.fit_pages.surface import BACKGROUND, LAYOUT_TYPE, make_surface

logger = logging.getLogger(__name__)

__all__ = ["BACKGROUND", "LAYOUT_TYPE", "FitPlotsArea", "make_surface"]


class FitPlotsArea(QtWidgets.QWidget):
    """A fit window's content: one emtk surface behind the ``plot_tab_widget`` calls.

    Signals
    -------
    currentChanged(int)
        The page whose tab was chosen (in any region).
    layoutChanged()
        Tabs moved, regions split or resized, a page chosen.
    """

    currentChanged = QtCore.Signal(int)
    layoutChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        from emtk.qt_host import ControlHost

        self.surface = make_surface(
            on_current_changed=self.currentChanged.emit,
            on_layout_changed=self.layoutChanged.emit,
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.host = ControlHost(self.surface, background=BACKGROUND, parent=self)
        layout.addWidget(self.host, 1)

    # -- pages ------------------------------------------------------------ #
    def add_page(self, title: str, provider: Callable[[], Any], key: str | None = None) -> int:
        """Add a page drawn from ``provider()`` (called when the page is first drawn)."""
        key = key if key is not None else f"{len(self.surface.pages)}:{title}"
        index = self.surface.add_page(key, title, provider)
        self.host.update()
        return index

    def addTab(self, page: Any, title: str) -> int:  # noqa: N802 - Qt's spelling
        """Add a built *page* (the Qt tab-widget spelling)."""
        return self.add_page(title, lambda p=page: p)

    def count(self) -> int:
        return len(self.surface.pages)

    def widget(self, index: int):
        """The page's plot object, if it has been built."""
        if not 0 <= index < self.count():
            return None
        page = self.surface.pages[index]
        if page.widget is None:
            try:
                page.widget = page.provider()
            except Exception:
                logger.exception("building fit-window page %s failed", page.title)
                return None
        return page.widget

    def currentWidget(self):  # noqa: N802
        return self.widget(self.currentIndex())

    def tabText(self, index: int) -> str:  # noqa: N802
        return self.surface.pages[index].title if 0 <= index < self.count() else ""

    def setTabText(self, index: int, title: str) -> None:  # noqa: N802
        if 0 <= index < self.count():
            self.surface.set_title(index, title)
            self.host.update()

    def visible_indices(self) -> list[int]:
        """The pages in view: the current one and the front tab of every region."""
        surface = self.surface
        shown = {surface.index_of_key(key) for key in surface.docks.selected.values() if key}
        shown.update(
            surface.index_of_key(key)
            for key in surface.docks.floating()
            if surface.docks.is_visible(key)
        )
        if surface.current >= 0:
            shown.add(surface.current)
        return sorted(i for i in shown if i >= 0)

    def currentIndex(self) -> int:  # noqa: N802
        return self.surface.current

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self.surface.set_current(int(index))
        self.host.update()

    def setNewTabButtonVisible(self, visible: bool) -> None:  # noqa: N802
        """Kept for callers of the Qt dock area; the surface has no new-tab button."""

    # -- the Code face ---------------------------------------------------- #
    def set_code_face(self, face) -> None:
        self.surface.code_face = face
        face.request_frame = self.surface.request_frame

    def show_code(self, shown: bool) -> None:
        """Show the Code face (``True``) or the plots."""
        self.surface.show_code = bool(shown)
        self.surface.request_frame()
        self.host.update()

    def code_shown(self) -> bool:
        return bool(self.surface.show_code)

    # -- layout state ----------------------------------------------------- #
    def get_layout_state(self, key_func: Callable | None = None) -> dict:
        """The dock layout (regions, tab order, splits) and the current page."""
        return {
            "type": LAYOUT_TYPE,
            "keys": [page.key for page in self.surface.pages],
            "docks": self.surface.docks.state(),
            "current_index": int(self.currentIndex()),
        }

    def set_layout_state(
        self, state: dict, key_func: Callable | None = None, emit_change: bool = True
    ) -> bool:
        """Restore a layout from :meth:`get_layout_state`.

        Returns False, changing nothing, for any other layout -- a Qt dock
        area's, or one saved for a different set of pages. A layout saved before
        pages were *appended* (its keys are a prefix of these) is restored, and
        the new pages dock home.
        """
        if not isinstance(state, dict) or state.get("type") != LAYOUT_TYPE:
            return False
        keys = [page.key for page in self.surface.pages]
        saved = list(state.get("keys") or [])
        if not saved or saved != keys[: len(saved)] or not isinstance(state.get("docks"), dict):
            return False
        surface = self.surface
        surface._suppress_layout_signal = True
        try:
            surface.docks.restore(state["docks"])
            # A page a newer build added is not in an older layout: dock it home.
            for page in surface.pages:
                if (
                    surface.docks.region_of(page.key) is None
                    and page.key not in surface.docks.floating()
                ):
                    surface.docks.dock(page.key, "center")
        finally:
            surface._suppress_layout_signal = False
        surface._selected = dict(surface.docks.selected)
        current = state.get("current_index")
        if isinstance(current, int):
            surface.set_current(current, notify=emit_change)
        self.host.update()
        return True

    def update(self, *args: Any) -> None:  # noqa: D401 - Qt's spelling
        """Repaint the surface."""
        self.surface.request_frame()
        self.host.update()
