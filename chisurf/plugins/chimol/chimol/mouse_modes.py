"""PyMOL's mouse-mode matrix, transcribed from ``pymol.controlling``.

The block PyMOL draws in the bottom-right of its viewport is this table: which
action each button carries under each modifier, for the mode you are in. It is
worth having exactly right rather than approximately, because it is *reference
material* -- someone reads it to find out what ctrl-shift-middle does, and a
table that is nearly right is worse than none.

So the bindings below are generated from PyMOL's own ``mode_dict`` rather than
copied off a screenshot, the same way the object menus were taken from its
``menu.py``. The labels are PyMOL's own casing (``MovZ``, ``PkAt``, ``MvSZ``),
which is not derivable from the action codes -- ``movz`` could be rendered a
dozen ways -- so that mapping is written out.

Chimol does not implement every action here. The table still shows all of them:
it describes PyMOL's mouse model, which is what someone is looking up, and
silently dropping the rows we have no answer for would make the block a subtly
different shape from the one they know.
"""
from __future__ import annotations

from .host.events import button_name, modifier_name

#: How PyMOL renders each action code. Its own capitalisation, which no rule
#: recovers -- ``mvsz`` is shown ``MvSZ`` and ``pk1`` as ``Pk1``.
ACTION_LABELS: dict[str, str] = {
    "none": "-",
    "rota": "Rota",
    "move": "Move",
    "movz": "MovZ",
    "movs": "MovS",
    "mvsz": "MvSZ",
    "mvzl": "MvZL",
    "movl": "MovL",
    "rotl": "RotL",
    "roto": "RotO",
    "movo": "MovO",
    "mvoz": "MvOZ",
    "rotf": "RotF",
    "movf": "MovF",
    "mvfz": "MvFZ",
    "torf": "TorF",
    "slab": "Slab",
    "clip": "Clip",
    "clpn": "ClpN",
    "clpf": "ClpF",
    "orig": "Orig",
    "cent": "Cent",
    "menu": "Menu",
    "sele": "Sele",
    "pkat": "PkAt",
    "pk1": "Pk1",
    "pkbd": "PkBd",
    "pktb": "PkTB",
    "+/-": "+/-",
    "+box": "+Box",
    "-box": "-Box",
    "box": "Box",
    "+lb": "+lb",
    "-lbx": "-lbX",
    "+lbx": "+lbX",
    "lbbx": "lbBx",
    "+mb": "+mb",
    "+rb": "+rb",
    "lb": "lb",
    "mb": "mb",
    "rb": "rb",
    "clik": "Clik",
    "dgrt": "DgRt",
    "dgmv": "DgMv",
    "dgmz": "DgMZ",
    "drgm": "DrgM",
    "drgo": "DrgO",
    "imsz": "ImSz",
    "imvz": "ImVZ",
    "irtz": "IrtZ",
    "mova": "MovA",
    "mvaz": "MvAZ",
    "movv": "MovV",
    "mvvz": "MvVZ",
    "rotv": "RotV",
    "rotz": "RotZ",
}

#: PyMOL's mouse-configuration rings: which modes the mode line cycles
#: through, from `pymol.controlling.ring_dict`. Cycling every mode there is
#: would step through editing modes nobody asked for; the ring is the point.
MODE_RINGS: dict[str, tuple[str, ...]] = {
    'maestro': ('three_button_maestro',),
    'one_button': ('one_button_viewing',),
    'three_button': ('three_button_viewing', 'three_button_editing'),
    'three_button_all_modes': ('three_button_editing', 'three_button_motions', 'three_button_viewing', 'three_button_lights'),
    'three_button_editing': ('three_button_editing', 'three_button_viewing'),
    'three_button_motions': ('three_button_motions', 'three_button_viewing'),
    'three_button_viewing': ('three_button_viewing', 'three_button_editing'),
    'two_button': ('two_button_viewing', 'two_button_selecting'),
    'two_button_editing': ('two_button_editing', 'two_button_viewing', 'two_button_selecting'),
    'two_button_viewing': ('two_button_viewing', 'two_button_selecting'),
}

