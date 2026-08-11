"""Keyboard keys, as plain integers, and how each host spells them.

Why the engine owns these
-------------------------
The in-viewport command line is a text editor, and a text editor is decisions
about keys: Return submits, Up recalls, ctrl+A goes to the start of the line.
That is the same arithmetic-over-a-table shape as :mod:`chimol.host.events`, and
it has the same constraint -- the engine must be able to make those decisions
where there is no window system.

The values are Qt's ``Qt.Key_*``, for the same reason the button values are
Qt's: they are fixed by an ABI, so writing them out costs nothing, and a Qt
event's ``key()`` can be passed straight in. A browser reports something else
entirely -- ``KeyboardEvent.key`` is a *string* -- so :func:`key_from_dom`
translates into these rather than the engine learning a second vocabulary.

The DOM table is deliberately small: printable characters do not appear in it at
all, because a browser reports them as their own text and the editor inserts
that text. Only the keys that *act* need names.
"""
from __future__ import annotations

__all__ = [
    "KEY_BACKSPACE",
    "KEY_DELETE",
    "KEY_DOWN",
    "KEY_END",
    "KEY_ENTER",
    "KEY_ESCAPE",
    "KEY_HOME",
    "KEY_LEFT",
    "KEY_RETURN",
    "KEY_RIGHT",
    "KEY_TAB",
    "KEY_UP",
    "key_from_dom",
    "modifiers_from_dom",
]

#: ``Qt.Key_*``. Return and Enter are distinct -- Enter is the numeric keypad's
#: -- and both submit, which is why every caller has to test for the pair.
KEY_ESCAPE = 0x01000000
KEY_TAB = 0x01000001
KEY_BACKSPACE = 0x01000003
KEY_RETURN = 0x01000004
KEY_ENTER = 0x01000005
KEY_DELETE = 0x01000007
KEY_HOME = 0x01000010
KEY_END = 0x01000011
KEY_LEFT = 0x01000012
KEY_UP = 0x01000013
KEY_RIGHT = 0x01000014
KEY_DOWN = 0x01000015

#: ``KeyboardEvent.key`` -> the constants above.
#:
#: A browser names the keypad's Enter ``"Enter"`` as well, so there is nothing
#: to distinguish; it maps to ``KEY_RETURN`` and the pair test still holds.
_DOM_KEYS: dict[str, int] = {
    "Escape": KEY_ESCAPE,
    "Esc": KEY_ESCAPE,             # IE/Edge legacy spelling, still emitted
    "Tab": KEY_TAB,
    "Backspace": KEY_BACKSPACE,
    "Enter": KEY_RETURN,
    "Delete": KEY_DELETE,
    "Del": KEY_DELETE,
    "Home": KEY_HOME,
    "End": KEY_END,
    "ArrowLeft": KEY_LEFT,
    "ArrowUp": KEY_UP,
    "ArrowRight": KEY_RIGHT,
    "ArrowDown": KEY_DOWN,
    "Left": KEY_LEFT,
    "Up": KEY_UP,
    "Right": KEY_RIGHT,
    "Down": KEY_DOWN,
}


def key_from_dom(name: str) -> int:
    """Return the engine's key value for a DOM ``KeyboardEvent.key``.

    Parameters
    ----------
    name : str
        The browser's name for the key, e.g. ``"ArrowLeft"`` or ``"a"``.

    Returns
    -------
    int
        One of the ``KEY_*`` constants, or ``0`` for a key with no special
        meaning -- which is every printable character, and is not a failure:
        the caller passes the character's *text* alongside and the editor
        inserts it.
    """
    return _DOM_KEYS.get(str(name), 0)


def modifiers_from_dom(ctrl: bool, shift: bool, alt: bool, meta: bool) -> int:
    """Pack a DOM event's four modifier booleans into an engine mask.

    Parameters
    ----------
    ctrl, shift, alt, meta : bool
        ``KeyboardEvent.ctrlKey`` and friends.

    Returns
    -------
    int
        A mask of :mod:`chimol.host.events`' ``*_MODIFIER`` values.

    Notes
    -----
    ``metaKey`` is Command on a Mac, where it -- not Control -- is what a
    line-editing shortcut is bound to. It is reported separately rather than
    folded into Control, and the command line accepts either, because a browser
    on Linux sends ``ctrlKey`` for the same intent.
    """
    from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER

    mask = 0
    if ctrl:
        mask |= CONTROL_MODIFIER
    if shift:
        mask |= SHIFT_MODIFIER
    if alt:
        mask |= ALT_MODIFIER
    if meta:
        mask |= META_MODIFIER
    return mask
