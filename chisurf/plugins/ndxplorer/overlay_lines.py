"""Tabulated lines pushed into every open ndX window (Qt-free).

Another tool computes lines (the FRET-line tool's *Push to ndX*) and ndX draws
each one as a data curve of its Overlays tab. Every live
:class:`ndxplorer.app.frame.NdxApp` takes them, whichever host shows it (the
native emtk window, or the legacy Qt :class:`~chisurf.plugins.ndxplorer.window.NdxWindow`),
so this lives apart from any host.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["push_overlay_lines"]


def push_overlay_lines(lines, source: str = "ChiSurf") -> int:
    """Draw tabulated lines in every open ndX window (``NdxApp.add_overlay_lines``).

    Every app of :func:`ndxplorer.app.frame.live_apps` takes them, whichever
    route opened it (the Qt :class:`~chisurf.plugins.ndxplorer.window.NdxWindow`, or the emtk entry point
    hosted directly); each becomes a data curve of its Overlays tab.

    Parameters
    ----------
    lines : sequence of dict
        A LineSet: ``{"name", "x", "y", "style": {"color"}}`` per line.
    source : str
        Who sent them, shown with the curves.

    Returns
    -------
    int
        How many windows took them (0: no ndX window is open).
    """
    from ndxplorer.app.frame import live_apps

    taken = 0
    for app in live_apps():
        try:
            app.add_overlay_lines(list(lines), source=source)
        except Exception:  # noqa: BLE001 - one window failing does not stop the rest
            logger.warning("ndX window did not take the lines", exc_info=True)
            continue
        wake = getattr(app, "request_frame", None)
        if callable(wake):
            wake()
        taken += 1
    return taken
