"""The QPainter chrome's before-half, captured before the GPU port replaces it.

Why this exists
---------------
The panel down the right, the sequence strip across the top, the wizard, the
prompt, the movie transport and the menus are all drawn by
``InternalGui.paint`` with a ``QPainter``, rasterised into a full-viewport
premultiplied RGBA image by ``qt_overlay.paint_chrome``, and uploaded as a
texture every time the cache expires. Replacing that with GPU quads makes "the
new panel looks fine" the wrong question -- the question is *whether anything
was lost* -- and once the paint layer is swapped the old appearance is
unrecoverable.

So this captures the before-half while it still exists: one PNG per state, and
beside it a **control inventory** in JSON.

The inventory is what parity is judged on, not the PNG
------------------------------------------------------
The port deliberately changes how text is rasterised -- a glyph atlas replaces
Qt's font engine, so metrics move by a pixel here and there -- which makes any
pixel or SSIM threshold either permanently red or so loose it proves nothing.
What must not change is *what is there and reachable*: every row, button, menu
item and strip cell present before must be present after, and hit-testable at
the same place.

:func:`inventory` therefore records two things per state:

* the widgets the layout believes it has -- panel rows, mode buttons, sequence
  rows, open-menu entries -- read from :class:`~.internal_gui.InternalGui`
  rather than from the image;
* every distinct control a coarse sweep of :meth:`~.internal_gui.InternalGui.hit_test`
  can actually *reach*. A control that is drawn but not hit-testable is a
  control the user cannot press, and the sweep is what tells those apart.

Use
---
    QT_QPA_PLATFORM=offscreen python -m chisurf.plugins.chimol.test.chrome_baseline

writes ``renders/chrome_baseline/<state>.png`` and ``inventory.json``.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

__all__ = ["STATES", "inventory", "capture", "OUT_DIR"]

#: Where the before-half lands.
OUT_DIR = pathlib.Path(__file__).resolve().parent / "renders" / "chrome_baseline"

#: The viewport the chrome is laid out for. Fixed so the after-half can be
#: taken at the same size -- a different width re-flows the panel and would
#: make a missing control indistinguishable from a re-wrapped one.
SIZE = (1280, 860)

#: The states worth photographing, as ``(name, setup)`` where ``setup`` is
#: applied to a live ``InternalGui``.
#:
#: A menu is open in one of them on purpose: menus are the only part of the
#: chrome that clips and scrolls, and ``setClipRect`` is the single QPainter
#: primitive with no obvious GPU-quad equivalent, so the state that exercises
#: it has to be in the baseline rather than discovered afterwards.
STATES: tuple[str, ...] = (
    "panel",
    "panel_and_sequence",
    "menu_open",
    "movie_transport",
    # Added after the four above were frozen. The in-viewport command line did
    # not exist when they were captured, so they switch it *off* explicitly
    # (see ``_apply_state``) rather than being re-photographed with it: their
    # PNGs are the only record of the QPainter chrome and cannot be re-taken.
    "command_line",
)


def _hit_sweep(gui, width: int, height: int, step: int = 4) -> list[str]:
    """Every distinct control a coarse sweep of ``hit_test`` can reach.

    Parameters
    ----------
    gui : InternalGui
        The laid-out panel.
    width, height : int
        Viewport size, in pixels.
    step : int
        Sweep spacing. Four pixels is finer than the smallest control and
        cheap enough to run over the whole viewport.

    Returns
    -------
    list of str
        Sorted ``"<kind>:<key>"`` labels. Reachability, not appearance -- a
        control that is painted but not in this list cannot be pressed.
    """
    found: set[str] = set()
    for y in range(0, height, step):
        for x in range(0, width, step):
            hit = gui.hit_test(x, y)
            kind = getattr(hit, "kind", None)
            if not kind:
                continue
            key = getattr(hit, "key", None)
            entry = getattr(hit, "entry", None)
            label = getattr(entry, "label", None) if entry is not None else None
            found.add(f"{kind}:{key or label or ''}")
    return sorted(found)


def inventory(gui, width: int, height: int) -> dict[str, Any]:
    """Describe what the panel holds and what of it is reachable.

    Parameters
    ----------
    gui : InternalGui
        The laid-out panel.
    width, height : int
        Viewport size, in pixels.

    Returns
    -------
    dict
        ``rows``, ``sequences``, ``menus`` and ``reachable``. Written beside
        the PNG and compared item by item after the port.
    """
    rows = [
        {
            "name": getattr(row, "name", None),
            "enabled": bool(getattr(row, "enabled", True)),
            "is_header": bool(getattr(row, "is_header", False)),
            "is_group": bool(getattr(row, "is_group", False)),
            "is_selection": bool(getattr(row, "is_selection", False)),
            "indent": int(getattr(row, "indent", 0)),
            "detail": getattr(row, "detail", ""),
        }
        for row in getattr(gui, "rows", []) or []
    ]
    sequences = [
        {
            "name": getattr(seq, "name", None),
            "columns": len(getattr(seq, "codes", "") or ""),
        }
        for seq in getattr(gui, "sequences", []) or []
    ]
    menus = [
        {
            "title": getattr(menu, "title", None),
            "entries": [getattr(e, "label", None) for e in (getattr(menu, "entries", None) or [])],
        }
        for menu in getattr(gui, "_menus", []) or []
    ]
    return {
        "size": [width, height],
        "rows": rows,
        "sequences": sequences,
        "menus": menus,
        "reachable": _hit_sweep(gui, width, height),
    }


def capture(out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """Photograph each state in :data:`STATES` and record its inventory.

    Parameters
    ----------
    out_dir : pathlib.Path, optional
        Where to write. Defaults to :data:`OUT_DIR`.

    Returns
    -------
    dict
        The inventory, keyed by state name. Also written as ``inventory.json``.

    Notes
    -----
    Needs Qt, because it is photographing the Qt implementation -- that is the
    point of a before-half. The after-half needs no font engine at all.
    """
    from chimol.hosts.qt import overlay as qt_overlay
    from chimol.ui.gui import InternalGui
    from qtpy import QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None  # keep it alive; see test_cmd_viewing's qapp note

    out_dir = pathlib.Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    width, height = SIZE

    record: dict[str, Any] = {}
    for state in STATES:
        gui = InternalGui()
        _apply_state(gui, state, width, height)

        image = qt_overlay.paint_chrome(gui, None, width, height, 1.0)
        if image is not None:
            QtGui.QImage(
                image.tobytes(),
                image.shape[1],
                image.shape[0],
                image.shape[1] * 4,
                QtGui.QImage.Format_RGBA8888_Premultiplied,
            ).save(str(out_dir / f"{state}.png"))

        record[state] = inventory(gui, width, height)

    (out_dir / "inventory.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    return record


def _apply_state(gui, state: str, width: int, height: int) -> None:
    """Drive *gui* into the named state and lay it out.

    Parameters
    ----------
    gui : InternalGui
        A fresh panel.
    state : str
        One of :data:`STATES`.
    width, height : int
        Viewport size, in pixels.
    """
    from chimol.ui.gui import GuiRow, SequenceRow

    gui.visible = True
    # The four original states are frozen images of a chrome that had no
    # command line, and their PNGs cannot be re-taken -- the QPainter path they
    # photograph is the before-half of the quad port. So the prompt is off for
    # them and on for the state that exists to show it, rather than every
    # baseline being invalidated by an addition none of them are about.
    gui.command_line.visible = state == "command_line"
    gui.set_rows(
        [
            GuiRow(name="all", is_header=True),
            GuiRow(name="148l"),
            GuiRow(name="sugars", enabled=False),
        ]
    )

    if state == "command_line":
        # Focused and mid-line, with output above it: unfocused it is one line
        # of hint text, which says nothing about the caret, the log colours or
        # what happens when a command has printed something.
        gui.focus_command(True)
        gui.command_line.set_text("color red, chain A")
        gui.command_line.feedback = 3
        gui.command_line.append("ChiMOL> fetch 148l", "echo")
        gui.command_line.append("loaded 148l: 1363 atoms", "message")
        gui.command_line.append("unknown command: colr", "error")

    if state not in ("panel", "command_line"):
        # ``sequence_visible`` gates the strip the way PyMOL's ``seq_view``
        # does -- off by default. Setting the rows without it lays out a strip
        # of zero height, which is why an earlier version of this capture
        # produced four identical images and an inventory that could not tell
        # the states apart.
        gui.sequence_visible = True
        gui.set_sequences(
            [
                SequenceRow(
                    name="148l",
                    codes="MNIFEMLRIDEGLRLKIYKDTEGYYTIGIGHLLTKSPSLNAAK",
                    numbers=list(range(1, 44)),
                )
            ]
        )

    # All three regions, every state: this is what a real frame does, and
    # laying out only the one a state is "about" leaves the others holding
    # rectangles from a different size.
    gui.layout(width, height)
    gui.layout_sequence(width, height)
    gui.layout_block(width, height)

    if state == "menu_open":
        # Menus hang off the per-row buttons, not off the name, so the press
        # has to land on one. Opened through ``mouse_press`` rather than
        # ``_open_menu`` so the menu is laid out by the code that lays it out
        # for real -- including the clipping and scrolling that make this the
        # state worth capturing.
        row = 1
        rect = gui._button_rects[row]["A"]
        gui.mouse_press(rect.x + rect.w / 2, rect.y + rect.h / 2)

    if state == "movie_transport":
        # ``movie_panel_visible`` is PyMOL's rule -- no transport for a
        # timeline of one -- so the frame count is what brings the scrubber and
        # the nine transport buttons into existence.
        gui.state = (12, 40)
        gui.layout_block(width, height)


if __name__ == "__main__":  # pragma: no cover - a capture, not a test
    record = capture()
    for _state, _entry in sorted(record.items()):
        print(
            f"{_state:20s} rows={len(_entry['rows'])} "
            f"sequences={len(_entry['sequences'])} "
            f"menus={len(_entry['menus'])} "
            f"reachable={len(_entry['reachable'])}"
        )
    print(f"written to {OUT_DIR}")
