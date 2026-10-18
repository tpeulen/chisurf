"""File-like objects that route a running cell's I/O to the console.

``sys.stdout`` and ``sys.stderr`` are replaced while a cell runs so that print
output reaches the widget instead of the terminal, and ``sys.stdin`` is replaced
so that :func:`input` and :mod:`getpass` work at the prompt rather than
dead-locking on a console that has no terminal behind it.
"""

from __future__ import annotations

import io
import typing

__all__ = ["OutputStream", "InputStream", "CapturingStream"]


class _ConsoleTextIO(typing.TextIO):
    """The text-stream behaviour both console streams share.

    A :class:`typing.TextIO`, which is what ``sys.stdout``/``sys.stdin`` and
    :class:`pdb.Pdb` are typed against. These used to derive from
    :class:`io.TextIOBase`, whose stubs inherit the *bytes* signatures of
    ``IOBase`` for ``readline``/``writelines``, so no correct text override
    type-checked and pdb would not accept the streams at all.

    Everything a console cannot do -- seek, truncate, a byte buffer, a file
    descriptor -- raises :exc:`io.UnsupportedOperation`, as an unseekable
    :class:`io.TextIOBase` does.
    """

    def __init__(self, name: str, *, encoding: str = "utf-8") -> None:
        self._name = name
        self._encoding = encoding
        self._closed = False

    # -- identity -----------------------------------------------------------
    @property
    def name(self) -> str:
        """str: ``"stdout"``, ``"stderr"`` or ``"stdin"``."""
        return self._name

    @property
    def mode(self) -> str:
        """str: ``"w"`` for a writable stream, ``"r"`` otherwise."""
        return "w" if self.writable() else "r"

    @property
    def encoding(self) -> str:
        """str: Nominal encoding of the stream; nothing is actually encoded."""
        return self._encoding

    @property
    def errors(self) -> str | None:
        """None: no encoding happens, so there is no error policy."""
        return None

    @property
    def line_buffering(self) -> int:
        """int: ``False``; writes are handed on immediately."""
        return False

    @property
    def newlines(self) -> None:
        """None: no newline translation is done."""
        return None

    @property
    def buffer(self) -> typing.BinaryIO:
        """Raise; a console stream has no byte layer underneath."""
        raise io.UnsupportedOperation("chinsole streams have no byte buffer")

    # -- state ----------------------------------------------------------------
    @property
    def closed(self) -> bool:
        """bool: Whether :meth:`close` was called."""
        return self._closed

    def close(self) -> None:
        """Mark the stream closed."""
        self._closed = True

    def __enter__(self) -> _ConsoleTextIO:
        """Return the stream."""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Close the stream."""
        self.close()

    def isatty(self) -> bool:
        """Return ``False``; there is no terminal behind the console."""
        return False

    def fileno(self) -> int:
        """Raise; a console stream has no file descriptor.

        Raises
        ------
        io.UnsupportedOperation
            Always.
        """
        raise io.UnsupportedOperation(
            "chinsole streams have no file descriptor; pass a pipe to subprocess"
        )

    def flush(self) -> None:
        """Do nothing; writes are already handed on."""

    def seekable(self) -> bool:
        """Return ``False``; the stream cannot be sought."""
        return False

    def seek(self, offset: int, whence: int = 0, /) -> int:
        """Raise; the stream cannot be sought."""
        raise io.UnsupportedOperation("chinsole streams cannot seek")

    def tell(self) -> int:
        """Raise; the stream has no position."""
        raise io.UnsupportedOperation("chinsole streams have no position")

    def truncate(self, size: int | None = None, /) -> int:
        """Raise; the stream cannot be truncated."""
        raise io.UnsupportedOperation("chinsole streams cannot be truncated")

    # -- the halves a subclass provides ---------------------------------------
    def readable(self) -> bool:
        """Return ``False``; :class:`InputStream` overrides."""
        return False

    def writable(self) -> bool:
        """Return ``False``; :class:`OutputStream` overrides."""
        return False

    def read(self, size: int = -1, /) -> str:
        """Raise; :class:`InputStream` overrides."""
        raise io.UnsupportedOperation("not readable")

    def readline(self, size: int = -1, /) -> str:
        """Raise; :class:`InputStream` overrides."""
        raise io.UnsupportedOperation("not readable")

    def readlines(self, hint: int = -1, /) -> list[str]:
        """Read lines until end of input (or until *hint* characters)."""
        lines: list[str] = []
        total = 0
        while True:
            line = self.readline()
            if not line:
                return lines
            lines.append(line)
            total += len(line)
            if 0 < hint <= total:
                return lines

    def __iter__(self) -> typing.Iterator[str]:
        """Iterate over lines."""
        return self

    def __next__(self) -> str:
        """Return the next line; stop at end of input."""
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def write(self, s: str, /) -> int:
        """Raise; :class:`OutputStream` overrides."""
        raise io.UnsupportedOperation("not writable")

    def writelines(self, lines: typing.Iterable[str], /) -> None:
        """Write each of *lines*."""
        for line in lines:
            self.write(line)


class OutputStream(_ConsoleTextIO):
    """A write-only text stream that hands everything to a callback.

    Parameters
    ----------
    name : str
        ``"stdout"`` or ``"stderr"``; passed to *sink* so one sink can colour
        the two differently.
    sink : callable
        ``sink(name, text)``. Called from whatever thread wrote, so the sink is
        responsible for thread-safety --
        the view (:mod:`chisurf.emtk.console`) is.
    encoding : str, optional
        Reported by :attr:`encoding`; nothing is actually encoded.

    Notes
    -----
    :meth:`fileno` deliberately raises. A console stream has no file
    descriptor, and the failure mode of pretending otherwise is nasty:
    :mod:`subprocess` would inherit the *real* process stdout and a child's
    output would go to the terminal ChiSurf was launched from -- invisibly, if
    it was launched from a desktop icon. Callers that need a descriptor must
    use a pipe, which is what ``!command`` does.

    :meth:`isatty` returns ``False``, matching a Jupyter kernel. The widget
    exports ``COLUMNS``/``LINES`` instead, so :func:`shutil.get_terminal_size`
    and pandas' display width still produce sensible values.
    """

    def __init__(
        self,
        name: str,
        sink: typing.Callable[[str, str], None],
        *,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__(name, encoding=encoding)
        self._sink = sink

    def writable(self) -> bool:
        """Return ``True``; the stream accepts writes."""
        return True

    def write(self, s: str, /) -> int:
        """Send *s* to the sink.

        Parameters
        ----------
        s : str

        Returns
        -------
        int
            Number of characters accepted.
        """
        text = s if isinstance(s, str) else str(s)
        if text:
            self._sink(self.name, text)
        return len(text)


class CapturingStream(OutputStream):
    """An :class:`OutputStream` that also keeps everything written to it.

    Used by ``%%capture`` and by anything that needs the text as well as the
    display, such as ``!command`` substitution.

    Parameters
    ----------
    name : str
    sink : callable, optional
        When ``None``, output is captured only and never displayed.
    """

    def __init__(
        self,
        name: str,
        sink: typing.Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(name, sink or (lambda _n, _t: None))
        self._buffer: list[str] = []

    def write(self, s: str, /) -> int:
        """Capture and forward *s*.

        Parameters
        ----------
        s : str

        Returns
        -------
        int
        """
        text = s if isinstance(s, str) else str(s)
        if text:
            self._buffer.append(text)
        return super().write(text)

    def getvalue(self) -> str:
        """Return everything written so far.

        Returns
        -------
        str
        """
        return "".join(self._buffer)


class InputStream(_ConsoleTextIO):
    """A read-only text stream that asks the console for a line.

    Parameters
    ----------
    reader : callable
        ``reader(prompt, password) -> str``. Expected to block until the user
        presses Enter while keeping the GUI responsive; the widget does that
        with a nested event loop. Must return the line *without* a trailing
        newline, or raise :exc:`EOFError` if the console went away.

    Notes
    -----
    This one seam is what gives the console :func:`input`, :mod:`getpass` and
    -- because :class:`pdb.Pdb` takes ``stdin``/``stdout`` -- a working
    post-mortem debugger, none of which needs IPython.
    """

    def __init__(self, reader: typing.Callable[[str, bool], str]) -> None:
        super().__init__("stdin")
        self._reader = reader

    def readable(self) -> bool:
        """Return ``True``; the stream can be read."""
        return True

    def readline(self, size: int | None = -1, /) -> str:
        """Return one line typed at the console, newline included.

        Parameters
        ----------
        size : int, optional
            Truncates the returned line when non-negative.

        Returns
        -------
        str
            Empty at end of input, as a file object signals EOF.
        """
        try:
            line = self._reader("", False)
        except EOFError:
            return ""
        if not line.endswith("\n"):
            line += "\n"
        return line if size is None or size < 0 else line[:size]

    def read(self, size: int | None = -1, /) -> str:
        """Read *size* characters, or until end of input.

        Parameters
        ----------
        size : int, optional

        Returns
        -------
        str
        """
        if size is not None and size >= 0:
            return self.readline(size)
        chunks: list[str] = []
        while True:
            line = self.readline()
            if not line:
                return "".join(chunks)
            chunks.append(line)
