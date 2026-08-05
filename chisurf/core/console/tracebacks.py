"""Format exceptions the way an interactive console should.

Two things separate this from :func:`traceback.print_exc`. First, the console's
own frames are trimmed: a user who typed ``1/0`` wants to see their line, not
six frames of ``shell.py``, ``interpreter.py`` and ``exec``. Second, the output
carries ANSI colour, so the same string is meaningful in the widget, in a
head-less test and in the session log.
"""

from __future__ import annotations

import linecache
import pathlib
import traceback
import typing

__all__ = ["format_exception", "format_syntax_error", "MODES"]

#: Directory whose frames are console plumbing rather than user code.
_CONSOLE_ROOT = pathlib.Path(__file__).resolve().parent

#: Accepted ``%xmode`` settings.
MODES = ("plain", "context", "verbose")

_RESET = "\x1b[0m"
_RED = "\x1b[31m"
_BRIGHT_RED = "\x1b[91m"
_GREEN = "\x1b[32m"
_CYAN = "\x1b[36m"
_BOLD = "\x1b[1m"
_FAINT = "\x1b[2m"


def _is_console_frame(filename: str) -> bool:
    """Return whether *filename* belongs to the console's own machinery.

    Parameters
    ----------
    filename : str

    Returns
    -------
    bool
    """
    if not filename:
        return False
    try:
        return pathlib.Path(filename).resolve().parent == _CONSOLE_ROOT
    except (OSError, ValueError):
        return False


def _trim(frames: list[traceback.FrameSummary]) -> list[traceback.FrameSummary]:
    """Drop the leading console frames from a traceback.

    Only *leading* frames are removed. A console frame further down is real --
    it means user code called back into the shell (a magic, say) and hiding it
    would misrepresent where the error happened.

    Parameters
    ----------
    frames : list of traceback.FrameSummary

    Returns
    -------
    list of traceback.FrameSummary
        Never empty: if every frame is console machinery the original list is
        returned, because showing plumbing beats showing nothing.
    """
    index = 0
    while index < len(frames) and _is_console_frame(frames[index].filename):
        index += 1
    trimmed = frames[index:]
    return trimmed or frames


def _format_frame(
        frame: traceback.FrameSummary,
        *,
        mode: str,
        colour: bool,
        last: bool,
) -> list[str]:
    """Render one traceback frame.

    Parameters
    ----------
    frame : traceback.FrameSummary
    mode : str
        One of :data:`MODES`.
    colour : bool
        Emit ANSI escapes.
    last : bool
        Whether this is the frame the exception was raised in; it gets a marker
        so the eye lands on it immediately.

    Returns
    -------
    list of str
        Lines, without trailing newlines.
    """
    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if colour else text

    marker = paint("--->", _BRIGHT_RED) if (last and mode != "plain") else "    "
    name = paint(frame.name, _CYAN)
    where = paint(f"{frame.filename}:{frame.lineno}", _GREEN)
    lines = [f"{marker} {where} in {name}"]

    if mode == "plain":
        lines = [f"  File \"{frame.filename}\", line {frame.lineno}, in {frame.name}"]

    source = frame.line
    if source:
        lines.append(f"        {source}")
        if last and getattr(frame, "colno", None) is not None:
            end = getattr(frame, "end_colno", None) or (frame.colno + 1)
            pad = " " * (8 + frame.colno - (len(frame.line) - len(frame.line.lstrip())))
            lines.append(paint(pad + "^" * max(1, end - frame.colno), _BRIGHT_RED))

    if mode == "verbose" and last:
        locals_ = getattr(frame, "locals", None)
        if locals_:
            lines.append(paint("        locals:", _FAINT))
            for key in sorted(locals_):
                value = locals_[key]
                if len(value) > 200:
                    value = value[:197] + "..."
                lines.append(paint(f"          {key} = {value}", _FAINT))
    return lines


