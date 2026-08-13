"""What each key does in the viewport, and where that is written down.

Why this is a table rather than a chain of ``if``\\ s
----------------------------------------------------
The viewer's single-key shortcuts used to be six hard-coded comparisons inside
``MolView.handle_key_event`` -- ``if ch == "r": ...`` -- which made two things
impossible at once. There was nowhere to *read* the bindings from, so the only
way to find out what ``d`` did was to open the source; and there was nowhere to
*write* them, so a key that collided with something (or with a keyboard layout
that does not have it where a US layout does) could not be moved.

Both fall out of putting the same information in one place: a table of actions,
each with the command it runs and one line saying what it is for, and the key
itself in the display configuration next to every other preference. The
overlay (``keys``) reads the table; the settings panel edits the configuration;
``handle_key_event`` resolves through both. Nothing is duplicated, so a binding
cannot be listed as one thing and do another.

Why the *action* is the stable name, not the key
------------------------------------------------
The configuration maps ``action -> key``, not ``key -> action``. A key is the
part the user changes, so keying the table by it would mean a rebind rewrites
the identity of the entry; the action is what stays put. It also makes the
"two actions on one key" case detectable rather than silently
last-one-wins -- see :func:`conflicts`.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ACTIONS",
    "Binding",
    "action_for_key",
    "bindings",
    "conflicts",
    "default_keys",
]


@dataclass(frozen=True)
class Binding:
    """One row of the table: an action, what it does, and the key on it.

    Attributes
    ----------
    action : str
        The stable identifier, and the key under ``keys`` in the display
        configuration.
    key : str
        The character currently bound, or ``""`` when the binding has been
        cleared (which is a legitimate way to switch a shortcut off).
    label : str
        What the overlay shows.
    """

    action: str
    key: str
    label: str


#: Every bindable action, as ``action -> (default key, label)``. The default is
#: what shipped as the hard-coded comparison, so an existing user's muscle
#: memory is unchanged; the label is what the overlay prints.
#:
#: ASCII only, deliberately: the overlay draws through the chrome's glyph
#: atlas, and a character the atlas has not baked paints as **nothing** at all
#: rather than raising (see ``docs/development/chimol_widget_toolkit.md``).
ACTIONS: dict[str, tuple[str, str]] = {
    "cartoon": ("r", "Show the cartoon / ribbon representation"),
    "ca_trace": ("c", "Show the C-alpha trace"),
    "atoms": ("b", "Show atoms (ball representation)"),
    "dots": ("d", "Toggle the dot surface"),
    "sidechains": ("s", "Toggle side chains in the atom view"),
    "close": ("q", "Close the viewer window"),
}


def default_keys() -> dict[str, str]:
    """The shipped ``action -> key`` mapping, as a fresh dict."""
    return {action: key for action, (key, _label) in ACTIONS.items()}


def _configured() -> dict[str, str]:
    """The live ``keys`` section, normalised to lower-case single characters.

    Falls back to the default for any action the configuration has no opinion
    on, so a config written before an action existed still resolves it.
    """
    from .config import _DISPLAY_CONFIG  # noqa: PLC0415

    section = _DISPLAY_CONFIG.get("keys")
    resolved = default_keys()
    if isinstance(section, dict):
        for action in resolved:
            if action not in section:
                continue
            try:
                value = str(section[action] or "").strip().lower()
            except Exception:  # noqa: BLE001 - a preference is not worth a crash
                continue
            # One character, or empty to mean "unbound". A longer string is a
            # typo rather than a chord: there is no chord support here, and
            # silently honouring its first letter would bind something the
            # user did not ask for.
            resolved[action] = value[:1] if len(value) == 1 else ("" if not value else value[:1])
    return resolved


def bindings() -> list[Binding]:
    """Every action with its current key, in the table's own order.

    Returns
    -------
    list of Binding
        Ordered as :data:`ACTIONS` is, which groups the representation
        switches together and leaves ``close`` last -- the order the overlay
        prints and the order a reader scans.
    """
    live = _configured()
    return [
        Binding(action, live.get(action, ""), label)
        for action, (_default, label) in ACTIONS.items()
    ]


def action_for_key(char: str) -> str | None:
    """Which action ``char`` runs, or ``None`` when nothing is bound to it.

    Parameters
    ----------
    char : str
        The character the key produced. Compared case-insensitively, because
        the shortcuts are single letters and shift is not part of the binding.

    Returns
    -------
    str or None
        The action name, or ``None``. An unbound (empty) key never matches, so
        clearing a binding really does switch the shortcut off rather than
        making it fire on every keystroke that produces no text.
    """
    wanted = str(char or "").strip().lower()
    if not wanted:
        return None
    for action, key in _configured().items():
        if key and key == wanted:
            return action
    return None


def conflicts() -> dict[str, list[str]]:
    """Keys bound to more than one action, as ``key -> [action, ...]``.

    Worth reporting rather than resolving: two actions on one key is a state
    the settings panel can be typed into, and the honest thing is to say so.
    :func:`action_for_key` returns the first in table order, so the behaviour
    is at least deterministic while it lasts.
    """
    seen: dict[str, list[str]] = {}
    for action, key in _configured().items():
        if key:
            seen.setdefault(key, []).append(action)
    return {key: actions for key, actions in seen.items() if len(actions) > 1}
