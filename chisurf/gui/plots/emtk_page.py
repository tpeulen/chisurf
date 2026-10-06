"""A fit-window page as what the fit window's emtk surface draws.

A page (:class:`~chisurf.gui.plots.plotbase.Plot`) is not a widget. It says
what to draw in one of three ways, checked in this order:

* ``emtk_draw(box)`` -- it draws itself in immediate mode inside the surface's
  emtk frame (selectors from :mod:`emtk.im` above a panel, say);
* ``emtk_panels`` (:meth:`~chisurf.gui.plots.plotbase.Plot.add_panel`) --
  chiplot panels stacked top to bottom, weighted by their stretch;
* ``emtk_body()`` -- one retained emtk control.

A page that does none of these has nothing the surface can draw; it is
*reported*, by class name, in :attr:`PageBody.missing` rather than drawn blank,
and ``test/gui/test_fit_window_pages_all_models.py`` fails on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["PageBody", "PanelItem", "page_body", "install_refresh"]


@dataclass
class PageBody:
    """What :func:`page_body` found.

    Attributes
    ----------
    control : object or None
        The page as one emtk control (``emtk_panels``/``emtk_body``).
    draw : callable or None
        ``draw(box)``: a page that draws itself in immediate mode.
    missing : list of str
        The page's class name when it declares nothing drawable.
    refreshables : list
        Objects that repaint through ``set_refresh_target`` (chiplot canvases,
        text editors, the page itself): the surface drawing the page installs
        its frame request on each, so a changed curve shows without waiting
        for input.
    panels : list of PanelItem
        The chiplot panels, for the right-click menu.
    """

    control: Any = None
    draw: Any = None
    missing: list[str] = field(default_factory=list)
    refreshables: list[Any] = field(default_factory=list)
    panels: list[PanelItem] = field(default_factory=list)

    def panel_at(self, px: float, py: float) -> PanelItem | None:
        """The chiplot panel drawn under a point last frame, if any."""
        for panel in self.panels:
            if panel.contains(px, py):
                return panel
        return None


class PanelItem:
    """A chiplot panel's canvas, remembering where it was drawn and whose it is.

    Delegates the whole control contract to the canvas; what it adds is the box
    of the last draw and the :class:`~chisurf.gui.chiplot.canvas.Plot` that owns
    the canvas, so a right click on the surface can offer that plot's menu
    (export, auto-range, the plot's own entries) as the panel's Qt wrapper did.
    """

    def __init__(self, plot: Any, canvas: Any) -> None:
        self.plot = plot
        self.canvas = canvas
        self.box: tuple[float, float, float, float] | None = None

    def contains(self, px: float, py: float) -> bool:
        """Whether a point is inside the last drawn box."""
        if self.box is None:
            return False
        x, y, w, h = self.box
        return x <= px < x + w and y <= py < y + h

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        self.box = (x, y, w, h)
        # A panel's own host filled the background before drawing it; on a
        # shared surface the panel does, or it shows the window's colour.
        background = getattr(self.canvas, "_background", None)
        if background is not None:
            p.fill_rect(x, y, w, h, tuple(background[:3]))
        self.canvas.draw(p, x, y, w, h)

    def __getattr__(self, name: str):
        # press/drag/release/hover/scroll/key: the canvas's own.
        return getattr(self.canvas, name)


def page_body(page: Any) -> PageBody:
    """Return what the surface draws for *page*.

    Parameters
    ----------
    page : Plot
        A fit-window page.

    Returns
    -------
    PageBody
    """
    body = PageBody()
    immediate = getattr(page, "emtk_draw", None)
    declared = getattr(page, "emtk_panels", None)
    custom = getattr(page, "emtk_body", None)
    if callable(immediate):
        body.draw = immediate
    elif declared and not callable(custom):
        body.control = _declared_stack(page, declared, body)
    elif callable(custom):
        body.control = custom()
    else:
        body.missing.append(type(page).__name__)
        return body
    _collect_refreshables(page, body)
    for item in getattr(page, "panel_items", None) or []:
        if item not in body.panels:
            body.panels.append(item)
    return body


def _declared_stack(page, declared: list, body: PageBody) -> Any:
    """The page's declared panels (``add_panel``), stacked by stretch, built once.

    Kept on the page, so a bar the user dragged stays where it was.
    """
    key = tuple(id(panel) for panel, _ in declared)
    cached = getattr(page, "_emtk_declared", None)
    if cached is not None and cached[0] == key:
        body.panels.extend(cached[2])
        return cached[1]
    items = [PanelItem(panel, panel.control()) for panel, _stretch in declared]
    body.panels.extend(items)
    if len(items) == 1:
        stack = items[0]
    else:
        from emtk.flags import Axis
        from emtk.widgets.pane_stack import PaneStack

        stack = PaneStack(items, [max(s, 0.01) for _, s in declared], axis=Axis.Y)
    page._emtk_declared = (key, stack, items)
    return stack


def _collect_refreshables(page: Any, body: PageBody) -> None:
    """Gather everything of *page* that repaints through ``set_refresh_target``."""
    candidates: list[Any] = [page]
    candidates += [getattr(item, "canvas", None) for item in getattr(page, "panel_items", None) or []]
    candidates += [panel.control() for panel, _ in getattr(page, "emtk_panels", None) or []]
    candidates += list(getattr(page, "refreshables", lambda: [])())
    for target in candidates:
        if (
            target is not None
            and callable(getattr(target, "set_refresh_target", None))
            and target not in body.refreshables
        ):
            body.refreshables.append(target)


def install_refresh(body: PageBody, request: Callable[[], None] | None) -> None:
    """Point every repaintable of *body* at *request* (``None`` to undo)."""
    for target in body.refreshables:
        setter = getattr(target, "set_refresh_target", None)
        if callable(setter):
            setter(request)
