"""A fit-window plot page as one emtk control.

A fit window draws all of its pages on one emtk surface. The pages themselves
are still built the way they always were: a :class:`~chisurf.gui.plots.plotbase.Plot`
stacks chiplot panels, emtk text views and emtk-hosted controls in a box layout
or a splitter. Those Qt containers are never shown any more; what each one
*holds* already draws through emtk, so this module reads the composition once
and returns the same arrangement as emtk controls:

* a chiplot panel on the emtk backend is its canvas, a control already;
* an :class:`~chisurf.gui.plots.emtk_text_view.EmtkTextView` is its ``TextEditor``;
* any emtk ``ControlHost`` is the control it hosts;
* a box layout or a splitter becomes an :class:`emtk.widgets.pane_stack.PaneStack`
  weighted by the layout's stretch factors or the splitter's sizes;
* a hidden widget is skipped, as Qt skips it.

A page that wants a different arrangement says so with ``emtk_body()`` (a
control), or draws itself with ``emtk_draw(box)`` inside the surface's emtk frame
(selectors from :mod:`emtk.im` above a panel, say). Anything
else -- a classic Qt widget the page shows -- cannot be drawn on the surface and
is *reported*, by class name, rather than silently dropped: :func:`page_body`
returns it in ``missing`` and the fit window shows the page as not yet ported.
``test/gui/test_fit_window_emtk.py`` holds the list of pages still in that state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from qtpy import QtCore, QtWidgets

__all__ = ["PageBody", "PanelItem", "page_body", "install_refresh"]


@dataclass
class PageBody:
    """What :func:`page_body` found.

    Attributes
    ----------
    control : object or None
        The page as one emtk control; ``None`` when nothing could be drawn.
    missing : list of str
        Class names of shown widgets with no emtk drawing.
    refreshables : list
        Objects that repaint through ``set_refresh_target`` (chiplot canvases,
        text views): the surface drawing the page installs its frame request
        on each, so a changed curve shows without waiting for input.
    """

    control: Any = None
    #: ``draw(box)`` -- a page that draws itself in immediate mode (``emtk_draw``).
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


def page_body(page: QtWidgets.QWidget) -> PageBody:
    """Return *page* as one emtk control, with what could not be translated.

    Parameters
    ----------
    page : QWidget
        A fit-window plot page.

    Returns
    -------
    PageBody
    """
    body = PageBody()
    immediate = getattr(page, "emtk_draw", None)
    if callable(immediate):
        body.draw = immediate
        _collect_refreshables(page, body)
        body.panels.extend(getattr(page, "panel_items", None) or [])
        return body
    custom = getattr(page, "emtk_body", None)
    if callable(custom):
        body.control = custom()
        _collect_refreshables(page, body)
        body.panels.extend(getattr(page, "panel_items", None) or [])
        return body
    layout = page.layout() if callable(getattr(page, "layout", None)) else getattr(page, "layout", None)
    if not isinstance(layout, QtWidgets.QLayout):
        layout = getattr(page, "layout", None)
    if isinstance(layout, QtWidgets.QLayout):
        body.control = _from_layout(layout, body)
    else:
        body.missing.append(type(page).__name__)
    return body


def _collect_refreshables(page: QtWidgets.QWidget, body: PageBody) -> None:
    """Gather every repaintable inside *page* (for a page that built its own body)."""
    if callable(getattr(page, "set_refresh_target", None)):
        body.refreshables.append(page)
    from chisurf.gui.chiplot.canvas import Plot as ChiPlot

    for plot in getattr(page, "_panels", None) or page.findChildren(ChiPlot):
        canvas = getattr(plot, "_canvas", None)
        if callable(getattr(canvas, "set_refresh_target", None)):
            body.refreshables.append(canvas)
    from chisurf.gui.plots.emtk_text_view import EmtkTextView

    body.refreshables.extend(page.findChildren(EmtkTextView))


def _stack(parts: list[tuple[Any, float]], vertical: bool) -> Any:
    """One control for *parts*: the part itself, or a weighted pane stack."""
    parts = [(control, weight) for control, weight in parts if control is not None]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0][0]
    from emtk.flags import Axis
    from emtk.widgets.pane_stack import PaneStack

    weights = [weight if weight > 0 else 1.0 for _, weight in parts]
    return PaneStack([c for c, _ in parts], weights, axis=Axis.Y if vertical else Axis.X)


def _from_grid(layout: QtWidgets.QGridLayout, body: PageBody) -> Any:
    """A grid as rows of side-by-side panes, weighted by the grid's stretch factors."""
    rows: dict[int, list[tuple[int, Any, float]]] = {}
    for index in range(layout.count()):
        item = layout.itemAt(index)
        row, column, _rowspan, colspan = layout.getItemPosition(index)
        widget = item.widget()
        if widget is not None:
            if widget.isHidden():
                continue
            control = _from_widget(widget, body)
        elif item.layout() is not None:
            control = _from_layout(item.layout(), body)
        else:
            continue
        stretch = sum(layout.columnStretch(c) for c in range(column, column + colspan))
        rows.setdefault(row, []).append((column, control, float(stretch or colspan)))
    parts = []
    for row in sorted(rows):
        cells = [(control, weight) for _, control, weight in sorted(rows[row], key=lambda c: c[0])]
        parts.append((_stack(cells, vertical=False), float(layout.rowStretch(row) or 1)))
    return _stack(parts, vertical=True)


