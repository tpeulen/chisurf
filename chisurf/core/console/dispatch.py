"""The one rule for deciding whether a typed line is a command or Python.

A console that accepts both a command language and Python has to decide, per
line, which one it is looking at. The rule is short but every clause of it was
paid for by a bug report, which is why it lives here rather than being written
out again at each prompt: it was written out three times -- the Qt console, the
standalone REPL's ptpython binding, and that REPL's ``input()`` fallback -- and
the three had drifted into three different rules, two of them carrying defects
the third had already fixed.

The rule, in order:

1. a line that does **not** compile as Python is a command (``fetch 1f5n`` is a
   syntax error, and at a command prompt so is a mistyped command name -- which
   is better answered by name than by ``NameError``);
2. a line that compiles is Python only when the name it would evaluate actually
   exists. ``set`` is a builtin and stays Python; ``ray``, ``zoom``, ``orient``,
   ``undo`` are bound to nothing, so evaluating them can only ever raise, and
   the command is what was meant.

Clause 2 is the one that is easy to get wrong in either direction. Preferring
Python whenever the line compiles makes every **no-argument** command
unreachable; preferring the command whenever the dispatcher claims the name
shadows real Python.

Note what is *not* in the rule: whether the dispatcher recognises the first
word. It reads like it must be the first question to ask, and both of the
divergent copies asked it, but it does not change a single answer -- an
unrecognised word that is not Python still belongs to the command layer, which
is the only one that can say "no such command", and a recognised word that is
bound in Python is still Python. Asking it only splits the rule into two
branches that then have to be kept identical by hand.

This module imports no Qt and no GUI, so a headless REPL can use the same rule
the widget does.
"""
from __future__ import annotations

import ast
import builtins
from collections.abc import Mapping
from typing import Any

__all__ = [
    "compiles_as_python",
    "is_incomplete_python",
    "name_exists_in_python",
    "is_command",
]


def is_incomplete_python(line: str) -> bool:
    """Whether *line* is the start of a Python block that is not finished yet.

    Parameters
    ----------
    line : str
        The buffer as typed so far.

    Returns
    -------
    bool
        True for ``for i in range(3):`` and other openings that need more
        input.

    Notes
    -----
    A prompt where Enter can mean "continue the block" has to ask this *before*
    the command-or-Python question, because an unfinished block does not
    compile and would otherwise be mistaken for a command -- and once it is
    swallowed there is no way to type the body. A prompt that submits whole
    cells (the Qt console) never sees a partial block and does not need it.
    """
    import codeop

    try:
        return codeop.compile_command(line, "<input>", "exec") is None
    except SyntaxError:
        return False
    except (OverflowError, ValueError):
        return False


def compiles_as_python(line: str) -> bool:
    """Whether *line* is syntactically valid Python.

    Parameters
    ----------
    line : str
        A single input line.

    Returns
    -------
    bool
        True when the line compiles in either ``eval`` or ``exec`` mode. Only
        syntax is tested; nothing is executed and no name is resolved.
    """
    for mode in ("eval", "exec"):
        try:
            compile(line, "<input>", mode)
        except SyntaxError:
            continue
        else:
            return True
    return False


def name_exists_in_python(line: str, namespace: Mapping[str, Any] | None) -> bool:
    """Whether the leading name of *line* is bound.

    Parameters
    ----------
    line : str
        A line that compiles as Python.
    namespace : mapping or None
        The user namespace to check, searched before builtins.

    Returns
    -------
    bool
        True when Python has something of that name -- a variable, an import, a
        builtin -- so evaluating it is meaningful. False when it would only ever
        raise ``NameError``, in which case the command layer is what the user
        meant.

    Notes
    -----
    Only the **root** name is checked, so ``zoom`` and ``zoom.__doc__`` answer
    alike, and a user who binds ``ray = 5`` gets their variable back -- which is
    surprising only if you have both, and is the same precedence a shell gives a
    function over a program of the same name.
    """
    try:
        tree = ast.parse(line.strip(), mode="eval")
    except SyntaxError:
        return False

    node: Any = tree.body
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    if not isinstance(node, ast.Name):
        # A literal, an operator, a comprehension -- not a bare name, so it is
        # an expression and belongs to Python whatever the dispatcher claims.
        return True

    root = node.id
    if namespace is not None and root in namespace:
        return True
    return hasattr(builtins, root)


def is_command(
    line: str,
    has_dispatcher: bool = True,
    namespace: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether *line* belongs to the command layer rather than Python.

    Parameters
    ----------
    line : str
        The typed line.
    has_dispatcher : bool, optional
        Whether a command layer is attached at all. False routes everything to
        Python. The dispatcher's *vocabulary* is deliberately not consulted --
        see the module docstring for why it cannot change the answer.
    namespace : mapping, optional
        The user namespace, for the name check described in the module
        docstring.

    Returns
    -------
    bool
        True to route the line to the command dispatcher.
    """
    if not has_dispatcher or not line.strip():
        return False

    if compiles_as_python(line):
        return not name_exists_in_python(line, namespace)

    # Does not compile. Claimed or not, it is not Python -- an unclaimed
    # non-compiling word at a command prompt is a mistyped command far more
    # often than a mistyped expression, and the command layer can say so by
    # name. `NameError: name 'splitt_chains' is not defined` is a true
    # statement about the wrong language.
    return True
