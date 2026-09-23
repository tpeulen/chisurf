"""The Global View window, drawn by emtk: a toolbar, four docks, a status line.

One immediate-mode frame draws everything:

* the **toolbar** -- the ``Toolbar`` panel of ``globalview.view.json``, one
  line that wraps when the window is narrow;
* an :class:`emtk.docking.DockManager` with two regions: the **Network** and
  the **Parameters** table as tabs of the wide one, **Selection** and **View**
  as tabs of the narrow one. Each can be dragged out, floated, re-docked and
  closed, and the arrangement is remembered;
* the **status line**, the model's one sentence about what is on screen.

Every control is declared in the view spec and drawn by :mod:`emtk.view_form`;
the only thing drawn by hand is the graph, which the node editor draws, and
its colour key. Qt appears nowhere here -- :mod:`.tool` hosts this in a window.
"""

from __future__ import annotations

import pathlib
import typing

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form, find_section
from emtk.widgets.view_spec import load_view_spec

from chisurf.plugins.core.globalview.gui.emtk_view import draw_legend

__all__ = ["DOCKS", "GlobalViewSurface", "SPEC_PATH"]

SPEC_PATH = pathlib.Path(__file__).with_name("globalview.view.json")

#: The docks, by title, and the region each starts in.
DOCKS: tuple = (
    ("Network", "main"),
    ("Parameters", "main"),
    ("Selection", "side"),
    ("View", "side"),
)

#: The wide region's share of the width at first start.
MAIN_FRACTION = 0.70
PAD = 4.0


class GlobalViewSurface(ImApp):
    """The whole window as one emtk control.

    Parameters
    ----------
    model : GlobalViewModel
        What is drawn and what the controls change.
    store : emtk.docking.LayoutStore, optional
        Where the dock arrangement is remembered; not remembered without one.
    on_used : callable, optional
        ``on_used(name)`` after a form field is committed or a button pressed:
        what a guided tour waits on.

    Attributes
    ----------
    forms : dict
        The :class:`~emtk.view_form.FormState` of each panel, by title. Their
        ``rects`` say where every field and button was drawn last frame.
    network_box : tuple or None
        Where the graph was drawn last frame.
    """

    def __init__(self, model, store=None, on_used: typing.Optional[typing.Callable] = None):
        super().__init__(self._gui)
        self.model = model
        self.spec = load_view_spec(SPEC_PATH)
        self.panels = {
            title: find_section(self.spec, title)
            for title in ("Toolbar", "View", "Selection", "Parameters")
        }
        self.forms = {title: FormState(on_used=on_used) for title in self.panels}
        self.docks = DockManager(
            Split("h", MAIN_FRACTION, Region("main"), Region("side"), min_size=260.0),
            store=store,
            name="globalview",
        )
        draws = {
            "Network": self._draw_network,
            "Parameters": lambda box: self._draw_panel("Parameters", box),
            "Selection": lambda box: self._draw_panel("Selection", box),
            "View": lambda box: self._draw_panel("View", box),
        }
        for title, region in DOCKS:
            self.docks.add_window(
                title, title, draws[title], dock=region, padding=PAD, min_size=(220.0, 140.0)
            )
        if store is not None:
            self.docks.load()
        self.box: tuple = (0.0, 0.0, 0.0, 0.0)
        self.network_box: typing.Optional[tuple] = None
        self._toolbar_h = 0.0

    # -- the frame --------------------------------------------------------

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """Draw one frame into *painter*."""
        self.box = (x, y, w, h)
        super().draw(painter, x, y, w, h)

    def _gui(self) -> None:
        x, y, w, h = self.box
        line = im.get_frame_height()
        toolbar_h = max(self._toolbar_h, line + 2.0 * PAD)
        status_h = line + 2.0

        im.begin("##globalview.toolbar", (x, y, w, toolbar_h))
        im.set_cursor_pos((x + PAD, y + PAD))
        draw_form(self.panels["Toolbar"], self.model, self.forms["Toolbar"], titles=False)
        im.end()
        # The toolbar wraps in a narrow window; the next frame gives it the
        # height its buttons took this one.
        rects = list(self.forms["Toolbar"].rects.values())
        if rects:
            bottom = max(r[1] + r[3] for r in rects)
            self._toolbar_h = max(bottom - y + PAD, line + 2.0 * PAD)

        self.docks.draw((x, y + toolbar_h, w, max(h - toolbar_h - status_h, 1.0)))

        im.begin("##globalview.status", (x, y + h - status_h, w, status_h))
        im.set_cursor_pos((x + PAD, y + h - status_h + 1.0))
        im.text(str(self.model.status))
        im.end()

    def _draw_network(self, box: tuple) -> None:
        self.network_box = tuple(box)
        control = self.model.control
        control._box = tuple(box)
        control._draw_graph(tuple(box))
        draw_legend(control.document, box)

    def _draw_panel(self, title: str, box: tuple) -> None:
        draw_form(self.panels[title], self.model, self.forms[title], titles=False)

    # -- where things are, for a tour and a test ---------------------------

    def rect_of(self, name: str) -> typing.Optional[tuple]:
        """Where the field, button or dock called *name* was drawn last frame.

        Parameters
        ----------
        name : str
            A field's ``attr``, a button's ``action``, a table's ``source``, or
            a dock's title.

        Returns
        -------
        tuple or None
            ``(x, y, w, h)`` in the surface's coordinates.
        """
        for form in self.forms.values():
            if name in form.rects:
                return tuple(form.rects[name])
        window = self.docks.window(name)
        if window is not None:
            frame = getattr(window, "frame", None) or getattr(window, "content", None)
            if frame is not None:
                return tuple(frame)
        return None

    def reveal(self, name: str) -> None:
        """Bring the dock holding *name* to the front (a tab behind another)."""
        if self.docks.window(name) is not None:
            self.docks.focus(name)
            return
        for title, form in self.forms.items():
            if name in form.rects and self.docks.window(title) is not None:
                self.docks.focus(title)
                return
        owner = self._panel_declaring(name)
        if owner is not None and self.docks.window(owner) is not None:
            self.docks.focus(owner)

    def _panel_declaring(self, name: str) -> typing.Optional[str]:
        def declares(section) -> bool:
            if not isinstance(section, dict):
                return False
            options = section.get("options")
            source = options.get("source") if isinstance(options, dict) else None
            if name in (section.get("attr"), section.get("action"), source):
                return True
            if any(b.get("action") == name for b in section.get("buttons") or []):
                return True
            return any(declares(s) for s in section.get("sections") or [])

        for title, panel in self.panels.items():
            if declares(panel):
                return title
        return None
