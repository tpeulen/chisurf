"""Mouse buttons and keyboard modifiers, as plain integers.

Why the engine owns these
-------------------------
The panel's hit-testing and the mouse-mode table decide what a click *means*:
which row it landed on, and whether ctrl+shift+left is ``CtSh``'s left cell or
``Ctrl``'s. That is arithmetic over a table, and it was the last thing in
chimol's engine that reached for a GUI toolkit -- ``mouse_modes`` imported Qt
inside three functions purely to compare against ``Qt.LeftButton`` and
``Qt.ControlModifier``.

The values below are fixed by Qt's ABI, so nothing is lost by writing them out,
and what is gained is that the engine can decide what a click means with no
window system present. A browser reports a different set (DOM ``button`` is
0/1/2 and its modifiers are booleans), so a second host translates into *these*
rather than the engine learning a second vocabulary.

Named ``host`` rather than ``platform``: a package called ``platform`` beside
modules that are sometimes imported with their own directory on ``sys.path``
would shadow the standard library's, which is a failure this repository has
already paid for once with ``chisurf/math/`` and the stdlib ``math``.
"""
from __future__ import annotations

__all__ = [
    "NO_BUTTON",
    "LEFT_BUTTON",
    "RIGHT_BUTTON",
    "MIDDLE_BUTTON",
    "NO_MODIFIER",
    "SHIFT_MODIFIER",
    "CONTROL_MODIFIER",
    "ALT_MODIFIER",
    "META_MODIFIER",
    "button_name",
    "modifier_name",
]

#: Mouse buttons. These are ``Qt.LeftButton`` and friends -- note that middle
#: is 4 and right is 2, which is the ordering a hand-written table gets wrong.
NO_BUTTON = 0
LEFT_BUTTON = 1
RIGHT_BUTTON = 2
MIDDLE_BUTTON = 4

#: Keyboard modifiers, as ``Qt.KeyboardModifier`` spells them.
NO_MODIFIER = 0x00000000
SHIFT_MODIFIER = 0x02000000
CONTROL_MODIFIER = 0x04000000
ALT_MODIFIER = 0x08000000
META_MODIFIER = 0x10000000

#: PyMOL's modifier row names, most specific first.
#:
#: The order is the point: ctrl+shift is its own row (``CtSh``), not a ctrl row
#: that happens to have shift held, so the combination has to be tested before
#: either of its parts.
_MODIFIER_ROWS: tuple[tuple[str, int], ...] = (
    ("ctsh", CONTROL_MODIFIER | SHIFT_MODIFIER),
    ("ctrl", CONTROL_MODIFIER),
    ("shft", SHIFT_MODIFIER),
    ("alt", ALT_MODIFIER),
)

#: PyMOL's button names.
_BUTTON_NAMES: tuple[tuple[int, str], ...] = (
    (LEFT_BUTTON, "l"),
    (MIDDLE_BUTTON, "m"),
    (RIGHT_BUTTON, "r"),
)


def button_name(button) -> str:
    """Return PyMOL's name for a mouse button.

    Parameters
    ----------
    button : int
        One of the ``*_BUTTON`` constants. A Qt button enum compares equal to
        its integer value, so a Qt event's ``button()`` may be passed directly.

    Returns
    -------
    str
        ``"l"``, ``"m"``, ``"r"``, or ``""`` for anything else.
    """
    for value, name in _BUTTON_NAMES:
        if int(button) == value:
            return name
    return ""


def modifier_name(modifiers) -> str:
    """Return PyMOL's name for a modifier state.

    Parameters
    ----------
    modifiers : int
        A mask of the ``*_MODIFIER`` constants.

    Returns
    -------
    str
        ``"ctsh"``, ``"ctrl"``, ``"shft"``, ``"alt"`` or ``"none"``.
    """
    value = int(modifiers)
    for name, mask in _MODIFIER_ROWS:
        if (value & mask) == mask:
            return name
    return "none"
