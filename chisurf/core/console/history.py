"""Persistent console input history.

Stored as one plain UTF-8 file rather than the SQLite database IPython uses.
That keeps it greppable and matches the convention ChiSurf already has for the
per-session ``session_file`` log -- and the two stay separate on purpose: the
session file is the macro provenance trail, this is what the Up arrow walks.
"""

from __future__ import annotations

import contextlib
import pathlib
import typing

__all__ = ["HistoryManager"]

#: Multi-line cells are stored on one line with the newlines escaped, so the
#: file stays one-entry-per-line and can be read with ``grep``.
_ESCAPES = ((chr(92), chr(92) * 2), ("\n", chr(92) + "n"))


def _encode(text: str) -> str:
    """Return *text* as a single storable line.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    for raw, escaped in _ESCAPES:
        text = text.replace(raw, escaped)
    return text


def _decode(line: str) -> str:
    """Return the cell stored as *line*.

    Parameters
    ----------
    line : str

    Returns
    -------
    str
    """
    out: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char == chr(92) and index + 1 < len(line):
            nxt = line[index + 1]
            if nxt == "n":
                out.append("\n")
                index += 2
                continue
            if nxt == chr(92):
                out.append(chr(92))
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


class HistoryManager:
    """Load, search and persist the console's input history.

    Parameters
    ----------
    path : pathlib.Path, optional
        History file. Defaults to ``chinsole_history.txt`` in the ChiSurf
        settings directory. Pass ``False`` to disable persistence entirely,
        which the tests use.
    max_entries : int, optional
        Entries kept on disk; the oldest are dropped.
    """

    def __init__(
        self,
        path: pathlib.Path | bool | None = None,
        max_entries: int = 5000,
    ) -> None:
        self.max_entries = max_entries
        self.entries: list[str] = []
        self.path = self._resolve_path(path)
        if self.path is not None:
            self.load()

    @staticmethod
    def _resolve_path(path: pathlib.Path | bool | None) -> pathlib.Path | None:
        """Return the history file to use.

        Parameters
        ----------
        path : pathlib.Path or bool or None

        Returns
        -------
        pathlib.Path or None
        """
        if path is False:
            return None
        if path is not None and path is not True:
            return pathlib.Path(path)
        try:
            import chisurf.core.settings

            return pathlib.Path(chisurf.core.settings.get_path("settings")) / "chinsole_history.txt"
        except Exception:
            return pathlib.Path.home() / ".chisurf" / "chinsole_history.txt"

    def load(self) -> None:
        """Read the history file, tolerating its absence or corruption."""
        if self.path is None or not self.path.is_file():
            return
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self.entries = [_decode(line) for line in text.splitlines() if line.strip()]
        if len(self.entries) > self.max_entries:
            del self.entries[: -self.max_entries]

    def save(self) -> None:
        """Write the history file, tolerating an unwritable directory."""
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = "\n".join(_encode(entry) for entry in self.entries[-self.max_entries :])
            self.path.write_text(payload + "\n", encoding="utf-8")
        except OSError:
            pass

    def append(self, source: str) -> None:
        """Record *source*.

        Consecutive duplicates are collapsed, which is what makes Up usable
        after running the same command three times.

        Parameters
        ----------
        source : str
        """
        source = source.rstrip("\n")
        if not source.strip():
            return
        if self.entries and self.entries[-1] == source:
            return
        self.entries.append(source)
        if len(self.entries) > self.max_entries * 2:
            del self.entries[: -self.max_entries]

    def search_prefix(self, prefix: str, before: int | None = None) -> list[str]:
        """Return entries starting with *prefix*, most recent first.

        Parameters
        ----------
        prefix : str
        before : int, optional
            Only consider entries before this index.

        Returns
        -------
        list of str
        """
        window = self.entries[:before] if before is not None else self.entries
        if not prefix:
            return list(reversed(window))
        return [entry for entry in reversed(window) if entry.startswith(prefix)]

    def search_substring(self, needle: str, before: int | None = None) -> list[str]:
        """Return entries containing *needle*, most recent first.

        Parameters
        ----------
        needle : str
        before : int, optional

        Returns
        -------
        list of str
        """
        window = self.entries[:before] if before is not None else self.entries
        if not needle:
            return list(reversed(window))
        lowered = needle.lower()
        return [entry for entry in reversed(window) if lowered in entry.lower()]

    def range(self, spec: str) -> list[tuple[int, str]]:
        """Return the entries named by a ``%history`` range *spec*.

        Parameters
        ----------
        spec : str
            Space-separated items, each ``N``, ``N-M``, ``N:M`` or ``N:``.
            One-based, matching the ``In[n]`` numbering the user sees.

        Returns
        -------
        list of tuple
            ``(number, source)`` pairs.
        """
        if not spec.strip():
            return list(enumerate(self.entries, start=1))
        wanted: list[int] = []
        for item in spec.replace(",", " ").split():
            separator = "-" if "-" in item else (":" if ":" in item else None)
            if separator is None:
                with contextlib.suppress(ValueError):
                    wanted.append(int(item))
                continue
            start, _, stop = item.partition(separator)
            try:
                first = int(start) if start else 1
                last = int(stop) if stop else len(self.entries)
            except ValueError:
                continue
            wanted.extend(range(first, last + 1))
        return [
            (number, self.entries[number - 1])
            for number in wanted
            if 1 <= number <= len(self.entries)
        ]

    def __len__(self) -> int:
        """Return the number of entries.

        Returns
        -------
        int
        """
        return len(self.entries)

    def __iter__(self) -> typing.Iterator[str]:
        """Iterate over the entries, oldest first.

        Yields
        ------
        str
        """
        return iter(self.entries)
