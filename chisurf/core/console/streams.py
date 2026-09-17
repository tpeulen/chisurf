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


class OutputStream(io.TextIOBase):
    """A write-only text stream that hands everything to a callback.

    Parameters
    ----------
    name : str
        ``"stdout"`` or ``"stderr"``; passed to *sink* so one sink can colour
        the two differently.
    sink : callable
        ``sink(name, text)``. Called from whatever thread wrote, so the sink is
        responsible for thread-safety --
        :class:`chisurf.gui.chinsole.bridge.OutputPump` is.
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
        super().__init__()
        self.name = name
        self._sink = sink
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        """str: Nominal encoding of the stream."""
        return self._encoding

    def writable(self) -> bool:
        """Return ``True``; the stream accepts writes."""
        return True

    def readable(self) -> bool:
        """Return ``False``; the stream cannot be read."""
        return False

    def seekable(self) -> bool:
        """Return ``False``; the stream cannot be sought."""
        return False

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

    def write(self, text: str) -> int:
        """Send *text* to the sink.

        Parameters
        ----------
        text : str

        Returns
        -------
        int
            Number of characters accepted.
        """
        if not isinstance(text, str):
            text = str(text)
        if text:
            self._sink(self.name, text)
        return len(text)

    def writelines(self, lines: typing.Iterable[str]) -> None:
        """Write each of *lines*.

        Parameters
        ----------
        lines : iterable of str
        """
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        """Do nothing; writes are already handed on."""


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

    def write(self, text: str) -> int:
        """Capture and forward *text*.

        Parameters
        ----------
        text : str

        Returns
        -------
        int
        """
        if not isinstance(text, str):
            text = str(text)
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


class InputStream(io.TextIOBase):
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
        super().__init__()
        self.name = "stdin"
        self._reader = reader

    def readable(self) -> bool:
        """Return ``True``; the stream can be read."""
        return True

    def writable(self) -> bool:
        """Return ``False``; the stream cannot be written."""
        return False

    def seekable(self) -> bool:
        """Return ``False``; the stream cannot be sought."""
        return False

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
        raise io.UnsupportedOperation("chinsole streams have no file descriptor")

    def readline(self, size: int = -1) -> str:
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

    def read(self, size: int = -1) -> str:
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
