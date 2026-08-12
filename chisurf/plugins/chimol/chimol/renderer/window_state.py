"""Remember the viewport windows between runs, and snap them while dragging.

Two small services for the in-viewport window system, kept out of
``internal_gui`` because neither is about drawing:

* **persistence** -- each window's placement, visibility and fold state is a
  little dict keyed by the window's ``key``, written as
  ``chimol_windows.json`` beside the user's other chimol settings. A layout
  the user arranged and then lost to a restart is the fastest way to teach
  them not to arrange it.
* **snapping** -- a window dragged near (or flung past) the viewport's edge
  lands flush on it and *anchors* there: a corner pins both coordinates, a
  side pins one and keeps the window's own position on the other, and either
  way the window follows its edge when the viewport is resized. That anchor
  is how the object list and the mouse block keep their reference positions
  (top-right and bottom-right) without being nailed down.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["load_states", "save_states", "snap", "state_path"]

#: How near an edge (logical pixels) a dragged window snaps flush to it.
SNAP_DISTANCE = 14.0

#: The fields worth remembering about a window. Size is included for resizable
#: windows only -- an auto-sized panel's size is derived from its content and
#: restoring a stale one would fight the layout.
_FIELDS = ("x", "y", "w", "h", "visible", "collapsed", "anchor")


def state_path() -> Path | None:
    """Where the window states live.

    ``~/.chisurf`` inside a ChiSurf install, ``~/.chimol`` standalone -- see
    :mod:`chimol.settings_dir`. This answered ``None`` outside a ChiSurf
    install, which meant the toolkit-free window lost its layout on every run.

    Returns
    -------
    pathlib.Path or None
    """
    from ..settings_dir import settings_path  # noqa: PLC0415

    return settings_path("chimol_windows.json")


def load_states(path: Path | None = None) -> dict:
    """Return the saved window states, ``{}`` when none exist or are bad."""
    path = state_path() if path is None else path
    if path is None:
        return {}
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except Exception:
        logger.debug("chimol: unreadable window states; starting fresh",
                     exc_info=True)
        return {}
    if not isinstance(raw, dict):
        return {}
    states: dict = {}
    for key, entry in raw.items():
        if isinstance(entry, dict):
            states[str(key)] = {
                field: entry[field] for field in _FIELDS if field in entry
            }
    return states


def save_states(states: dict, path: Path | None = None) -> bool:
    """Write the window states; ``False`` when there is nowhere to write."""
    path = state_path() if path is None else path
    if path is None:
        return False
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(states, indent=2, sort_keys=True))
        return True
    except Exception:
        logger.debug("chimol: could not save window states", exc_info=True)
        return False


def snap(x: float, y: float, w: float, h: float,
         width: float, height: float, top: float = 0.0,
         distance: float = SNAP_DISTANCE) -> tuple[float, float, str | None]:
    """Snap a window rectangle to the viewport's edges.

    Parameters
    ----------
    x, y, w, h : float
        The window frame being dragged.
    width, height : float
        The viewport.
    top : float
        Height of fixed chrome at the top (menu and tool bars) that the
        snapped position should sit below.
    distance : float
        How near an edge the frame must be to snap.

    Returns
    -------
    tuple
        ``(x, y, anchor)`` -- the snapped position, and where the window is
        now glued: a corner (``"top-right"``, ...), a side (``"right"``,
        ``"top"``, ...), or ``None`` in the open. An anchored window follows
        its edge when the viewport resizes.

    Notes
    -----
    An edge counts as reached when the frame is within ``distance`` of it
    **or pushed past it** -- which is how an edge is actually hit: the cursor
    is flung at it and overshoots, the frame ends far beyond the line, and a
    symmetric ``abs()`` test concluded the window was nowhere near the edge
    it had just been slammed into. That miss is what made the sides feel
    unsticky.
    """
    left = x <= distance
    right = (x + w) >= width - distance
    high = y <= top + distance
    low = (y + h) >= height - distance

    if left:
        x = 0.0
    elif right:
        x = width - w
    if high:
        y = top
    elif low:
        y = height - h

    vertical = "top" if high else ("bottom" if low else "")
    horizontal = "left" if left else ("right" if right else "")
    anchor = "-".join(part for part in (vertical, horizontal) if part) or None
    return x, y, anchor


def anchored_position(anchor: str, x: float, y: float, w: float, h: float,
                      width: float, height: float, top: float = 0.0
                      ) -> tuple[float, float]:
    """Return the frame position an anchored window takes in this viewport.

    A corner anchor pins both coordinates; a side anchor pins one and keeps
    the window's own position on the other, so a window parked on the right
    side stays on the right side -- at its own height -- through resizes.
    """
    parts = set(str(anchor).split("-"))
    if "left" in parts:
        x = 0.0
    elif "right" in parts:
        x = max(width - w, 0.0)
    if "top" in parts:
        y = top
    elif "bottom" in parts:
        y = max(height - h, top)
    return x, y
