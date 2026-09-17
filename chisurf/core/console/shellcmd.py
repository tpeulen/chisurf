"""The ``!command`` escape.

Output is streamed through a reader thread rather than collected at the end, so
a long-running command scrolls as it goes instead of appearing all at once when
it finishes. The console's own streams have no file descriptor -- deliberately,
see :class:`~chisurf.core.console.streams.OutputStream` -- so a pipe is used and
the thread pumps it across.
"""

from __future__ import annotations

import os
import string
import subprocess
import threading
import typing

__all__ = ["SList", "run_streaming", "capture", "expand_variables"]


class SList(list):
    """A list of output lines with the conveniences a shell user expects."""

    @property
    def n(self) -> str:
        """str: The lines joined with newlines."""
        return "\n".join(self)

    @property
    def s(self) -> str:
        """str: The lines joined with spaces, ready to pass to another command."""
        return " ".join(line.strip() for line in self)

    @property
    def p(self) -> list:
        """list: The lines as :class:`pathlib.Path` objects."""
        import pathlib

        return [pathlib.Path(line) for line in self]

    def grep(self, pattern: str, prune: bool = False) -> SList:
        """Return the lines matching *pattern*.

        Parameters
        ----------
        pattern : str
            Regular expression.
        prune : bool, optional
            Return the lines that do *not* match.

        Returns
        -------
        SList
        """
        import re

        compiled = re.compile(pattern)
        return SList(line for line in self if bool(compiled.search(line)) is not prune)

    def fields(self, *indices: int) -> SList:
        """Return whitespace-separated fields of each line.

        Parameters
        ----------
        *indices : int
            Field positions; all fields when omitted.

        Returns
        -------
        SList
        """
        out = SList()
        for line in self:
            parts = line.split()
            if not indices:
                out.append(" ".join(parts))
                continue
            try:
                out.append(" ".join(parts[i] for i in indices))
            except IndexError:
                out.append("")
        return out


class _Interpolator(string.Formatter):
    """Formatter that leaves an unknown ``{name}`` alone."""

    def get_value(self, key, args, kwargs):
        """Return the value for *key*, or the braces back when unknown.

        Parameters
        ----------
        key : str or int
        args : tuple
        kwargs : dict

        Returns
        -------
        object
        """
        try:
            return super().get_value(key, args, kwargs)
        except (KeyError, IndexError):
            return "{" + str(key) + "}"


def expand_variables(cmd: str, namespace: typing.Mapping[str, typing.Any]) -> str:
    """Interpolate ``{name}`` and ``$name`` from *namespace* into *cmd*.

    Parameters
    ----------
    cmd : str
    namespace : mapping

    Returns
    -------
    str
        *cmd* unchanged if interpolation fails: a shell command containing a
        brace (a ``find -exec {} ;``, an awk program) is far more likely than a
        mistyped substitution, and mangling it would be worse than not trying.
    """
    result = cmd
    try:
        result = _Interpolator().vformat(result, (), dict(namespace))
    except Exception:
        return cmd

    # ``$name`` is expanded only for names that actually exist, so ordinary
    # shell variables ($HOME, $PATH) reach the shell untouched.
    out: list[str] = []
    index = 0
    while index < len(result):
        char = result[index]
        if char != "$" or index + 1 >= len(result):
            out.append(char)
            index += 1
            continue
        rest = result[index + 1 :]
        name = ""
        for candidate in rest:
            if candidate.isalnum() or candidate == "_":
                name += candidate
            else:
                break
        if name and name in namespace:
            out.append(str(namespace[name]))
            index += 1 + len(name)
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _popen(cmd: str) -> subprocess.Popen:
    """Start *cmd* in a shell with its output on a pipe.

    Parameters
    ----------
    cmd : str

    Returns
    -------
    subprocess.Popen
    """
    return subprocess.Popen(  # noqa: S602 - a shell escape is the feature
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        errors="replace",
        cwd=os.getcwd(),
    )


def run_streaming(shell: typing.Any, cmd: str) -> int:
    """Run *cmd*, streaming its output to *shell* as it arrives.

    Parameters
    ----------
    shell : Shell
    cmd : str

    Returns
    -------
    int
        The child's exit status, or ``-1`` if it could not be started.
    """
    try:
        process = _popen(cmd)
    except OSError as exc:
        shell.write_err(f"could not run command: {exc}\n")
        return -1

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            shell.write(line)

    thread = threading.Thread(target=pump, name="chinsole-shell", daemon=True)
    thread.start()
    try:
        status = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            status = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            status = process.wait()
        shell.write_err("\nKeyboardInterrupt\n")
    thread.join(timeout=2)
    return status


def capture(shell: typing.Any, cmd: str, *, split: bool = True):
    """Run *cmd* and return its output instead of displaying it.

    Parameters
    ----------
    shell : Shell
    cmd : str
    split : bool, optional
        Return an :class:`SList` of lines rather than one string.

    Returns
    -------
    SList or str
    """
    try:
        process = _popen(cmd)
    except OSError as exc:
        shell.write_err(f"could not run command: {exc}\n")
        return SList() if split else ""
    output, _ = process.communicate()
    output = output or ""
    if not split:
        return output
    return SList(output.splitlines())