def format_exception(
        exc: BaseException,
        *,
        mode: str = "context",
        colour: bool = True,
        chain: bool = True,
        limit: int | None = None,
) -> str:
    """Return a formatted traceback for *exc*.

    Parameters
    ----------
    exc : BaseException
    mode : str, optional
        One of :data:`MODES`. ``verbose`` adds the failing frame's locals.
    colour : bool, optional
        Emit ANSI escapes.
    chain : bool, optional
        Include ``__cause__`` / ``__context__`` chains.
    limit : int, optional
        Maximum number of frames.

    Returns
    -------
    str
        Ends with a newline.
    """
    if isinstance(exc, SyntaxError) and exc.lineno is not None and not exc.__traceback__:
        return format_syntax_error(exc, colour=colour)

    capture_locals = mode == "verbose"
    try:
        summary = traceback.TracebackException.from_exception(
            exc, limit=limit, capture_locals=capture_locals, lookup_lines=True,
        )
    except Exception:
        # capture_locals runs repr() on every local, and a broken __repr__ must
        # not replace the user's real error with ours.
        summary = traceback.TracebackException.from_exception(exc, limit=limit)

    return "".join(_render(summary, mode=mode, colour=colour, chain=chain))


def _render(
        summary: traceback.TracebackException,
        *,
        mode: str,
        colour: bool,
        chain: bool,
        seen: set[int] | None = None,
) -> typing.Iterator[str]:
    """Yield the lines for *summary*, recursing through the exception chain.

    Parameters
    ----------
    summary : traceback.TracebackException
    mode, colour, chain
        As :func:`format_exception`.
    seen : set of int, optional
        Guards against a cyclic ``__context__``.

    Yields
    ------
    str
    """
    seen = seen if seen is not None else set()
    if id(summary) in seen:
        return
    seen.add(id(summary))

    if chain:
        if summary.__cause__ is not None:
            yield from _render(summary.__cause__, mode=mode, colour=colour, chain=chain, seen=seen)
            yield "\nThe above exception was the direct cause of the following exception:\n\n"
        elif summary.__context__ is not None and not summary.__suppress_context__:
            yield from _render(summary.__context__, mode=mode, colour=colour, chain=chain, seen=seen)
            yield "\nDuring handling of the above exception, another exception occurred:\n\n"

    frames = _trim(list(summary.stack))
    if frames:
        header = "Traceback (most recent call last):"
        yield (f"{_FAINT}{header}{_RESET}\n" if colour else f"{header}\n")
        for index, frame in enumerate(frames):
            lines = _format_frame(
                frame, mode=mode, colour=colour, last=index == len(frames) - 1,
            )
            yield "\n".join(lines) + "\n"

    for line in summary.format_exception_only():
        yield (f"{_RED}{line.rstrip()}{_RESET}\n" if colour else line)


def format_syntax_error(exc: SyntaxError, *, colour: bool = True) -> str:
    """Return a formatted ``SyntaxError`` with its caret.

    Parameters
    ----------
    exc : SyntaxError
    colour : bool, optional

    Returns
    -------
    str
        Ends with a newline.
    """
    def paint(text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if colour else text

    where = f"{exc.filename or '<chinsole>'}:{exc.lineno or 0}"
    lines = [paint(f"  {where}", _GREEN)]

    text = exc.text
    if text is None and exc.filename and exc.lineno:
        text = linecache.getline(exc.filename, exc.lineno) or None
    if text:
        stripped = text.rstrip("\n")
        lines.append(f"    {stripped}")
        offset = (exc.offset or 1) - 1
        end = getattr(exc, "end_offset", None)
        width = max(1, (end - 1 - offset) if end and end - 1 > offset else 1)
        lines.append(paint("    " + " " * offset + "^" * width, _BRIGHT_RED))

    name = type(exc).__name__
    message = exc.msg or str(exc)
    lines.append(paint(f"{name}: {message}", _RED))
    return "\n".join(lines) + "\n"