#: The default ring, as `config_mouse` starts on.
DEFAULT_RING = "three_button"

#: The rows of the block, top to bottom: the modifier, and how PyMOL labels it.
MODIFIER_ROWS: tuple[tuple[str, str], ...] = (
    ("none", "& Keys"),
    ("shft", "Shft"),
    ("ctrl", "Ctrl"),
    ("ctsh", "CtSh"),
)

#: The click rows below them, each naming its own buttons.
CLICK_ROWS: tuple[tuple[str, str], ...] = (
    ("single", "SnglClk"),
    ("double", "DblClk"),
)

#: The columns, left to right, and their headings.
BUTTON_COLUMNS: tuple[tuple[str, str], ...] = (
    ("l", "L"),
    ("m", "M"),
    ("r", "R"),
    ("w", "Wheel"),
)


#: Every mode PyMOL offers, in its own order -- position matters there.
MODE_NAMES: dict[str, str] = {
    'three_button_lights': '3-Button Lights',
    'three_button_viewing': '3-Button Viewing',
    'three_button_editing': '3-Button Editing',
    'three_button_motions': '3-Button Motions',
    'three_button_maestro': '3-Button Maestro',
    'two_button_viewing': '2-Button Viewing',
    'two_button_selecting': '2-Btn. Selecting',
    'two_button_editing': '2-Button Editing',
    'two_button_lights': '2-Button Lights',
    'one_button_viewing': '1-Button Viewing',
}

