"""Advanced mode: rarely needed controls stay hidden until asked for.

Chisurf's plugins show a working set of controls -- the parameters an analysis
needs -- and keep the rest (routing-channel assignments, file types, detector
pairing, ...) behind one *Advanced* switch. The workflow hubs make the split
concrete: a step hosted in a pipeline takes its detector setup from the
pipeline's setup step, so its own channel controls are exactly the kind of
thing that belongs behind the switch.

The flag is process-wide and per session; plugins read it while drawing, so a
toggle redraws every open window. It is not a user profile: nothing persists.
"""

from __future__ import annotations

__all__ = ["advanced_mode", "set_advanced_mode", "draw_toggle"]

_advanced = False


def advanced_mode() -> bool:
    """Whether advanced controls are shown (default ``False``)."""
    return _advanced


def set_advanced_mode(on: bool) -> None:
    """Show (``True``) or hide (``False``) advanced controls, process-wide."""
    global _advanced
    _advanced = bool(on)


def draw_toggle(label: str = "Advanced") -> bool:
    """Draw the switch. Returns ``True`` on the frame the user flips it."""
    from emtk import im
    from emtk.i18n import tr

    changed, on = im.checkbox(tr(label), advanced_mode())
    im.set_item_tooltip(
        tr("Show the rarely needed controls: routing channels, file types, raw "
           "detector settings. Off, only what an analysis needs is visible.", domain="emtk")
    )
    if changed:
        set_advanced_mode(on)
    return changed
