"""A terminal screen model: ANSI bytes in, a grid of coloured runs out.

The ChiSurf console already parses ANSI escapes for its scrollback
(:mod:`chisurf.core.console.ansi`); a terminal needs the same parsing pushed
into a *grid*: programs address the cursor (``ESC [y;xH``), overwrite lines in
place, scroll regions, insert and delete cells, and switch to an alternate
screen for full-screen interfaces. This module is that grid, written against
the console parser's event vocabulary so colour handling (SGR state across
chunks, xterm-256 and true-colour, partial escapes held back) is the same
tested implementation.

What is modelled
----------------
* printing with last-column deferred wrap, as a vt100 does;
* ``BS`` / ``CR`` / ``TAB`` (8-column stops) / ``BEL`` (a flag);
* cursor addressing (``CUP`` ``H``/``f``, ``G`` ``d``, and the relative moves
  ``A`` ``B`` ``C`` ``D`` ``F``);
* erasing (``EL`` ``K``, ``ED`` ``J``, ``ECH`` ``X``) and the cell and line
  edits ``ICH @`` / ``DCH P`` / ``IL L`` / ``DL M``;
* scrolling at the bottom edge, inside a scrolling region (``DECSTBM r``),
  the explicit scrolls ``SU S`` / ``SD T`` (``SD`` pulls back from the
  scrollback when the region is the whole screen, as tmux's history does), and
  scrollback;
* the alternate screen (``?1049h`` / ``?1049l``): its own grid that never
  touches the scrollback, and the cursor visibility mode (``?25``).

Everything else (OSC titles, charset shifts, keypad modes) is dropped, as the
console parser does. The model draws nothing and imports nothing from emtk.
"""

from __future__ import annotations

import dataclasses
from typing import Iterator

from chisurf.core.console.ansi import (
    AnsiParser,
    Backspace,
    CarriageReturn,
    EraseDisplay,
    EraseLine,
    SgrState,
    Text,
)

__all__ = ["Run", "TerminalScreen"]

_TAB_STOP = 8
_DEFAULT = SgrState()


@dataclasses.dataclass(frozen=True)
class Run:
    """One run of cells sharing an :class:`SgrState`, at a column of its line.

    Attributes
    ----------
    start : int
        The run's first column.
    text : str
        The run's characters.
    state : SgrState
        Their attributes.
    """

    start: int
    text: str
    state: SgrState


# -- events beyond the console parser's vocabulary -------------------------


@dataclasses.dataclass(frozen=True)
class _CursorTo:
    row: int | None
    col: int | None


@dataclasses.dataclass(frozen=True)
class _Move:
    drow: int
    dcol: int


@dataclasses.dataclass(frozen=True)
class _InsertLines:
    count: int


@dataclasses.dataclass(frozen=True)
class _DeleteLines:
    count: int


@dataclasses.dataclass(frozen=True)
class _InsertChars:
    count: int


@dataclasses.dataclass(frozen=True)
class _DeleteChars:
    count: int


@dataclasses.dataclass(frozen=True)
class _EraseChars:
    count: int


@dataclasses.dataclass(frozen=True)
class _Scroll:
    count: int


@dataclasses.dataclass(frozen=True)
class _SetScrollRegion:
    top: int
    bottom: int | None


@dataclasses.dataclass(frozen=True)
class _PrivateMode:
    mode: int
    on: bool


def _n(params: list[int], index: int, default: int = 1) -> int:
    return params[index] if index < len(params) and params[index] else default