#: ``{mode: {(button, modifier): action}}``, transcribed from
#: ``pymol.controlling.mode_dict``.
#:
#: PyMOL stores these as a *list* applied in order, and one mode binds a cell
#: twice -- ``three_button_motions`` sets double-left to ``menu`` and then to
#: ``torf``. The later binding is the one in effect, so that is the one kept
#: here; leaving both in a dict literal would have relied on the same rule
#: silently.
MODE_BINDINGS: dict[str, dict[tuple[str, str], str]] = {
    'three_button_lights': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'move',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'rotl',
        ('m', 'shft'): 'movl',
        ('r', 'shft'): 'mvzl',
        ('l', 'ctrl'): 'none',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'none',
        ('l', 'ctsh'): 'none',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'none',
        ('l', 'alt'): 'none',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'slab',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'mvsz',
        ('w', 'ctsh'): 'movz',
        ('double_left', 'none'): 'none',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'none',
        ('single_left', 'none'): 'none',
        ('single_middle', 'none'): 'cent',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
    },
    'three_button_viewing': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'move',
        ('r', 'none'): 'movz',
        ('l', 'shft'): '+Box',
        ('m', 'shft'): '-Box',
        ('r', 'shft'): 'clip',
        ('l', 'ctrl'): 'move',
        ('m', 'ctrl'): 'pkat',
        ('r', 'ctrl'): 'pk1',
        ('l', 'ctsh'): 'Sele',
        ('m', 'ctsh'): 'orig',
        ('r', 'ctsh'): 'clip',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'slab',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'mvsz',
        ('w', 'ctsh'): 'movz',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'pkat',
        ('single_left', 'none'): '+/-',
        ('single_middle', 'none'): 'cent',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
        ('single_left', 'ctrl'): 'cent',
    },
    'three_button_editing': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'move',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'roto',
        ('m', 'shft'): 'movo',
        ('r', 'shft'): 'mvoz',
        ('l', 'ctrl'): 'torf',
        ('m', 'ctrl'): '+/-',
        ('r', 'ctrl'): 'pktb',
        ('l', 'ctsh'): 'mova',
        ('m', 'ctsh'): 'orig',
        ('r', 'ctsh'): 'clip',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'slab',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'mvsz',
        ('w', 'ctsh'): 'movz',
        ('double_left', 'none'): 'torf',
        ('double_middle', 'none'): 'drgm',
        ('double_right', 'none'): 'pktb',
        ('single_left', 'none'): 'pkat',
        ('single_middle', 'none'): 'cent',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
        ('single_left', 'ctrl'): 'cent',
    },
    'three_button_motions': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'move',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'rotv',
        ('m', 'shft'): 'movv',
        ('r', 'shft'): 'mvvz',
        ('l', 'ctrl'): 'torf',
        ('m', 'ctrl'): 'pkat',
        ('r', 'ctrl'): 'pktb',
        ('l', 'ctsh'): 'mova',
        ('m', 'ctsh'): 'orig',
        ('r', 'ctsh'): 'clip',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'slab',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'mvsz',
        ('w', 'ctsh'): 'movz',
        ('double_left', 'none'): 'torf',
        ('double_middle', 'none'): 'drgm',
        ('double_right', 'none'): 'pktb',
        ('single_left', 'none'): 'pkat',
        ('single_middle', 'none'): 'cent',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
        ('single_left', 'ctrl'): 'cent',
    },
    'three_button_maestro': {
        ('l', 'none'): 'box',
        ('m', 'none'): 'rota',
        ('r', 'none'): 'move',
        ('l', 'shft'): '+Box',
        ('m', 'shft'): '-Box',
        ('r', 'shft'): 'clip',
        ('l', 'ctrl'): '+/-',
        ('m', 'ctrl'): 'irtz',
        ('r', 'ctrl'): 'pk1',
        ('l', 'ctsh'): 'Sele',
        ('m', 'ctsh'): 'orig',
        ('r', 'ctsh'): 'clip',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'imvz',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'none',
        ('w', 'ctsh'): 'slab',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'pkat',
        ('single_left', 'none'): 'sele',
        ('single_middle', 'none'): 'cent',
        ('single_right', 'none'): 'menu',
        ('single_left', 'shft'): '+/-',
        ('single_left', 'alt'): 'cent',
    },
    'two_button_viewing': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'none',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'pk1',
        ('m', 'shft'): 'none',
        ('r', 'shft'): 'clip',
        ('l', 'ctrl'): 'move',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'pkat',
        ('l', 'ctsh'): 'sele',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'cent',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'none',
        ('w', 'shft'): 'none',
        ('w', 'ctrl'): 'none',
        ('w', 'ctsh'): 'none',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'cent',
        ('single_left', 'none'): 'pkat',
        ('single_middle', 'none'): 'none',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
    },
    'two_button_selecting': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'none',
        ('r', 'none'): 'movz',
        ('l', 'shft'): '+Box',
        ('m', 'shft'): 'none',
        ('r', 'shft'): '-Box',
        ('l', 'ctrl'): '+/-',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'pkat',
        ('l', 'ctsh'): 'sele',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'cent',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'none',
        ('w', 'shft'): 'none',
        ('w', 'ctrl'): 'none',
        ('w', 'ctsh'): 'none',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'cent',
        ('single_left', 'none'): '+/-',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
    },
    'two_button_editing': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'none',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'pkat',
        ('m', 'shft'): 'none',
        ('r', 'shft'): 'clip',
        ('l', 'ctrl'): 'torf',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'pktb',
        ('l', 'ctsh'): 'rotf',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'movf',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'none',
        ('w', 'shft'): 'none',
        ('w', 'ctrl'): 'none',
        ('w', 'ctsh'): 'none',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'cent',
        ('single_left', 'none'): 'pkat',
        ('single_middle', 'none'): 'none',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
    },
    'two_button_lights': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'none',
        ('r', 'none'): 'movz',
        ('l', 'shft'): 'rotl',
        ('m', 'shft'): 'none',
        ('r', 'shft'): 'mvzl',
        ('l', 'ctrl'): 'movl',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'none',
        ('l', 'ctsh'): 'none',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'cent',
        ('l', 'alt'): 'none',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('w', 'none'): 'none',
        ('w', 'shft'): 'none',
        ('w', 'ctrl'): 'none',
        ('w', 'ctsh'): 'none',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'cent',
        ('single_left', 'none'): 'none',
        ('single_middle', 'none'): 'none',
        ('single_right', 'none'): 'menu',
        ('single_left', 'alt'): 'cent',
    },
    'one_button_viewing': {
        ('l', 'none'): 'rota',
        ('m', 'none'): 'none',
        ('r', 'none'): 'none',
        ('l', 'shft'): '+Box',
        ('m', 'shft'): 'none',
        ('r', 'shft'): 'none',
        ('l', 'ctrl'): 'movZ',
        ('m', 'ctrl'): 'none',
        ('r', 'ctrl'): 'none',
        ('l', 'ctsh'): 'clip',
        ('m', 'ctsh'): 'none',
        ('r', 'ctsh'): 'none',
        ('l', 'alt'): 'move',
        ('m', 'alt'): 'none',
        ('r', 'alt'): 'none',
        ('l', 'alsh'): '-Box',
        ('m', 'alsh'): 'none',
        ('r', 'alsh'): 'none',
        ('l', 'ctal'): 'none',
        ('m', 'ctal'): 'none',
        ('r', 'ctal'): 'none',
        ('l', 'ctas'): 'none',
        ('m', 'ctas'): 'none',
        ('r', 'ctas'): 'none',
        ('w', 'none'): 'slab',
        ('w', 'shft'): 'movs',
        ('w', 'ctrl'): 'mvsz',
        ('w', 'ctsh'): 'movz',
        ('double_left', 'none'): 'menu',
        ('double_middle', 'none'): 'none',
        ('double_right', 'none'): 'none',
        ('single_left', 'none'): '+/-',
        ('single_middle', 'none'): 'none',
        ('single_right', 'none'): 'none',
        ('single_left', 'shft'): 'none',
        ('single_left', 'ctrl'): 'menu',
        ('single_left', 'ctsh'): 'pkat',
        ('single_left', 'alt'): 'cent',
        ('single_left', 'alsh'): 'none',
        ('single_left', 'ctal'): 'none',
        ('single_left', 'ctas'): 'none',
    },
}


