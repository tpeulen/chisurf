"""The fit window's content as one emtk surface: pages, tabs, dock regions, the Code face.

Everything inside a fit window -- the plot pages, their tabs and dock regions,
the data table, the report, the Code face -- is drawn by emtk on a single
surface. The emtk shell hosts it as a dock window (:mod:`chisurf.emtk.fit_window`);
the Qt shell hosts it inside an MDI sub-window through
:class:`chisurf.gui.widgets.fitting.fit_plots_area.FitPlotsArea`.

The surface is :class:`FitWindowSurface`, an :class:`emtk.app.ImApp`. Its pages
are windows of an :class:`emtk.docking.DockManager`: tabs in one region by
default, and a tab dragged onto a region's edge splits the window. Each page is
a plot object; what it shows is read once by
:func:`chisurf.emtk.fit_pages.pages.emtk_page.page_body` and drawn here with
:func:`emtk.im.host_control`. A right click on a chiplot panel offers that
panel's menu (export data or image, auto-range, the plot's own entries).

Qt-free: importing this module imports neither Qt nor emtk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

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
            self.docks = DockManager(
                Region("center", keep=True),
                on_change=self._docks_changed,
                snapping=True,
                name="fitwin",
            )
            self.code_face = None
            self.show_code = False
            self._menu_panel = None
            #: ``(kind, plot, FileDialog, DialogWindow)`` while an export asks where to write.
            self._export: tuple | None = None
            self._suppress_layout_signal = False
            super().__init__(gui=self._render, continuous=False)

        # -- pages ------------------------------------------------------ #
        def add_page(self, key: str, title: str, provider: Callable[[], Any]) -> int:
            index = len(self.pages)
            page = _Page(key=str(key), title=str(title), provider=provider)
            self.pages.append(page)
            self.docks.add_window(
                page.key,
                page.title,
                lambda box, i=index: self._draw_page(i, box),
                dock="center",
                closable=False,
                scrollable=False,
            )
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
            newly = [
                key
                for region, key in selected.items()
                if key is not None and self._selected.get(region) != key
            ]
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
            from chisurf.emtk.fit_pages.pages.emtk_page import install_refresh, page_body

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
                im.text_colored(
                    (220, 90, 90),
                    f"{page.title}: {', '.join(body.missing)} declares nothing to draw.",
                )
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
                    self.ask_export("csv", plot)
                if im.menu_item("Export image…"):
                    self.ask_export("image", plot)
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

        def ask_export(self, kind: str, plot) -> None:
            """Ask where to write *plot* as ``"csv"`` data or an ``"image"`` (emtk's save dialog)."""
            from emtk.dialog_window import DialogWindow
            from emtk.file_dialog import FileDialog

            if kind == "csv":
                title, name, filters = "Export data as CSV", "plot.csv", "CSV files (*.csv)"
            else:
                title, name, filters = "Export image", "plot.png", "Images (*.png *.jpg *.tif)"
            self._export = (
                kind,
                plot,
                FileDialog(title, mode="save", filename=name, filters=filters),
                DialogWindow(title, size=(760, 540)),
            )
            self.request_frame()

        def _draw_export(self, box) -> None:
            kind, plot, dialog, window = self._export
            closed = window.begin(box)
            paths = dialog.draw()
            window.end()
            if closed or paths is False:
                self._export = None
            elif paths:
                self._export = None
                try:
                    if kind == "csv":
                        plot.export_csv(paths[0])
                    else:
                        plot.export_image(paths[0])
                except OSError as exc:
                    import logging

                    logging.getLogger(__name__).warning("export to %s failed: %s", paths[0], exc)

        def _render(self) -> None:
            vp = im.get_main_viewport()
            box = (0.0, 0.0, float(vp.size[0]), float(vp.size[1]))
            if self.show_code and self.code_face is not None:
                self.code_face.draw(box)
            else:
                self.docks.draw(box)
            if self._export is not None:
                self._draw_export(box)

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