class _Parser(AnsiParser):
    """The console parser, extended with the cursor and cell events a grid needs."""

    def _apply_csi(self, params: str, final: str, events: list) -> None:
        if params.startswith("?"):
            # A private mode (``?25l`` hides the cursor, ``?1049h`` the alt screen):
            # the set/reset choice is the CSI's final byte, the numbers its params.
            on = final == "h"
            for part in params[1:].split(";"):
                if part.isdigit():
                    events.append(_PrivateMode(int(part), on))
            return
        if final == "m":  # colour: the console parser's own, tested SGR path
            super()._apply_csi(params, final, events)
            return
        numbers = [int(p) for p in params.split(";") if p.isdigit()]
        if final in ("H", "f"):
            events.append(_CursorTo(_n(numbers, 0) - 1, _n(numbers, 1) - 1))
        elif final == "A":
            events.append(_Move(-_n(numbers, 0), 0))
        elif final in ("B", "e"):
            events.append(_Move(_n(numbers, 0), 0))
        elif final == "C" or final == "a":
            events.append(_Move(0, _n(numbers, 0)))
        elif final == "D":
            events.append(_Move(0, -_n(numbers, 0)))
        elif final == "E":
            events.append(_CursorTo(None, 0))
            events.append(_Move(_n(numbers, 0), 0))
        elif final == "F":
            events.append(_CursorTo(None, 0))
            events.append(_Move(-_n(numbers, 0), 0))
        elif final == "G" or final == "`":
            events.append(_CursorTo(None, _n(numbers, 0) - 1))
        elif final == "d":
            events.append(_CursorTo(_n(numbers, 0) - 1, None))
        elif final == "J":
            events.append(EraseDisplay(numbers[0] if numbers else 0))
        elif final == "K":
            events.append(EraseLine(numbers[0] if numbers else 0))
        elif final == "L":
            events.append(_InsertLines(_n(numbers, 0)))
        elif final == "M":
            events.append(_DeleteLines(_n(numbers, 0)))
        elif final == "@":
            events.append(_InsertChars(_n(numbers, 0)))
        elif final == "P":
            events.append(_DeleteChars(_n(numbers, 0)))
        elif final == "X":
            events.append(_EraseChars(_n(numbers, 0)))
        elif final == "S":
            events.append(_Scroll(_n(numbers, 0)))
        elif final == "T":
            events.append(_Scroll(-_n(numbers, 0)))
        elif final == "r":
            events.append(
                _SetScrollRegion(
                    _n(numbers, 0), numbers[1] if len(numbers) > 1 and numbers[1] else None
                )
            )
        # Everything else (cursor save/restore, tab sets, ...) has no grid
        # equivalent here; dropping it keeps the text intact.


