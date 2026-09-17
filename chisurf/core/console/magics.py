"""The magic registry.

Magics are ordinary functions taking ``(shell, line)`` -- or
``(shell, line, cell)`` for a cell magic. There is no class hierarchy and no
trait system, because a magic is a one-argument command and anything more is
scaffolding.

:func:`register_magic` is public: a ChiSurf plugin adds ``%burst_fit`` in three
lines, which is more than the console this replaces offered its host
application.
"""

from __future__ import annotations

import argparse
import dataclasses
import shlex
import typing

__all__ = [
    "MagicError",
    "MagicSpec",
    "MagicRegistry",
    "BUILTIN",
    "register_magic",
    "magic_parser",
    "parse_args",
]


class MagicError(Exception):
    """A magic could not do what was asked.

    Raised rather than printed so the shell renders it on the error channel in
    one place, and so a magic called from Python code can be caught.
    """


@dataclasses.dataclass(frozen=True)
class MagicSpec:
    """One registered magic.

    Attributes
    ----------
    name : str
    kind : str
        ``"line"`` or ``"cell"``.
    func : callable
    doc : str
    group : str
        Where it came from, for ``%lsmagic``.
    """

    name: str
    kind: str
    func: typing.Callable
    doc: str = ""
    group: str = "core"


class _ArgumentParser(argparse.ArgumentParser):
    """An :class:`argparse.ArgumentParser` that cannot exit the process."""

    def error(self, message: str) -> typing.NoReturn:
        """Raise :exc:`MagicError` instead of calling :func:`sys.exit`.

        Parameters
        ----------
        message : str

        Raises
        ------
        MagicError
            Always.
        """
        raise MagicError(f"{self.prog}: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> typing.NoReturn:
        """Raise :exc:`MagicError` instead of exiting.

        Parameters
        ----------
        status : int, optional
        message : str, optional

        Raises
        ------
        MagicError
            Always. ``--help`` reaches here too, which is why the message is
            passed through: printing usage must not take the GUI down with it.
        """
        raise MagicError(message or "")


def magic_parser(prog: str, description: str = "") -> argparse.ArgumentParser:
    """Return an argument parser safe to use inside a GUI.

    Parameters
    ----------
    prog : str
    description : str, optional

    Returns
    -------
    argparse.ArgumentParser
    """
    return _ArgumentParser(prog=prog, description=description, add_help=False)


def parse_args(line: str) -> list[str]:
    """Split a magic's argument line into words.

    Parameters
    ----------
    line : str

    Returns
    -------
    list of str
    """
    import os

    if not line.strip():
        return []
    try:
        return shlex.split(line, posix=os.name != "nt")
    except ValueError as exc:
        raise MagicError(f"could not parse arguments: {exc}") from exc


class MagicRegistry:
    """A collection of magics, addressable by name and kind."""

    def __init__(self) -> None:
        self._line: dict[str, MagicSpec] = {}
        self._cell: dict[str, MagicSpec] = {}

    def _table(self, kind: str) -> dict[str, MagicSpec]:
        """Return the table for *kind*.

        Parameters
        ----------
        kind : str

        Returns
        -------
        dict
        """
        return self._cell if kind == "cell" else self._line

    def register(
        self,
        name: str,
        func: typing.Callable,
        kind: str = "line",
        group: str = "core",
    ) -> None:
        """Add a magic.

        Parameters
        ----------
        name : str
        func : callable
        kind : str, optional
        group : str, optional
        """
        spec = MagicSpec(name, kind, func, (func.__doc__ or "").strip(), group)
        self._table(kind)[name] = spec

    def line(self, name: str | None = None, group: str = "core"):
        """Return a decorator registering a line magic.

        Parameters
        ----------
        name : str, optional
        group : str, optional

        Returns
        -------
        callable
        """

        def decorate(func: typing.Callable) -> typing.Callable:
            self.register(name or func.__name__, func, "line", group)
            return func

        return decorate

    def cell(self, name: str | None = None, group: str = "core"):
        """Return a decorator registering a cell magic.

        Parameters
        ----------
        name : str, optional
        group : str, optional

        Returns
        -------
        callable
        """

        def decorate(func: typing.Callable) -> typing.Callable:
            self.register(name or func.__name__, func, "cell", group)
            return func

        return decorate

    def get(self, name: str, kind: str = "line") -> MagicSpec | None:
        """Return the spec for *name*, or ``None``.

        Parameters
        ----------
        name : str
        kind : str, optional

        Returns
        -------
        MagicSpec or None
        """
        return self._table(kind).get(name)

    def names(self, kind: str | None = None) -> list[str]:
        """Return the registered magic names.

        Parameters
        ----------
        kind : str, optional
            ``"line"``, ``"cell"``, or both when omitted.

        Returns
        -------
        list of str
        """
        if kind == "line":
            return sorted(self._line)
        if kind == "cell":
            return sorted(self._cell)
        return sorted(set(self._line) | set(self._cell))

    def specs(self, kind: str = "line") -> list[MagicSpec]:
        """Return the specs for *kind*, name-ordered.

        Parameters
        ----------
        kind : str, optional

        Returns
        -------
        list of MagicSpec
        """
        return [self._table(kind)[name] for name in sorted(self._table(kind))]

    def call(
        self,
        shell: typing.Any,
        name: str,
        line: str,
        cell: str | None = None,
    ) -> typing.Any:
        """Invoke a magic.

        Parameters
        ----------
        shell : Shell
        name : str
        line : str
        cell : str, optional
            Present for a cell magic.

        Returns
        -------
        object

        Raises
        ------
        MagicError
            When no such magic is registered.
        """
        kind = "cell" if cell is not None else "line"
        spec = self.get(name, kind)
        if spec is None:
            # A cell magic that is not registered may still exist as a line
            # magic applied to a body; say so precisely rather than "unknown".
            other = self.get(name, "line" if kind == "cell" else "cell")
            if other is not None:
                raise MagicError(f"%{name} is a {other.kind} magic, not a {kind} magic")
            raise MagicError(f"unknown magic: %{name}  (try %lsmagic)")
        if kind == "cell":
            return spec.func(shell, line, cell)
        return spec.func(shell, line)

    def copy(self) -> MagicRegistry:
        """Return an independent copy.

        Each shell gets its own, so registering a magic in one console does not
        silently alter another.

        Returns
        -------
        MagicRegistry
        """
        clone = MagicRegistry()
        clone._line = dict(self._line)
        clone._cell = dict(self._cell)
        return clone


#: The magics every shell starts with.
BUILTIN = MagicRegistry()


def register_magic(
    name: str,
    func: typing.Callable | None = None,
    *,
    kind: str = "line",
    group: str = "plugin",
):
    """Register a magic on the built-in registry.

    Usable directly or as a decorator. Registering here affects shells created
    afterwards; an existing shell takes ``shell.register_magic_function``.

    Parameters
    ----------
    name : str
    func : callable, optional
        Omit to use as a decorator.
    kind : str, optional
    group : str, optional

    Returns
    -------
    callable
    """
    if func is not None:
        BUILTIN.register(name, func, kind, group)
        return func

    def decorate(target: typing.Callable) -> typing.Callable:
        BUILTIN.register(name, target, kind, group)
        return target

    return decorate
