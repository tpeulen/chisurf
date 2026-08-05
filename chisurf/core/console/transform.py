"""Turn what the user typed into Python, and decide when they are finished.

Two jobs live here, and both are line-oriented rather than cell-oriented on
purpose. Transformation rewrites the interactive escapes (``%magic``, ``!shell``,
``obj?``) into ordinary calls on a shell object, per line, preserving
indentation -- so ``%time f()`` works inside a ``for`` body and magics compose
with real Python instead of being a separate grammar that only works at column
zero.

The second job, :func:`check_complete`, is what makes Enter feel right: it
answers whether a partially typed cell is finished, and if not, how far the next
line should be indented.
"""

from __future__ import annotations

import codeop
import re
import tokenize
import typing

__all__ = [
    "ESC_MAGIC",
    "ESC_CELL_MAGIC",
    "ESC_SHELL",
    "SHELL_OBJECT",
    "transform_cell",
    "transform_line",
    "split_cell_magic",
    "check_complete",
    "indent_hint",
    "strip_prompts",
]

ESC_MAGIC = "%"
ESC_CELL_MAGIC = "%%"
ESC_SHELL = "!"
ESC_SHELL_CAP = "!!"
ESC_HELP = "?"

#: Name the rewritten escapes call through. Bound in the user namespace by
#: :class:`~chisurf.core.console.shell.Shell`. A dunder-ish name rather than
#: ``get_ipython()`` so a rewritten line still works when pasted into a file run
#: by ``%run``, and so ``%who`` can hide it by name.
SHELL_OBJECT = "__chinsole__"

#: Statements that open a block. ``match`` and ``case`` are soft keywords and
#: are handled by the trailing-colon rule instead, since ``match = 3`` is legal.
_BLOCK_OPENERS = (
    "if", "elif", "else", "for", "while", "def", "class", "with",
    "try", "except", "finally", "async",
)

#: Statements after which the next line should dedent.
_DEDENT_AFTER = ("pass", "break", "continue", "return", "raise")

#: SyntaxError messages that mean "keep typing" rather than "this is wrong".
_INCOMPLETE_MESSAGES = (
    "unexpected EOF",
    "was never closed",
    "expected an indented block",
    "unterminated triple-quoted string",
    "incomplete input",
)

_ASSIGN_MAGIC_RE = re.compile(
    r"^(?P<indent>\s*)(?P<lhs>[A-Za-z_][\w.\[\]'\", ]*=\s*)?"
    r"(?P<esc>%{1,2}|!{1,2})(?P<rest>.*)$"
)
_HELP_RE = re.compile(r"^(?P<indent>\s*)(?P<expr>[A-Za-z_][\w.]*(?:\(\))?)(?P<marks>\?{1,2})\s*$")
_HELP_PREFIX_RE = re.compile(r"^(?P<indent>\s*)(?P<marks>\?{1,2})(?P<expr>[A-Za-z_][\w.]*)\s*$")
_PROMPT_RE = re.compile(r"^(?:>>> |\.\.\. |In \[\d+\]: |\s{4,}\.\.\.: |Out\[\d+\]: )")