class TerminalScreen:
    """One terminal screen: *columns* × *rows* of cells, plus scrollback.

    Parameters
    ----------
    columns, rows : int
        The grid size (a PTY's ``winsize``).
    max_scrollback : int
        Lines kept above the grid; older ones are dropped.

    Lines are addressed *absolutely*: ``0 .. scrollback_lines - 1`` are the
    scrollback, the grid follows, so a selection survives scrolling. Each line
    is a list of ``(char, SgrState)`` cells up to its last written column; the
    tail is default-state blanks.
    """

    def __init__(self, columns: int = 80, rows: int = 24, max_scrollback: int = 2000) -> None:
        self.columns = max(2, int(columns))
        self.rows = max(2, int(rows))
        self.max_scrollback = max(0, int(max_scrollback))
        self._scrollback: list[list[tuple[str, SgrState]]] = []
        self._grid: list[list[tuple[str, SgrState]]] = [[] for _ in range(self.rows)]
        self._alt: list[list[tuple[str, SgrState]]] | None = None
        self._parser = _Parser()
        self._row = 0
        self._col = 0
        self._wrap_pending = False
        self._cursor_visible = True
        self._top = 0
        self._bottom = self.rows - 1
        self._bell = False
        #: Bumped by every feed, so a view can cache what it computed.
        self.revision = 0

    # ── state a view reads ────────────────────────────────────────────────

    @property
    def cursor(self) -> tuple[int, int]:
        """``(row, column)`` of the cursor in the grid."""
        return (self._row, self._col)

    @property
    def cursor_visible(self) -> bool:
        return self._cursor_visible

    @property
    def alt(self) -> bool:
        """Whether the alternate screen is active (a full-screen program)."""
        return self._alt is not None

    @property
    def bell(self) -> bool:
        """Whether BEL rang since the last read; reading clears it."""
        value, self._bell = self._bell, False
        return value

    @property
    def scrollback_lines(self) -> int:
        return len(self._scrollback)

    @property
    def total_lines(self) -> int:
        """Scrollback plus grid rows: the height of the absolute history."""
        return len(self._scrollback) + self.rows

    @property
    def max_scroll_offset(self) -> int:
        """How far up from the live view a viewport may scroll."""
        return len(self._scrollback)

    @property
    def _lines(self) -> list[list[tuple[str, SgrState]]]:
        return self._alt if self._alt is not None else self._grid

    # ── reading ───────────────────────────────────────────────────────────

    def _line_at(self, index: int) -> list[tuple[str, SgrState]] | None:
        back = len(self._scrollback)
        if index < back:
            return self._scrollback[index]
        if index - back < self.rows:
            return self._lines[index - back]
        return None

    def _cells(self, index: int) -> list[tuple[str, SgrState]]:
        """Line *index* padded to the width with default blanks (a copy)."""
        line = self._line_at(int(index))
        if line is None:
            return [(" ", _DEFAULT)] * self.columns
        return line + [(" ", _DEFAULT)] * max(0, self.columns - len(line))

    def line_text(self, index: int) -> str:
        """Line *index* as text, padded to the width, trailing blanks stripped."""
        return "".join(ch for ch, _state in self._cells(int(index))).rstrip()

    def line_runs(self, index: int) -> list[Run]:
        """Line *index* as runs: consecutive cells sharing a state."""
        line = self._line_at(int(index))
        if not line:
            return []
        runs: list[Run] = []
        start = 0
        for position, (ch, state) in enumerate(line):
            if position > start and state != line[start][1]:
                runs.append(Run(start, "".join(c for c, _s in line[start:position]), line[start][1]))
                start = position
        runs.append(Run(start, "".join(c for c, _s in line[start:]), line[start][1]))
        return runs

    def visible(self, offset: int = 0) -> list[tuple[int, str]]:
        """``[(absolute index, text)]`` of the *rows* live lines at *offset* up."""
        offset = max(0, min(int(offset), self.max_scroll_offset))
        first = len(self._scrollback) - offset
        return [(first + row, self.line_text(first + row)) for row in range(self.rows)]

    def text_range(self, start: tuple[int, int], end: tuple[int, int]) -> str:
        """The text from absolute ``(line, column)`` *start* to *end*, inclusive."""
        (line0, col0), (line1, col1) = start, end
        if (line0, col0) > (line1, col1):
            (line0, col0), (line1, col1) = (line1, col1), (line0, col0)
        parts = []
        for index in range(line0, min(line1, self.total_lines - 1) + 1):
            text = "".join(ch for ch, _state in self._cells(index))
            if index == line0 and index == line1:
                parts.append(text[col0 : col1 + 1])
            elif index == line0:
                parts.append(text[col0:])
            elif index == line1:
                parts.append(text[: col1 + 1])
            else:
                parts.append(text)
        return "\n".join(part.rstrip() for part in parts)

    # ── feeding ───────────────────────────────────────────────────────────

    def feed(self, text: str) -> None:
        """Apply *text* (decoded PTY output) to the screen."""
        for event in self._parser.feed(text):
            if isinstance(event, Text):
                self._print(event.text, event.state)
            elif isinstance(event, CarriageReturn):
                self._col = 0
                self._wrap_pending = False
            elif isinstance(event, Backspace):
                self._col = max(0, self._col - event.count)
                self._wrap_pending = False
            elif isinstance(event, EraseLine):
                self._erase_line(event.mode)
            elif isinstance(event, EraseDisplay):
                self._erase_display(event.mode)
            elif isinstance(event, _CursorTo):
                if event.row is not None:
                    self._row = self._clamp_row(event.row)
                if event.col is not None:
                    self._col = self._clamp_col(event.col)
                self._wrap_pending = False
            elif isinstance(event, _Move):
                self._row = self._clamp_row(self._row + event.drow)
                self._col = self._clamp_col(self._col + event.dcol)
                self._wrap_pending = False
            elif isinstance(event, _InsertLines):
                self._insert_lines(event.count)
            elif isinstance(event, _DeleteLines):
                self._delete_lines(event.count)
            elif isinstance(event, _InsertChars):
                self._insert_chars(event.count)
            elif isinstance(event, _DeleteChars):
                self._delete_chars(event.count)
            elif isinstance(event, _EraseChars):
                self._erase_chars(event.count)
            elif isinstance(event, _Scroll):
                self._scroll(event.count)
            elif isinstance(event, _SetScrollRegion):
                bottom = (self.rows - 1) if event.bottom is None else self._clamp_row(event.bottom - 1)
                self._top = min(self._clamp_row(event.top - 1), bottom)
                self._bottom = bottom
                self._row, self._col = 0, 0  # DECSTBM homes the cursor
                self._wrap_pending = False
            elif isinstance(event, _PrivateMode):
                self._private_mode(event.mode, event.on)
        self.revision += 1

    # ── printing ──────────────────────────────────────────────────────────

    def _print(self, text: str, state: SgrState) -> None:
        plain: list[str] = []
        for char in text:
            if char == "\n":
                if plain:
                    self._write_cells("".join(plain), state)
                    plain = []
                self._linefeed()
            elif char == "\t":
                if plain:
                    self._write_cells("".join(plain), state)
                    plain = []
                stop = (self._col // _TAB_STOP + 1) * _TAB_STOP
                self._write_cells(" " * (stop - self._col), state)
            elif char == "\x07":
                if plain:
                    self._write_cells("".join(plain), state)
                    plain = []
                self._bell = True
            elif ord(char) < 32 or char == "\x7f":
                continue  # controls a grid has no equivalent for
            else:
                plain.append(char)
        if plain:
            self._write_cells("".join(plain), state)

    def _write_cells(self, text: str, state: SgrState | None = None) -> None:
        state = state if state is not None else self._parser.state
        lines = self._lines
        index = 0
        while index < len(text):
            if self._wrap_pending:
                self._wrap_pending = False
                self._col = 0
                self._linefeed()
            line = lines[self._row]
            room = self.columns - self._col
            take = min(len(text) - index, room)
            need = self._col + take
            if len(line) < need:
                line.extend([(" ", _DEFAULT)] * (need - len(line)))
            for offset, char in enumerate(text[index : index + take]):
                line[self._col + offset] = (char, state)
            self._col += take
            index += take
            if self._col >= self.columns - 1 and take >= room:
                self._col = self.columns - 1
                self._wrap_pending = True

    def _linefeed(self) -> None:
        if self._row == self._bottom:
            self._scroll(1)
        elif self._row < self.rows - 1:
            self._row += 1

    # ── erasing and editing ───────────────────────────────────────────────

    def _blank_line(self) -> list[tuple[str, SgrState]]:
        return []

    def _erase_line(self, mode: int) -> None:
        line = self._lines[self._row]
        if mode == 0:
            del line[self._col :]
        elif mode == 1:
            line[:] = line[self._col :]
        else:
            self._lines[self._row] = []

    def _erase_display(self, mode: int) -> None:
        if mode == 2 or mode == 3:
            for row in range(self.rows):
                self._lines[row] = []
            self._col = 0
            return
        if mode == 0:
            self._erase_line(0)
            for row in range(self._row + 1, self.rows):
                self._lines[row] = []
        elif mode == 1:
            self._erase_line(1)
            for row in range(0, self._row):
                self._lines[row] = []

    def _insert_chars(self, count: int) -> None:
        line = self._lines[self._row]
        blanks = [(" ", _DEFAULT)] * min(count, self.columns - self._col)
        line[self._col : self._col] = blanks
        del line[self.columns :]

    def _delete_chars(self, count: int) -> None:
        line = self._lines[self._row]
        del line[self._col : self._col + min(count, self.columns - self._col)]

    def _erase_chars(self, count: int) -> None:
        line = self._lines[self._row]
        end = min(self._col + count, self.columns)
        for column in range(self._col, end):
            if column < len(line):
                line[column] = (" ", _DEFAULT)
            else:
                break

    def _insert_lines(self, count: int) -> None:
        if not self._top <= self._row <= self._bottom:
            return
        count = min(count, self._bottom - self._row + 1)
        lines = self._lines
        kept = lines[self._row : self._bottom + 1 - count]
        lines[self._row : self._bottom + 1] = [[] for _ in range(count)] + kept

    def _delete_lines(self, count: int) -> None:
        if not self._top <= self._row <= self._bottom:
            return
        count = min(count, self._bottom - self._row + 1)
        lines = self._lines
        kept = lines[self._row + count : self._bottom + 1]
        lines[self._row : self._bottom + 1] = kept + [[] for _ in range(count)]

    # ── scrolling ─────────────────────────────────────────────────────────

    def _scroll(self, count: int) -> None:
        """Scroll the region *count* lines (negative: down)."""
        if count > 0:
            self._scroll_up(count)
        elif count < 0:
            self._scroll_down(-count)

    def _scroll_up(self, count: int) -> None:
        top, bottom = self._top, self._bottom
        lines = self._lines
        count = min(count, bottom - top + 1)
        leaving = lines[top : top + count]
        if self._alt is None and top == 0:
            for line in leaving:
                self._scrollback.append(line)
            drop = len(self._scrollback) - self.max_scrollback
            if drop > 0:
                del self._scrollback[:drop]
        lines[top : bottom + 1] = lines[top + count : bottom + 1] + [[] for _ in range(count)]

    def _scroll_down(self, count: int) -> None:
        top, bottom = self._top, self._bottom
        lines = self._lines
        count = min(count, bottom - top + 1)
        back: list[list[tuple[str, SgrState]]] = []
        if self._alt is None and top == 0:
            take = min(count, len(self._scrollback))
            if take:
                back = self._scrollback[-take:]
                del self._scrollback[-take:]
        fresh = list(reversed(back)) + [[] for _ in range(count - len(back))]
        lines[top : bottom + 1] = fresh + lines[top : bottom + 1 - count]

    # ── modes, clamps, resize ─────────────────────────────────────────────

    def _private_mode(self, mode: int, on: bool) -> None:
        if mode == 1049 or mode == 47 or mode == 1047:
            if on and self._alt is None:
                self._alt = [[] for _ in range(self.rows)]
                self._row, self._col = 0, 0
                self._wrap_pending = False
                self._top, self._bottom = 0, self.rows - 1
            elif not on and self._alt is not None:
                self._alt = None
                self._row, self._col = 0, 0
                self._wrap_pending = False
                self._top, self._bottom = 0, self.rows - 1
        elif mode == 25:
            self._cursor_visible = on

    def _clamp_row(self, row: int) -> int:
        return max(0, min(int(row), self.rows - 1))

    def _clamp_col(self, col: int) -> int:
        return max(0, min(int(col), self.columns - 1))

    def resize(self, columns: int, rows: int) -> None:
        """Resize the grid; top lines that no longer fit go to the scrollback."""
        columns = max(2, int(columns))
        rows = max(2, int(rows))
        if columns == self.columns and rows == self.rows:
            return
        if self._alt is None:
            if rows < self.rows:
                lift = self.rows - rows
                lift = min(lift, self.rows - 1)  # keep at least one grid row
                for line in self._grid[:lift]:
                    self._scrollback.append(line)
                del self._grid[:lift]
            elif rows > self.rows:
                self._grid.extend([[] for _ in range(rows - self.rows)])
            drop = len(self._scrollback) - self.max_scrollback
            if drop > 0:
                del self._scrollback[:drop]
        else:
            if rows < self.rows:
                del self._alt[rows - self.rows :]
            elif rows > self.rows:
                self._alt.extend([[] for _ in range(rows - self.rows)])
        self.columns, self.rows = columns, rows
        self._row = self._clamp_row(self._row)
        self._col = self._clamp_col(self._col)
        self._top = self._clamp_row(self._top)
        self._bottom = self._clamp_row(self._bottom)
        self._wrap_pending = False
        self.revision += 1
