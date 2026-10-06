"""The fit window's content: one emtk surface.

Everything inside a fit window -- the plot pages, their tabs and dock regions,
the data table, the report, the Code face -- is drawn by emtk on a single
surface. Qt only *hosts* it: the MDI sub-window and its title bar are Qt, and
inside them is one :func:`emtk.qt_host.ControlHost`.

The surface is :class:`FitWindowSurface`, an :class:`emtk.app.ImApp`. Its pages
are windows of an :class:`emtk.docking.DockManager`: tabs in one region by
default, and a tab dragged onto a region's edge splits the window, as the Qt
dock area it replaces did. Each page is a plot object built as before; what it
shows is read once by :func:`chisurf.gui.plots.emtk_page.page_body` and drawn
here with :func:`emtk.im.host_control`. A right click on a chiplot panel offers
that panel's menu (export data or image, auto-range, the plot's own entries).

:class:`FitPlotsArea` is the Qt-facing shim: the call surface the rest of
ChiSurf has always used for ``FitSubWindow.plot_tab_widget`` (``addTab``,
``count``, ``currentIndex``, ``setCurrentIndex``, ``widget``, ``tabText``, the
``currentChanged``/``layoutChanged`` signals, ``get_layout_state`` /
``set_layout_state``), now answered from the surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from qtpy import QtCore, QtWidgets

logger = logging.getLogger(__name__)

#: The surface's background, the dark chrome every emtk tool shares.
BACKGROUND = (30, 32, 38)
#: ``get_layout_state()["type"]``: the dock layout of this surface.
LAYOUT_TYPE = "emtk_fit_window"


@dataclass
class _Page:
    """One page of the surface: its key, tab title and where its plot comes from."""

    key: str
    title: str
    provider: Callable[[], Any]
    widget: Any = None
    body: Any = None
    signature: tuple = ()
    bound_request: Any = None
    extras: dict = field(default_factory=dict)


def _signature(body) -> tuple:
    """What a page body draws, by identity: a changed signature is a rebuilt page."""
    leaves = tuple(id(getattr(p, "canvas", p)) for p in body.panels)
    drawer = getattr(body.draw, "__func__", body.draw)
    return (type(body.control).__name__, id(drawer), leaves, tuple(body.missing))


class FitWindowSurface:
    """The emtk app drawing a fit window's pages and Code face.

    Built lazily as an :class:`emtk.app.ImApp` subclass (see :func:`_surface_class`)
    so importing this module does not import emtk.
    """


def _surface_class():
    from emtk import im
    from emtk.app import ImApp
    from emtk.docking import DockManager, Region

    class _FitWindowSurface(ImApp, FitWindowSurface):
        def __init__(self, on_current_changed=None, on_layout_changed=None) -> None:
            self.pages: list[_Page] = []
            self.current = -1
            self._selected: dict[str, Any] = {}
            self.on_current_changed = on_current_changed
            self.on_layout_changed = on_layout_changed
            self.docks = DockManager(Region("center", keep=True), on_change=self._docks_changed,
                                     snapping=True, name="fitwin")
            self.code_face = None
            self.show_code = False
            #: Page index -> the box its Qt widget covers this frame (unported pages).
            self.islands: dict[int, tuple] = {}
            #: Called after every frame with :attr:`islands` (the Qt side places them).
            self.after_frame = None
            self._menu_panel = None
            self._suppress_layout_signal = False
            super().__init__(gui=self._render, continuous=False)

        # -- pages ------------------------------------------------------ #
        def add_page(self, key: str, title: str, provider: Callable[[], Any]) -> int:
            index = len(self.pages)
            page = _Page(key=str(key), title=str(title), provider=provider)
            self.pages.append(page)
            self.docks.add_window(page.key, page.title, lambda box, i=index: self._draw_page(i, box),
                                  dock="center", closable=False, scrollable=False)
            if self.current < 0:
                self.current = 0
                self.docks.focus(page.key)
            self._selected = dict(self.docks.selected)
            return index

        def set_title(self, index: int, title: str) -> None:
            page = self.pages[index]
            page.title = str(title)
            window = self.docks.window(page.key)
            if window is not None:
                window.title = page.title

        def set_current(self, index: int, *, notify: bool = True) -> None:
            if not 0 <= index < len(self.pages):
                return
            changed = index != self.current
            self.current = index
            self.docks.focus(self.pages[index].key)
            self._selected = dict(self.docks.selected)
            self.request_frame()
            if changed and notify and self.on_current_changed is not None:
                self.on_current_changed(index)

        def index_of_key(self, key: str) -> int:
            for index, page in enumerate(self.pages):
                if page.key == key:
                    return index
            return -1

        def _docks_changed(self, manager) -> None:
            selected = dict(manager.selected)
            newly = [key for region, key in selected.items()
                     if key is not None and self._selected.get(region) != key]
            self._selected = selected
            if newly:
                index = self.index_of_key(newly[-1])
                if index >= 0 and index != self.current:
                    self.current = index
                    if self.on_current_changed is not None:
                        self.on_current_changed(index)
            if not self._suppress_layout_signal and self.on_layout_changed is not None:
                self.on_layout_changed()

        # -- drawing ------------------------------------------------------ #
        def page_body(self, index: int):
            """The page's emtk body, rebuilt only when what it draws changed."""
            from chisurf.gui.plots.emtk_page import install_refresh, page_body

            page = self.pages[index]
            widget = page.provider()
            if widget is None:
                return None
            body = page_body(widget)
            signature = _signature(body)
            if widget is page.widget and page.body is not None and signature == page.signature:
                body = page.body
            else:
                page.widget, page.body, page.signature = widget, body, signature
                page.bound_request = None
            if page.bound_request != self.request_frame:
                install_refresh(body, self.request_frame)
                page.bound_request = self.request_frame
            return body

        def _draw_page(self, index: int, box) -> None:
            body = self.page_body(index)
            page = self.pages[index]
            if body is not None and body.draw is not None:
                io = im.get_io()
                right_click = bool(io.mouse_clicked[1])
                body.draw(box)
                if right_click:
                    self._menu_panel = body.panel_at(*io.mouse_pos)
                self._draw_panel_menu(page)
                return
            if body is not None and body.missing:
                # Not yet drawable on the surface: its Qt widget is laid over
                # this box until the page is ported (the guard test lists them).
                self.islands[index] = tuple(float(v) for v in box)
                return
            if body is None or body.control is None:
                im.text_disabled(f"{page.title}: nothing to show yet.")
                return
            io = im.get_io()
            right_click = bool(io.mouse_clicked[1])
            im.host_control(f"##page-{page.key}", body.control)
            if right_click and im.is_item_hovered():
                self._menu_panel = body.panel_at(*io.mouse_pos)
            self._draw_panel_menu(page)

        def _draw_panel_menu(self, page) -> None:
            """The right-click menu of the chiplot panel that was clicked."""
            if not im.begin_popup_context_item(f"##plot-menu-{page.key}"):
                return
            panel = self._menu_panel
            plot = getattr(panel, "plot", None)
            if plot is not None:
                if im.menu_item("Export data as CSV…"):
                    plot._on_export_csv()
                if im.menu_item("Export image…"):
                    plot._on_export_image()
                im.separator()
                if im.menu_item("Auto-range"):
                    plot.autoscale()
                extra = list(getattr(plot, "_extra_menu_actions", ()) or ())
                if extra:
                    im.separator()
                    for label, callback in extra:
                        if im.menu_item(label):
                            callback()
            im.end_popup()

        def _render(self) -> None:
            vp = im.get_main_viewport()
            box = (0.0, 0.0, float(vp.size[0]), float(vp.size[1]))
            self.islands = {}
            if self.show_code and self.code_face is not None:
                self.code_face.draw(box)
            else:
                self.docks.draw(box)
            if self.after_frame is not None:
                self.after_frame(dict(self.islands))

        # -- host hooks ---------------------------------------------------- #
        def key(self, key, text="", modifiers=0):
            if self.show_code and self.code_face is not None:
                if self.code_face.key(key, text, modifiers):
                    self.wants_frame = True
                    return True
            return super().key(key, text, modifiers)

        def animating(self) -> bool:
            face = self.code_face
            busy = bool(self.show_code and face is not None and face.busy())
            return super().animating() or busy

    return _FitWindowSurface