def _from_layout(layout: QtWidgets.QLayout, body: PageBody) -> Any:
    if isinstance(layout, QtWidgets.QGridLayout):
        return _from_grid(layout, body)
    vertical = not (
        isinstance(layout, QtWidgets.QBoxLayout)
        and layout.direction() in (QtWidgets.QBoxLayout.LeftToRight, QtWidgets.QBoxLayout.RightToLeft)
    )
    parts: list[tuple[Any, float]] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        stretch = float(layout.stretch(index)) if isinstance(layout, QtWidgets.QBoxLayout) else 0.0
        widget = item.widget()
        if widget is not None:
            if widget.isHidden():
                continue
            parts.append((_from_widget(widget, body), stretch))
        elif item.layout() is not None:
            parts.append((_from_layout(item.layout(), body), stretch))
    return _stack(parts, vertical)


def _from_widget(widget: QtWidgets.QWidget, body: PageBody) -> Any:
    from chisurf.gui.chiplot.canvas import Plot as ChiPlot
    from chisurf.gui.plots.emtk_text_view import EmtkTextView

    if isinstance(widget, ChiPlot):
        canvas = getattr(widget, "_canvas", None)
        if canvas is not None and callable(getattr(canvas, "draw", None)):
            if callable(getattr(canvas, "set_refresh_target", None)):
                body.refreshables.append(canvas)
            item = PanelItem(widget, canvas)
            body.panels.append(item)
            return item
        body.missing.append(f"{type(widget).__name__}({type(canvas).__name__})")
        return None
    if isinstance(widget, EmtkTextView):
        editor = getattr(widget, "_editor", None)
        if editor is None:
            body.missing.append("EmtkTextView(Qt fallback)")
            return None
        body.refreshables.append(widget)
        return editor
    if getattr(widget, "is_emtk", False) and getattr(widget, "control", None) is not None:
        control = widget.control
        if callable(getattr(control, "set_refresh_target", None)):
            body.refreshables.append(control)
        if hasattr(control, "_entries") and hasattr(control, "_background"):
            # A chiplot canvas met without its Plot wrapper (a grid's panel).
            item = PanelItem(None, control)
            body.panels.append(item)
            return item
        return control
    from chisurf.gui.chiplot.canvas import Grid as ChiGrid

    if isinstance(widget, ChiGrid):
        return _from_layout(widget.layout(), body)
    if isinstance(widget, QtWidgets.QSplitter):
        vertical = widget.orientation() == QtCore.Qt.Vertical
        sizes = list(widget.sizes())
        parts = []
        for index in range(widget.count()):
            child = widget.widget(index)
            if child is None or child.isHidden():
                continue
            weight = float(sizes[index]) if index < len(sizes) else 1.0
            parts.append((_from_widget(child, body), weight))
        return _stack(parts, vertical)
    custom = getattr(widget, "emtk_body", None)
    if callable(custom):
        return custom()
    # A plain container: what it lays out is what counts.
    if type(widget) is QtWidgets.QWidget and isinstance(widget.layout(), QtWidgets.QLayout):
        return _from_layout(widget.layout(), body)
    body.missing.append(type(widget).__name__)
    return None


def install_refresh(body: PageBody, request: Callable[[], None] | None) -> None:
    """Point every repaintable of *body* at *request* (``None`` to undo)."""
    for target in body.refreshables:
        setter = getattr(target, "set_refresh_target", None)
        if callable(setter):
            setter(request)