def action_for(mode: str, button: str, modifier: str) -> str:
    """Return the label for one cell of the block.

    Parameters
    ----------
    mode : str
        A key of :data:`MODE_BINDINGS`.
    button : str
        ``"l"``, ``"m"``, ``"r"``, ``"w"``, or a click spelling such as
        ``"single_left"``.
    modifier : str
        ``"none"``, ``"shft"``, ``"ctrl"``, ``"ctsh"`` or ``"alt"``.

    Returns
    -------
    str
        PyMOL's label, or ``"-"`` where the mode binds nothing. An unbound cell
        is drawn rather than left blank, so the grid keeps its shape.
    """
    bindings = MODE_BINDINGS.get(mode, {})
    action = bindings.get((button, modifier), "none")
    return ACTION_LABELS.get(action, ACTION_LABELS.get(action.lower(), action))


def rows_for(mode: str) -> list[tuple[str, list[str]]]:
    """Return the block for *mode* as ``(row label, four cell labels)``."""
    rows: list[tuple[str, list[str]]] = []
    for modifier, label in MODIFIER_ROWS:
        rows.append(
            (label, [action_for(mode, button, modifier) for button, _h in BUTTON_COLUMNS])
        )
    for prefix, label in CLICK_ROWS:
        cells = [
            action_for(mode, f"{prefix}_{name}", "none")
            for name in ("left", "middle", "right")
        ]
        rows.append((label, cells + [""]))     # no wheel column for a click
    return rows


