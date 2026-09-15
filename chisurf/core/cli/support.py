"""Shared building blocks for the chisurf command-line interfaces.

Every chisurf CLI -- the ``csc`` umbrella group and the per-plugin entry points
(``lltf``, ``burst-background``, ``count-rate``, ...) -- is a click group, and
they should behave the same way when a user mistypes a subcommand. That single
piece of behaviour used to come from the third-party ``click-didyoumean``
package; it is a ``difflib.get_close_matches`` call over the group's own command
names, so it lives here instead of in a dependency.

This module deliberately imports nothing from chisurf, so a plugin CLI can pull
in the group class without dragging in the plugin-registration machinery of
:mod:`chisurf.core.cli`.
"""

from __future__ import annotations

import difflib
import typing

import click

__all__ = ["DidYouMeanMixin", "DidYouMeanGroup"]


class DidYouMeanMixin:
    """Suggest close command names when a subcommand is not found.

    Mixed into a click group (before the click base class) it turns the bare
    ``No such command 'analyse'.`` into a git-like message that lists the
    registered commands closest to what was typed.

    Parameters
    ----------
    max_suggestions : int, optional
        Most suggestions to list. Default 3.
    cutoff : float, optional
        Similarity in ``[0, 1]`` a command name must reach to be suggested, as
        defined by :func:`difflib.get_close_matches`. Default 0.5.
    """

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        self.max_suggestions = kwargs.pop("max_suggestions", 3)
        self.cutoff = kwargs.pop("cutoff", 0.5)
        super().__init__(*args, **kwargs)

    def resolve_command(self, ctx: click.Context, args: list[str]):
        """Resolve a subcommand, adding suggestions when it does not exist.

        Parameters
        ----------
        ctx : click.Context
            Context of the group being resolved.
        args : list of str
            Remaining command-line arguments; ``args[0]`` is the command name.

        Returns
        -------
        tuple
            ``(name, command, remaining_args)`` as returned by click.

        Raises
        ------
        click.exceptions.UsageError
            When no command matches, with the suggestions appended.
        """
        try:
            return super().resolve_command(ctx, args)
        except click.exceptions.UsageError as error:
            matches = difflib.get_close_matches(
                click.utils.make_str(args[0]),
                self.list_commands(ctx),
                self.max_suggestions,
                self.cutoff,
            )
            if not matches:
                raise
            listed = "\n    ".join(matches)
            raise click.exceptions.UsageError(
                f"{error}\n\nDid you mean one of these?\n    {listed}", error.ctx
            ) from error


class DidYouMeanGroup(DidYouMeanMixin, click.Group):
    """Click group that suggests close matches for an unknown subcommand."""
