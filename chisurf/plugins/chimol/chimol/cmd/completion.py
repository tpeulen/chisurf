"""Completion vocabulary for the chimol command language.

One source, read by both front ends: the Qt console
(:class:`chisurf.gui.chinsole.Chinsole` via the app's dispatcher) and the
terminal REPL's prompt-toolkit completer.

It existed twice before, and the two copies had drifted — the terminal's
setting list was missing the six ``metaball_*`` entries and appended them
separately, so which settings could be completed depended on which prompt you
were typing at. A vocabulary that describes the *same* command language has no
business being duplicated.

Qt-free on purpose, so the terminal REPL does not pull a GUI stack in to know
what a colour is called.
"""

from __future__ import annotations

import typing

__all__ = [
    "REPRESENTATIONS",
    "COLOURS",
    "SETTINGS",
    "REPRESENTATION_COMMANDS",
    "COLOUR_COMMANDS",
    "SETTING_COMMANDS",
    "OBJECT_COMMANDS",
    "argument_pool",
    "command_names",
]

#: Values accepted by ``show`` / ``hide`` / ``as``.
REPRESENTATIONS = (
    "cartoon", "sticks", "atoms", "dots", "surface",
    "ca_trace", "lines", "spheres", "metaball", "plane", "all",
)

#: Values accepted by ``color`` and ``bg_color``. Colouring *schemes* sit
#: alongside literal colours because the command takes either.
COLOURS = (
    "red", "green", "blue", "yellow", "cyan", "magenta",
    "white", "black", "gray", "orange",
    "single", "by_residue", "by_ss", "by_sequence",
    "byelement", "bychain", "spectrum",
)

#: Names accepted by ``set`` / ``get``.
SETTINGS = (
    "bg_color", "color_mode", "line_width", "stick_radius",
    "sphere_scale", "cartoon_transparency", "surface_type",
    "metaball_alpha", "metaball_shininess", "metaball_threshold",
    "metaball_resolution", "metaball_radius", "metaball_padding",
)

REPRESENTATION_COMMANDS = frozenset({"show", "hide", "as"})
COLOUR_COMMANDS = frozenset({"color", "bg_color", "bg_colour"})
SETTING_COMMANDS = frozenset({"set", "get"})
OBJECT_COMMANDS = frozenset({
    "select", "delete", "enable", "disable",
    "show", "hide", "color", "center", "zoom",
})


def command_names(cmd: typing.Any) -> list[str]:
    """Return the registered command names.

    Parameters
    ----------
    cmd : Cmd or None

    Returns
    -------
    list of str
        Empty when *cmd* is unavailable, so a completer can be built before a
        viewer exists.
    """
    if cmd is None or not hasattr(cmd, "command_names"):
        return []
    try:
        return sorted(cmd.command_names())
    except Exception:
        return []


def _object_names(cmd: typing.Any) -> list[str]:
    """Return the names of the objects currently loaded.

    Parameters
    ----------
    cmd : Cmd or None

    Returns
    -------
    list of str
    """
    if cmd is None:
        return []
    try:
        _window, viewer = cmd._require_window_and_viewer()
    except Exception:
        return []
    if viewer is None:
        return []
    try:
        return [obj["name"] for obj in viewer.list_objects() if "name" in obj]
    except Exception:
        return []


def argument_pool(command: str, cmd: typing.Any = None) -> list[str]:
    """Return the completion candidates for *command*'s arguments.

    Parameters
    ----------
    command : str
        The command name, as typed.
    cmd : Cmd, optional
        Consulted for the names of loaded objects, which are the one part of
        the vocabulary that is not static.

    Returns
    -------
    list of str
        Sorted and case-insensitively de-duplicated.
    """
    name = command.strip().lower()
    pool: list[str] = []
    if name in REPRESENTATION_COMMANDS:
        pool.extend(REPRESENTATIONS)
    if name in COLOUR_COMMANDS:
        pool.extend(COLOURS)
    if name in SETTING_COMMANDS:
        pool.extend(SETTINGS)
    if name in OBJECT_COMMANDS:
        pool.extend(_object_names(cmd))

    seen: set[str] = set()
    result: list[str] = []
    for item in sorted(pool):
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
