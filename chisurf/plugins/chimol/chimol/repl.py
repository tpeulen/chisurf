"""Which typed line is a command and which is Python -- and who gets to decide.

chimol's prompt takes two languages at once: its own commands (``fetch 1crn``,
``color red``) and Python (``viewer.objects``). Something has to route each
line, and the rule is subtler than "is the first word a command" -- that
version sent ``set`` to chimol's ``set`` rather than the builtin, which is the
case the rule exists to protect.

Why the decision is attachable
------------------------------
The rule is not chimol's alone. A host that already runs a console has already
answered it, and answering it a second way is how two prompts in the same
application come to disagree about what ``set`` means. But chimol also has to
work with *no* host at all: it runs in a plain terminal, in a GLFW window and
in a browser, and in none of those is there a console to ask.

So the resolver is a **seam**. A host calls :func:`attach` with its own, and
chimol uses it; nobody attaches, and chimol uses the one below, which is built
on :mod:`codeop` and the command vocabulary and needs nothing but the standard
library. That is the same shape as :mod:`chimol.settings_dir`: ask, and carry
your own answer for when there is nothing to ask.

The fallback is not a stub. It implements the rule in full -- compile the line,
and if it compiles as Python, route it to Python **unless** its first name is
undefined there -- so a chimol running alone behaves the way a chimol running
inside a console does, rather than degrading to the naive version the rule
replaced.
"""
from __future__ import annotations

import codeop
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from collections.abc import Mapping

__all__ = ["ReplRouter", "attach", "attached", "detach", "router"]


@runtime_checkable
class ReplRouter(Protocol):
    """What chimol's prompt needs from whoever is routing its input."""

    def is_command(
        self, line: str, namespace: Mapping[str, Any] | None = None
    ) -> bool:
        """Whether *line* belongs to the command layer rather than Python."""

    def is_incomplete_python(self, line: str) -> bool:
        """Whether *line* is an unfinished block awaiting more input."""


class _BuiltinRouter:
    """chimol's own answer, for when no host has attached one.

    Implements the same rule as a console host: a line that compiles as Python
    is Python, unless the name it starts with does not exist in the namespace,
    in which case it was meant as a command. A line that does not compile is a
    command -- at a command prompt a non-compiling word is a mistyped command
    far more often than a mistyped expression, and the command layer can say so
    by name, where Python can only say ``NameError``.
    """

    def is_incomplete_python(self, line: str) -> bool:
        """Whether ptpython should keep collecting rather than route the line.

        An unfinished block is neither language yet: without this ``for i in
        range(3):`` is swallowed as a command and the body can never be typed.
        ``codeop.compile_command`` returns ``None`` for exactly that state.
        """
        try:
            return codeop.compile_command(line, symbol="exec") is None
        except (SyntaxError, ValueError, OverflowError):
            # A hard syntax error is not *incomplete*, it is wrong -- and a
            # wrong line still has to be routed somewhere rather than left
            # collecting input forever.
            return False

    def is_command(
        self, line: str, namespace: Mapping[str, Any] | None = None
    ) -> bool:
        """Whether *line* goes to the command dispatcher."""
        if not line.strip():
            return False
        if not self._compiles_as_python(line):
            return True
        return not self._first_name_exists(line, namespace)

    @staticmethod
    def _compiles_as_python(line: str) -> bool:
        try:
            compile(line, "<input>", "exec")
        except (SyntaxError, ValueError, OverflowError):
            return False
        return True

    @staticmethod
    def _first_name_exists(
        line: str, namespace: Mapping[str, Any] | None
    ) -> bool:
        """Whether the line's leading name is bound in *namespace*.

        ``color red`` compiles as Python only in the sense that ``color`` is a
        name and ``red`` follows it -- but if neither is defined, it was a
        command. Checking the *first* name is what keeps ``set`` pointing at
        the builtin while ``fetch 1crn`` still reaches chimol.
        """
        head = line.strip().split()[0].split("(")[0].split("[")[0].split(".")[0]
        if not head.isidentifier():
            return True  # not a bare name at all -- treat as Python
        if namespace is not None and head in namespace:
            return True
        import builtins

        return hasattr(builtins, head)


#: The fallback, built once. Stateless, so sharing it is safe.
_BUILTIN = _BuiltinRouter()

#: What a host attached, if one did.
_attached: ReplRouter | None = None


def attach(host: ReplRouter) -> None:
    """Route chimol's prompt through *host* instead of the built-in rule.

    Parameters
    ----------
    host : ReplRouter
        Anything answering :meth:`~ReplRouter.is_command` and
        :meth:`~ReplRouter.is_incomplete_python`. A module works: the protocol
        is named after the two functions a console already exports, so
        ``attach(chisurf.core.console.dispatch)`` is the whole integration.

    Raises
    ------
    TypeError
        If *host* does not answer both. Failing here names the missing method;
        failing later means a prompt that routes every line to the wrong
        language and no clue why.
    """
    missing = [
        name
        for name in ("is_command", "is_incomplete_python")
        if not callable(getattr(host, name, None))
    ]
    if missing:
        raise TypeError(
            f"{host!r} cannot route a chimol prompt: it has no "
            + " or ".join(missing)
        )
    global _attached
    _attached = host


def detach() -> None:
    """Go back to the built-in rule. Mainly for tests."""
    global _attached
    _attached = None


def attached() -> bool:
    """Whether a host has attached a router."""
    return _attached is not None


def router() -> ReplRouter:
    """The router in force: whatever was attached, else chimol's own."""
    return _attached if _attached is not None else _BUILTIN
