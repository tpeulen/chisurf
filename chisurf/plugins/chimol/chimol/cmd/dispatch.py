"""Adapt chimol's command language to the console's dispatcher protocol.

chimol's prompt takes both its own commands (``fetch 1crn``, ``color red``) and
Python. Which one a line is belongs to :class:`chisurf.gui.chinsole.Chinsole` --
it applies the rule -- and *what the commands are* belongs here.
"""

from __future__ import annotations

import re
import typing

from . import completion

__all__ = ["ChimolDispatcher"]

_SPLIT = re.compile(r"[\s,]+")


class ChimolDispatcher:
    """Expose a chimol ``Cmd`` through the console's dispatcher protocol.

    Parameters
    ----------
    cmd : Cmd
        The command interpreter bound to a viewer.
    """

    def __init__(self, cmd: typing.Any) -> None:
        self.cmd = cmd

    def names(self) -> list[str]:
        """Return the command names.

        Returns
        -------
        list of str
        """
        return completion.command_names(self.cmd)

    def handles(self, line: str) -> bool:
        """Return whether *line* begins with a chimol command.

        Parameters
        ----------
        line : str

        Returns
        -------
        bool

        Notes
        -----
        This answers only "is this word one of mine". Whether it *runs* as a
        command is the console's decision, and it also requires the line not to
        be valid Python — otherwise chimol's ``set`` would shadow ``set()``.
        """
        first = _SPLIT.split(line.strip(), maxsplit=1)[0].lower()
        return bool(first) and first in set(self.names())

    def completions(self, line: str, cursor: int) -> list[str]:
        """Return completions for *line* at *cursor*.

        Parameters
        ----------
        line : str
        cursor : int

        Returns
        -------
        list of str
        """
        head = line[:cursor].lstrip()
        parts = _SPLIT.split(head)
        if not parts or not parts[0]:
            return []

        if len(parts) <= 1 and not head.endswith((" ", ",")):
            prefix = parts[0].lower()
            return [n for n in self.names() if n.startswith(prefix)]

        prefix = "" if head.endswith((" ", ",")) else parts[-1].lower()
        pool = completion.argument_pool(parts[0], self.cmd)
        return [item for item in pool if item.lower().startswith(prefix)]

    def execute(self, line: str) -> None:
        """Run *line* as a chimol command.

        Parameters
        ----------
        line : str

        Notes
        -----
        Exceptions are deliberately not caught. The previous handler wrapped
        this call in a bare ``except: pass``, so a mistyped command did nothing
        at all and said nothing about why; the console prints what escapes to
        its error channel instead.
        """
        self.cmd.do(line)