def next_mode(mode: str, ring: str = DEFAULT_RING) -> str:
    """Return the mode after *mode* in *ring*, wrapping around.

    PyMOL cycles within a configured ring rather than through every mode it
    knows: the mode line on a viewing ring steps viewing -> editing -> viewing,
    and never lands on the lights or maestro modes unless you ask for them.
    Cycling all ten would walk someone through modes they did not choose.
    """
    modes = MODE_RINGS.get(ring) or MODE_RINGS.get(DEFAULT_RING) or ()
    if not modes:
        return mode
    if mode not in modes:
        return modes[0]
    return modes[(modes.index(mode) + 1) % len(modes)]


def modifier_of(modifiers) -> str:
    """Return PyMOL's name for a modifier state.

    Thin wrapper over :func:`chimol.host.events.modifier_name`, kept because
    this module's name for it is what the tables and the call sites use.
    """
    return modifier_name(modifiers)


def button_of(button) -> str:
    """Return PyMOL's name for a mouse button, or ``""``."""
    return button_name(button)


def action_of(mode: str, button, modifiers) -> str:
    """Return the *action code* a Qt button and modifier map to in *mode*.

    The code, not the label: the block draws ``MovZ`` and the handler wants
    ``movz``. Both come from one table, so what the panel promises and what the
    mouse does cannot drift apart -- which is the whole reason for wiring the
    handlers through here rather than writing the bindings out a second time.
    """
    name = button_of(button)
    if not name:
        return "none"
    bindings = MODE_BINDINGS.get(mode, {})
    return str(bindings.get((name, modifier_of(modifiers)), "none")).lower()


def click_action_of(mode: str, button, modifiers) -> str:
    """Return the action code a *click* carries, as opposed to a drag.

    PyMOL binds the press to the drag action (left is ``rota``) and the click
    -- a press released without a meaningful drag -- to a separate ``single_*``
    cell (``single_left`` is ``+/-`` in the viewing modes). This resolves that
    cell so the release handler can tell a click that selects from a drag that
    rotates.
    """
    name = {"l": "left", "m": "middle", "r": "right"}.get(button_name(button))
    if name is None:
        return "none"
    bindings = MODE_BINDINGS.get(mode, {})
    return str(bindings.get(("single_" + name, modifier_of(modifiers)), "none")).lower()


def wheel_action_of(mode: str, modifiers) -> str:
    """Return the action code the wheel carries under *modifiers*."""
    bindings = MODE_BINDINGS.get(mode, {})
    return str(bindings.get(("w", modifier_of(modifiers)), "none")).lower()


def normalize_mouse_mode(mode) -> str:
    """Return a valid rotation-style name.

    Parameters
    ----------
    mode : Any
        Candidate value, typically ``"pymol"`` or ``"chimol"``.

    Returns
    -------
    str
        ``"pymol"`` or ``"chimol"``; anything unrecognised falls back to
        ``"pymol"``.
    """
    return "chimol" if str(mode).lower().strip() == "chimol" else "pymol"


def rotation_delta_multiplier(mouse_mode: str) -> float:
    """The sign a left drag's rotation carries, by rotation style.

    In PyMOL-style rotation the *object* appears to follow the cursor; in
    chimol-style rotation the camera does, so the object turns the other way.

    Returns
    -------
    float
        ``-1.0`` for PyMOL-style object rotation, ``1.0`` for chimol-style
        camera rotation.
    """
    return -1.0 if mouse_mode == "pymol" else 1.0


def pan_delta_multiplier(mouse_mode: str) -> float:
    """The sign a pan carries, by rotation style.

    In PyMOL-style panning the object follows the cursor; in chimol-style
    panning the camera does, so the object moves opposite to it.

    Returns
    -------
    float
        ``1.0`` for PyMOL-style object panning, ``-1.0`` for chimol-style.
    """
    return 1.0 if mouse_mode == "pymol" else -1.0
