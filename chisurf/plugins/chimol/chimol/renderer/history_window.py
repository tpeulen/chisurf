"""The action list: what has happened to the scene, newest last.

Every change to the object list passes through one place
(:mod:`~chimol.renderer.object_registry`), so there is something to show. This
is that something: one row per action, the undone ones struck through, and the
point at which ``undo`` would take you marked.

Why it is worth a panel rather than a log line
----------------------------------------------
An undo stack you cannot see is a stack you have to keep in your head. The
question a user actually has -- *what will Ctrl+Z do next, and how far back can
I go* -- has no answer without a list, and the answer changes with every
command.

It is read-only on purpose. Clicking a row to jump there means replaying or
inverting an arbitrary run of changes, and half of them are not invertible (a
visibility touch does not record the value it replaced). Offering a jump that
silently does something else at some rows would be worse than not offering one.
"""
from __future__ import annotations

from .internal_gui import GuiWindow
from ..cmtk.painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER

__all__ = ["HistoryWindow"]

_PAD = 6.0
_ROW = 15.0

#: Rows, in the order the eye reads them: what happened, then how far back it
#: is. Colours match the chrome's own -- gold for the live edge, dim for what
#: has been undone.
_TEXT = (235, 235, 240)
_DIM = (140, 140, 150)
_EDGE = (255, 208, 96)
_UNDONE = (110, 110, 120)
_BG_ALT = (34, 34, 38, 220)


class HistoryWindow:
    """A list of the scene's changes, as a viewport window.

    Parameters
    ----------
    viewer : chimol.renderer.view.MolView
        Read for :meth:`~chimol.renderer.view.MolView.object_history`. Nothing
        is cached: the list is short, and a cached copy is one more thing that
        can be stale in a panel that exists to show what is current.
    """

    KEY = "history"

    def __init__(self, viewer) -> None:
        self.viewer = viewer
        self._scroll = 0

    def window(self, **kwargs) -> GuiWindow:
        """A :class:`GuiWindow` wired to this panel."""
        options = dict(key=self.KEY, title="History", x=40.0, y=120.0,
                       w=280.0, h=200.0, transient=True)
        options.update(kwargs)
        return GuiWindow(body=self.draw, **options)

    def draw(self, p, rect) -> None:
        """Paint the action list, newest last."""
        try:
            history = list(self.viewer.object_history())
        except Exception:  # noqa: BLE001 - a panel is not worth a frame
            history = []

        if not history:
            p.text(rect.x + _PAD, rect.y + _PAD, rect.w - 2 * _PAD, _ROW,
                   ALIGN_VCENTER | ALIGN_LEFT,
                   "Nothing has changed yet.", _DIM)
            return

        # The tail, because the newest is what anybody is looking for and the
        # ring holds far more than a panel can show.
        visible = max(int((rect.h - 2 * _PAD) / _ROW), 1)
        shown = history[-visible:]
        try:
            undone = {id(c) for c in self.viewer._objects._redo}
        except Exception:  # noqa: BLE001
            undone = set()

        y = rect.y + _PAD
        for index, change in enumerate(shown):
            if index % 2:
                p.fill_rect(rect.x, y, rect.w, _ROW, _BG_ALT)
            is_last = change is shown[-1]
            colour = _UNDONE if id(change) in undone else (
                _EDGE if is_last else _TEXT
            )
            label = str(change.label or change.kind)
            p.text(rect.x + _PAD, y, rect.w - 2 * _PAD - 40.0, _ROW,
                   ALIGN_VCENTER | ALIGN_LEFT, label, colour)
            p.text(rect.x + _PAD, y, rect.w - 2 * _PAD, _ROW,
                   ALIGN_VCENTER | ALIGN_RIGHT, str(change.revision), _DIM)
            y += _ROW

        # What Ctrl+Z would do, spelled out: the panel exists to answer that.
        try:
            registry = self.viewer._objects
            nxt = registry._undo[-1].label if registry.can_undo() else ""
        except Exception:  # noqa: BLE001
            nxt = ""
        if nxt:
            p.text(rect.x + _PAD, rect.y + rect.h - _ROW - 2.0,
                   rect.w - 2 * _PAD, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                   f"ctrl+z: {nxt}", _EDGE)
