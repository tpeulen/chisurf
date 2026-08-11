"""What a typed command means in the browser.

Why this is not ``chimol.cmd.Cmd``
----------------------------------
It should be, and one day it is. ``Cmd`` is the real command language -- a
hundred-odd commands with a declarative registry and a parser -- and every one
of them acts on ``self.window``, a ``MolViewPluginWindow``: a Qt main window
holding the object store, the docked panels and the viewer. That window is
precisely the part a browser does not have, and the part the port is working
through panel by panel. Pointing the browser at ``Cmd`` today would produce a
prompt where every command answers "no window".

So this is a small command set bound to the browser :class:`~chimol.web.demo.Viewer`
directly -- the camera, the background, the panel and the sequence strip, which
is what the browser demo actually holds. It matters that it is *real*: the point
of the in-viewport prompt is that a browser can be typed at, and a prompt whose
commands are stubs proves nothing.

The spelling is PyMOL's, because it has to be: ``bg_color white``,
``turn x, 90``, ``set seq_view, off``. When the app layer ports and ``Cmd``
becomes reachable here, these names already match, and this module is deleted
rather than translated.
"""
from __future__ import annotations

import math
from collections.abc import Callable

__all__ = ["BrowserCommands"]


def _split(line: str) -> tuple[str, list[str]]:
    """Split *line* into a command name and its comma-or-space arguments.

    Parameters
    ----------
    line : str
        The typed line.

    Returns
    -------
    tuple
        The lowercased name and the argument strings, stripped.
    """
    text = line.strip()
    if not text:
        return "", []
    head, _, tail = text.partition(" ")
    parts = [part.strip() for part in tail.replace(",", " ").split()]
    return head.lower(), [part for part in parts if part]


class BrowserCommands:
    """The commands the browser viewer answers, and how it answers them.

    Parameters
    ----------
    viewer : chimol.web.demo.Viewer
        The viewer being driven.
    """

    def __init__(self, viewer) -> None:
        self.viewer = viewer
        #: Set by the viewer so a command's output reaches the prompt's log.
        self.report: Callable[[str], None] | None = None

    # ── dispatch ─────────────────────────────────────────────────────────
    def names(self) -> list[str]:
        """Every command name, for completion."""
        return sorted(
            name[3:] for name in dir(self) if name.startswith("do_")
        )

    def completions(self, line: str, cursor: int) -> list[str]:
        """Complete the command name at *cursor*.

        Arguments are not completed. The desktop's completer knows the loaded
        objects and the colour table; here the only pool worth offering is the
        command list, and offering a wrong pool is worse than offering none.
        """
        head = line[:cursor].lstrip()
        if " " in head or "," in head:
            return []
        return [name for name in self.names() if name.startswith(head.lower())]

    def __call__(self, line: str) -> None:
        """Run *line*. Raises :class:`ValueError` for an unknown command."""
        name, args = _split(line)
        if not name:
            return
        handler = getattr(self, f"do_{name}", None)
        if handler is None:
            raise ValueError(
                f"unknown command: {name} -- try 'help'"
            )
        handler(*args)

    def _say(self, text: str) -> None:
        if self.report is not None:
            self.report(text)

    # ── the commands ─────────────────────────────────────────────────────
    def do_help(self, *args: str) -> None:
        """List the commands, or describe one."""
        if args:
            handler = getattr(self, f"do_{args[0].lower()}", None)
            if handler is None:
                raise ValueError(f"unknown command: {args[0]}")
            self._say(f"{args[0]}: {(handler.__doc__ or '').strip().splitlines()[0]}")
            return
        self._say("  ".join(self.names()))

    def do_bg_color(self, *args: str) -> None:
        """Set the background colour, by PyMOL name or ``#rrggbb``."""
        from ..colors import as_rgba

        if not args:
            raise ValueError("bg_color needs a colour")
        rgba = as_rgba(args[0])
        if rgba is None:
            raise ValueError(f"no such colour: {args[0]}")
        self.viewer.background = (float(rgba[0]), float(rgba[1]), float(rgba[2]))

    def do_turn(self, *args: str) -> None:
        """Rotate the camera about an axis: ``turn x, 90``."""
        if len(args) < 2:
            raise ValueError("turn needs an axis and an angle: turn x, 90")
        axis = args[0].lower()
        if axis not in ("x", "y", "z"):
            raise ValueError(f"no such axis: {axis}")
        angle = math.radians(float(args[1]))
        self.viewer.turn(axis, angle)

    def do_zoom(self, *args: str) -> None:
        """Frame the molecule again, optionally with a buffer in Angstrom."""
        buffer = float(args[0]) if args else 0.0
        self.viewer.frame(buffer)

    def do_reset(self, *args: str) -> None:
        """Restore the starting camera."""
        self.viewer.reset_camera()

    def do_seq_view(self, *args: str) -> None:
        """Show or hide the sequence strip: ``seq_view on``."""
        self.viewer.gui.sequence_visible = _on_off(
            args, self.viewer.gui.sequence_visible
        )

    def do_internal_gui(self, *args: str) -> None:
        """Show or hide the object panel."""
        self.viewer.gui.visible = _on_off(args, self.viewer.gui.visible)

    def do_set(self, *args: str) -> None:
        """Set a viewer setting: ``set seq_view, off``.

        Only the settings this viewer holds are accepted, and an unknown name is
        an error rather than a silent no-op -- a ``set`` that quietly does
        nothing is the single most confusing thing a command layer can do.
        """
        if not args:
            raise ValueError("set needs a setting name")
        name = args[0].lower()
        rest = args[1:]
        known = {
            "seq_view": self.do_seq_view,
            "internal_gui": self.do_internal_gui,
            "internal_prompt": self.do_internal_prompt,
            "internal_feedback": self.do_internal_feedback,
        }
        handler = known.get(name)
        if handler is None:
            raise ValueError(f"unknown setting: {name}")
        handler(*rest)

    def do_internal_prompt(self, *args: str) -> None:
        """Show or hide this command line."""
        self.viewer.gui.command_line.visible = _on_off(
            args, self.viewer.gui.command_line.visible
        )

    def do_internal_feedback(self, *args: str) -> None:
        """How many lines of output the prompt shows above itself."""
        if not args:
            raise ValueError("internal_feedback needs a number of lines")
        self.viewer.gui.command_line.feedback = max(0, int(float(args[0])))

    def do_clear(self, *args: str) -> None:
        """Empty the feedback log."""
        self.viewer.gui.command_line.clear_log()

    def do_count_atoms(self, *args: str) -> None:
        """Report how many atoms the scene holds."""
        self._say(f"{self.viewer.atom_count} atoms")


def _on_off(args, current: bool) -> bool:
    """Read PyMOL's on/off/toggle argument.

    Parameters
    ----------
    args : sequence of str
        The command's arguments; empty means toggle, as PyMOL's buttons do.
    current : bool
        The present value, for a toggle.

    Returns
    -------
    bool
    """
    if not args:
        return not current
    value = str(args[0]).strip().lower()
    if value in ("on", "1", "true", "yes"):
        return True
    if value in ("off", "0", "false", "no"):
        return False
    if value == "toggle":
        return not current
    raise ValueError(f"expected on, off or toggle -- got {args[0]}")
