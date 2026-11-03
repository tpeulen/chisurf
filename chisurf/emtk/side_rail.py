"""A navigation rail beside a tool that resizes by its edge and folds to its icons when narrow.

The rail of the step hub (:mod:`chisurf.emtk.tool_hub`), of Settings, of Imaging Tools and of the
MMFDB admin share it: the right edge is a grip (a window of its own, drawn over the tool and
centred on the line, so it can be grabbed on either side and shows where to grab); dragged
narrower than :attr:`SideRail.fold` the rail folds to a strip of icons, as a dock folds to its
title, and dragged out again it unfolds; a double click on the edge restores the default width.
The width the user chose goes into the tool's settings (:meth:`SideRail.export`).

The tool keeps drawing its own rail; :meth:`SideRail.width_now` says how wide, :attr:`folded`
whether to draw only the icons (:meth:`SideRail.item` draws a row either way), and the tool
leaves the grip zone out of the box it hands its hosted tool (:meth:`SideRail.on_grip`).
"""

from __future__ import annotations

from typing import Callable

from emtk import im

from chisurf.core.support.i18n import tr

#: Below this width the rail folds to its icons.
FOLD = 150.0
#: The folded strip's width.
FOLDED = 44.0
#: Half the grip's width on each side of the edge.
GRIP = 6.0


class SideRail:
    """Width, fold and grip of one navigation rail.

    Parameters
    ----------
    key : str
        Names the grip's window and drag (unique within the app).
    default : callable
        ``default(total_width) -> width``: the rail's width until the user drags its edge.
    most : float
        The widest the rail may be dragged, as a fraction of the window.
    """

    def __init__(self, key: str, default: Callable[[float], float], *, most: float = 0.6) -> None:
        self.key = key
        self.default = default
        self.most = float(most)
        #: The width the user dragged (``None``: :attr:`default`); below :data:`FOLD` it is folded.
        self.width: float | None = None
        self._left = 0.0

    @property
    def folded(self) -> bool:
        """Narrower than :data:`FOLD`: only the icons of the rows show."""
        return self.width is not None and self.width < FOLD

    @property
    def left(self) -> float:
        """The width the rail was drawn at last (where its edge is)."""
        return self._left

    def width_now(self, total: float) -> float:
        """The rail's width in a window *total* wide."""
        if self.folded:
            self._left = FOLDED
        elif self.width is None:
            self._left = float(self.default(total))
        else:
            self._left = max(FOLD, min(float(self.width), total * self.most))
        return self._left

    def on_grip(self, x: float) -> bool:
        """*x* is on the grip of the rail drawn last: a press there is the rail's, not the tool's."""
        return abs(float(x) - self._left) <= GRIP

    def draw_grip(self, left: float, top: float, height: float, total: float) -> None:
        """The grip on the edge at *left*, from *top* down *height*; call after the tool is drawn."""
        flags = (
            im.WindowFlags.NO_DECORATION
            | im.WindowFlags.NO_BACKGROUND
            | im.WindowFlags.NO_MOVE
            | im.WindowFlags.NO_SAVED_SETTINGS
            | im.WindowFlags.NO_SCROLLBAR
            | im.WindowFlags.NO_SCROLL_WITH_MOUSE
            | im.WindowFlags.NO_NAV
        )
        box = (left - GRIP, top, 2.0 * GRIP, height)
        im.set_next_window_pos(box[:2], im.Cond.ALWAYS)
        im.set_next_window_size(box[2:], im.Cond.ALWAYS)
        if im.begin(f"##{self.key} grip", flags=flags):
            changed, new_left, _ = im.splitter_behavior(
                box, im.get_id(f"##{self.key}_grip"), im.Axis.X, left, total - left, FOLDED - 8.0, 300.0
            )
            if changed:
                self.width = float(new_left)
            hovered = im.is_mouse_hovering_rect(box[:2], (box[0] + box[2], box[1] + box[3]))
            held = changed or (hovered and im.is_mouse_down(0))
            colour = im.get_style().color(
                im.Col.SEPARATOR_ACTIVE
                if held
                else im.Col.SEPARATOR_HOVERED if hovered else im.Col.SEPARATOR
            )
            bar = 3.0 if hovered or held else 1.0
            im.get_window_draw_list().add_rect_filled(
                (left - bar / 2.0, top), (left + bar / 2.0, top + height), colour
            )
            if hovered:
                im.set_tooltip(
                    tr("Drag to resize the list; narrow, it folds to its icons. Double click: default width.")
                )
                if im.is_mouse_double_clicked(0):
                    self.width = None
        im.end()

    def item(self, label: str, selected: bool, key: str, icon: str | None = None, height: float = 28.0) -> bool:
        """One row of the rail: the icon and *label*, or folded the icon alone (*label* its tooltip).

        Returns whether it was clicked. The caller sets the tooltip of an unfolded row; a folded
        row names itself.
        """
        if not self.folded:
            return im.selectable(label + "##" + key, selected, size=(self._left - 8.0, height), icon=icon)
        clicked = im.selectable(
            "##" + key, selected, size=(self._left - 8.0, height), icon=icon or label.strip()[:2]
        )
        im.set_item_tooltip(label)
        return clicked

    def export(self) -> float | None:
        """The dragged width for the tool's settings (``None``: the default)."""
        return None if self.width is None else float(self.width)

    def restore(self, value) -> None:
        """Take a width :meth:`export` gave (anything else leaves the default)."""
        self.width = float(value) if isinstance(value, (int, float)) else None