def make_surface(**kwargs):
    """Build a :class:`FitWindowSurface` (an emtk ``ImApp``)."""
    return _surface_class()(**kwargs)


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
        # Page widgets are built as before but never shown: the surface draws
        # what they hold. A hidden holder keeps them alive and out of sight.
        self._holder = QtWidgets.QWidget(self)
        self._holder.hide()
        #: Page index -> its Qt widget while it is laid over the surface.
        self._islands: dict[int, QtWidgets.QWidget] = {}
        self._pending_islands: dict | None = None
        self.surface.after_frame = self._islands_drawn

    # -- pages ------------------------------------------------------------ #
    def add_page(self, title: str, provider: Callable[[], Any], key: str | None = None) -> int:
        """Add a page drawn from ``provider()`` (called when the page is first drawn)."""
        key = key if key is not None else f"{len(self.surface.pages)}:{title}"
        index = self.surface.add_page(key, title, provider)
        self.host.update()
        return index

    def addTab(self, widget: QtWidgets.QWidget, title: str) -> int:  # noqa: N802 - Qt's spelling
        """Add *widget* as a page (the Qt tab-widget spelling)."""
        widget.setParent(self._holder)
        return self.add_page(title, lambda w=widget: w)

    def adopt(self, widget: QtWidgets.QWidget) -> None:
        """Keep a page's plot widget alive, hidden, for the surface to draw."""
        # QWidget.parentWidget, not widget.parent(): plot pages assign a
        # ``parent`` attribute that shadows the Qt method.
        if widget is not None and QtWidgets.QWidget.parentWidget(widget) is not self._holder:
            widget.setParent(self._holder)

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
        shown.update(surface.index_of_key(key) for key in surface.docks.floating()
                     if surface.docks.is_visible(key))
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

    # -- pages not yet drawn by emtk ------------------------------------- #
    def _islands_drawn(self, islands: dict) -> None:
        """Note where unported pages go; placed after the paint, not inside it."""
        current = {i: tuple(round(v) for v in box) for i, box in islands.items()}
        placed = {i: tuple(w.geometry().getRect()) for i, w in self._islands.items()}
        if current == placed:
            return
        first = self._pending_islands is None
        self._pending_islands = current
        if first:
            QtCore.QTimer.singleShot(0, self._place_islands)

    def _place_islands(self) -> None:
        """Lay each unported page's Qt widget over its dock box; hide the rest."""
        wanted, self._pending_islands = self._pending_islands or {}, None
        for index in list(self._islands):
            if index not in wanted:
                widget = self._islands.pop(index)
                widget.hide()
                widget.setParent(self._holder)
        for index, (x, y, w, h) in wanted.items():
            widget = self.surface.pages[index].widget
            if widget is None:
                continue
            if self._islands.get(index) is not widget:
                widget.setParent(self)
                self._islands[index] = widget
            widget.setGeometry(int(x), int(y), max(int(w), 1), max(int(h), 1))
            widget.show()
            widget.raise_()

    def island_indices(self) -> list[int]:
        """Pages shown as Qt widgets over the surface (not yet drawn by emtk)."""
        return sorted(self._islands)

    # -- the Code face ---------------------------------------------------- #
    def set_code_face(self, face) -> None:
        self.surface.code_face = face
        face.request_frame = self.surface.request_frame

    def show_code(self, shown: bool) -> None:
        """Show the Code face (``True``) or the plots."""
        self.surface.show_code = bool(shown)
        if shown:
            self._pending_islands = {}
            self._place_islands()
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

    def set_layout_state(self, state: dict, key_func: Callable | None = None,
                         emit_change: bool = True) -> bool:
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
                if surface.docks.region_of(page.key) is None and page.key not in surface.docks.floating():
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
