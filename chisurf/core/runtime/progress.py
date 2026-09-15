"""Terminal progress bar for long-running headless computations.

Two places in the tree loop long enough to want a progress indicator: burst
variance analysis over a burst table, and the maximum-entropy decay solver over
its iterations. Both used ``tqdm``; a bar that redraws itself in place with a
carriage return is a few lines, so it lives here rather than in a dependency --
and, unlike the previous state, it is actually declared and always available
(``tqdm`` was imported by core code without being a declared dependency).

Nothing is printed unless the stream is a terminal, so headless runs, log files
and the ZMQ server stay clean.

Examples
--------
>>> total = 0
>>> for value in progress(range(3), desc="summing"):
...     total += value
>>> total
3
"""

from __future__ import annotations

import shutil
import sys
import time
import typing

__all__ = ["progress", "trange"]

#: Smallest interval between two redraws, in seconds.
_MIN_REDRAW_INTERVAL = 0.1


def _render(desc: str, done: int, total: int | None, elapsed: float, width: int) -> str:
    """Compose one progress line.

    Parameters
    ----------
    desc : str
        Label shown in front of the bar.
    done : int
        Number of completed items.
    total : int or None
        Expected number of items, or ``None`` when unknown.
    elapsed : float
        Seconds since the iteration started.
    width : int
        Terminal width in characters.

    Returns
    -------
    str
        The line to write, without a trailing newline.
    """
    prefix = f"{desc}: " if desc else ""
    rate = f" [{done / elapsed:.0f}/s]" if elapsed > 0 else ""
    if not total:
        return f"{prefix}{done}{rate}"
    fraction = min(1.0, done / total)
    suffix = f" {100 * fraction:3.0f}% {done}/{total}{rate}"
    bar_width = max(4, width - len(prefix) - len(suffix) - 3)
    filled = int(round(bar_width * fraction))
    return f"{prefix}|{'#' * filled}{'-' * (bar_width - filled)}|{suffix}"


def progress(
    iterable: typing.Iterable,
    total: int | None = None,
    desc: str = "",
    stream: typing.TextIO | None = None,
) -> typing.Iterator:
    """Iterate over *iterable*, drawing a progress bar on a terminal.

    Parameters
    ----------
    iterable : iterable
        The sequence to consume. Consumed lazily; generators are fine.
    total : int, optional
        Expected number of items. Taken from ``len(iterable)`` when omitted and
        available, otherwise only a running count is shown.
    desc : str, optional
        Label shown in front of the bar.
    stream : file-like, optional
        Where to draw. Defaults to :data:`sys.stderr`. Drawing is skipped
        entirely unless the stream is a terminal.

    Yields
    ------
    object
        The items of *iterable*, unchanged.
    """
    if total is None:
        try:
            total = len(iterable)  # type: ignore[arg-type]
        except TypeError:
            total = None

    out = sys.stderr if stream is None else stream
    try:
        show = bool(out) and out.isatty()
    except Exception:  # pragma: no cover - exotic stream objects
        show = False

    if not show:
        yield from iterable
        return

    width = shutil.get_terminal_size((80, 24)).columns
    started = time.monotonic()
    last_draw = 0.0
    done = 0
    try:
        for item in iterable:
            yield item
            done += 1
            now = time.monotonic()
            if now - last_draw >= _MIN_REDRAW_INTERVAL:
                last_draw = now
                out.write("\r" + _render(desc, done, total, now - started, width).ljust(width))
                out.flush()
    finally:
        out.write("\r" + _render(desc, done, total, time.monotonic() - started, width).ljust(width))
        out.write("\n")
        out.flush()


def trange(*args, desc: str = "", stream: typing.TextIO | None = None) -> typing.Iterator[int]:
    """Iterate over :func:`range` with a progress bar.

    Parameters
    ----------
    *args : int
        Arguments forwarded to :func:`range`.
    desc : str, optional
        Label shown in front of the bar.
    stream : file-like, optional
        Where to draw; see :func:`progress`.

    Yields
    ------
    int
        The values of the range.
    """
    return progress(range(*args), desc=desc, stream=stream)