def _q(text: str) -> str:
    """Return *text* as a Python string literal.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    return repr(text)


def split_cell_magic(raw: str) -> tuple[str, str, str] | None:
    """Split a ``%%name line`` / body cell magic.

    Parameters
    ----------
    raw : str
        The whole cell.

    Returns
    -------
    tuple of str or None
        ``(name, line, body)``, or ``None`` when *raw* is not a cell magic.
    """
    if not raw.startswith(ESC_CELL_MAGIC):
        return None
    head, _, body = raw.partition("\n")
    head = head[len(ESC_CELL_MAGIC):]
    name, _, line = head.partition(" ")
    name = name.strip()
    if not name.isidentifier():
        return None
    return name, line.strip(), body


def transform_line(line: str, *, magic_names: typing.Container[str] = ()) -> str:
    """Rewrite one line's interactive escapes into plain Python.

    Parameters
    ----------
    line : str
        A single physical line, without its newline.
    magic_names : container of str, optional
        Known line-magic names. Only consulted to decide whether a bare word is
        a magic; an unknown ``%name`` is still rewritten so the shell can report
        it properly rather than raising a ``SyntaxError``.

    Returns
    -------
    str
        The line, rewritten if it used an escape, otherwise unchanged.
    """
    match = _HELP_RE.match(line) or _HELP_PREFIX_RE.match(line)
    if match:
        expr = match.group("expr")
        detail = len(match.group("marks")) - 1
        return f"{match.group('indent')}{SHELL_OBJECT}.pinfo({_q(expr)}, detail_level={detail})"

    match = _ASSIGN_MAGIC_RE.match(line)
    if not match:
        return line

    indent = match.group("indent")
    lhs = match.group("lhs") or ""
    esc = match.group("esc")
    rest = match.group("rest")

    if esc == ESC_SHELL_CAP:
        return f"{indent}{lhs}{SHELL_OBJECT}.getoutput({_q(rest.strip())})"
    if esc == ESC_SHELL:
        call = "getoutput" if lhs else "system"
        return f"{indent}{lhs}{SHELL_OBJECT}.{call}({_q(rest.strip())})"
    if esc == ESC_CELL_MAGIC:
        # A ``%%`` that reached line transformation is not at the head of a
        # cell, so it cannot be a cell magic. Treat it as a line magic rather
        # than emitting something that will not compile.
        esc = ESC_MAGIC

    name, _, args = rest.partition(" ")
    name = name.strip()
    if not name:
        return line
    return f"{indent}{lhs}{SHELL_OBJECT}.run_line_magic({_q(name)}, {_q(args.strip())})"


def transform_cell(raw: str, *, magic_names: typing.Container[str] = ()) -> str:
    """Rewrite a whole cell's interactive escapes into plain Python.

    Parameters
    ----------
    raw : str
        Everything the user typed.
    magic_names : container of str, optional
        Known line-magic names.

    Returns
    -------
    str
        Executable Python. A cell that used no escape comes back unchanged.
    """
    if not raw.strip():
        return raw

    cell = split_cell_magic(raw)
    if cell is not None:
        name, line, body = cell
        return (
            f"{SHELL_OBJECT}.run_cell_magic({_q(name)}, {_q(line)}, {_q(body)})"
        )

    lines = raw.splitlines()
    out = [transform_line(line, magic_names=magic_names) for line in lines]
    result = "\n".join(out)
    if raw.endswith("\n"):
        result += "\n"
    return result


def strip_prompts(text: str) -> str:
    """Remove interpreter prompts from pasted text.

    Pasting a snippet copied out of a doctest, a README or another console is
    common enough that failing on it reads as the console being broken.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
        *text* unchanged when no line carried a prompt, so ordinary pastes are
        never altered.
    """
    lines = text.splitlines()
    if not any(_PROMPT_RE.match(line) for line in lines):
        return text
    kept = []
    for line in lines:
        match = _PROMPT_RE.match(line)
        if match is None:
            # Continuation of an ``Out[..]`` block, or plain output: drop it,
            # since it was never input.
            if kept and not line.strip():
                kept.append("")
            continue
        if line.startswith("Out["):
            continue
        kept.append(line[match.end():])
    return "\n".join(kept)


def _last_logical_line(source: str) -> str:
    """Return the last non-blank line of *source*.

    Parameters
    ----------
    source : str

    Returns
    -------
    str
        Empty when *source* has no non-blank line.
    """
    for line in reversed(source.splitlines()):
        if line.strip():
            return line
    return ""


def indent_hint(source: str) -> str:
    """Return the whitespace the next line of *source* should start with.

    Parameters
    ----------
    source : str
        The cell typed so far.

    Returns
    -------
    str
        A run of spaces, possibly empty.
    """
    line = _last_logical_line(source)
    if not line:
        return ""
    indent = len(line) - len(line.lstrip())
    stripped = line.strip()
    # A trailing colon opens a block -- but only when it really is trailing,
    # not when it closes a dict literal or an annotation on a continued line.
    code = stripped.split("#", 1)[0].rstrip()
    if code.endswith(":"):
        indent += 4
    elif stripped.split(" ", 1)[0].rstrip(":") in _DEDENT_AFTER:
        indent -= 4
    return " " * max(indent, 0)


def _bracket_state(source: str) -> str | None:
    """Return ``'incomplete'`` when *source* has an unclosed bracket or string.

    Parameters
    ----------
    source : str

    Returns
    -------
    str or None
        ``'incomplete'``, or ``None`` when tokenisation reached the end
        cleanly or failed for a reason that is a genuine syntax error.
    """
    import io as _io

    try:
        for _ in tokenize.generate_tokens(_io.StringIO(source).readline):
            pass
    except tokenize.TokenError:
        # Raised for an unterminated bracket or triple-quoted string: the user
        # is still typing.
        return "incomplete"
    except IndentationError:
        return None
    except SyntaxError:
        return None
    return None


def check_complete(source: str) -> tuple[str, str]:
    """Decide whether *source* is a finished cell.

    Parameters
    ----------
    source : str
        Everything typed so far.

    Returns
    -------
    tuple of str
        ``(status, indent)`` where *status* is ``'complete'``, ``'incomplete'``
        or ``'invalid'``, and *indent* is the whitespace to prefill the next
        line with when incomplete.

    Notes
    -----
    :func:`codeop.compile_command` alone is not enough, and the gap is exactly
    what separates a console that feels right from one that does not. It
    accepts ``for i in range(3):\\n    pass`` as complete the moment the body
    has one statement, so pressing Enter after the first body line would
    execute the loop instead of letting you write a second line. The
    compound-statement rule below is what both IPython and qtconsole add on
    top, and it is why a block only runs once you leave a blank line.
    """
    if not source.strip():
        return "complete", ""

    normalised = source.rstrip() + "\n"

    if _bracket_state(source) == "incomplete":
        return "incomplete", indent_hint(source)

    try:
        compiled = codeop.compile_command(normalised, "<chinsole>", "exec")
    except (SyntaxError, OverflowError, ValueError) as exc:
        message = str(exc)
        if any(token in message for token in _INCOMPLETE_MESSAGES):
            return "incomplete", indent_hint(source)
        return "invalid", ""

    if compiled is None:
        return "incomplete", indent_hint(source)

    lines = source.splitlines()
    first = lines[0].strip() if lines else ""
    opener = first.split(" ", 1)[0].rstrip(":")
    is_block = opener in _BLOCK_OPENERS or first.startswith("@")

    if is_block or len(lines) > 1:
        last = lines[-1] if lines else ""
        # A blank final line, or one at column zero that is not itself an
        # opener, ends the block. Anything still indented means the user is
        # mid-body and Enter should give them another line.
        if last.strip() and (last[:1].isspace() or last.rstrip().endswith(":")):
            return "incomplete", indent_hint(source)

    return "complete", ""
