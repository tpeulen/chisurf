"""Parse ANSI terminal escapes into events a text widget can apply.

Tracebacks are formatted as ANSI-escaped text rather than as Qt formats, and
this module is why that works. Keeping the escape sequence as the interchange
means the identical bytes go to the widget, to a head-less test assertion and to
the session log -- and it means third-party output that already emits colour
(pytest, colorama, anything using ``rich``) renders correctly for free.

The cursor events matter as much as the colours. ``\\r`` followed by
``\\x1b[K`` is how every progress bar redraws its line in place; a console that
ignores them turns one ``tqdm`` bar into several thousand lines of scrollback.
"""

from __future__ import annotations

import dataclasses
import re
import typing

__all__ = [
    "SgrState",
    "Text",
    "CarriageReturn",
    "Backspace",
    "EraseLine",
    "EraseDisplay",
    "AnsiParser",
    "strip_ansi",
]

#: Matches a CSI sequence: ESC [ params intermediates final.
_CSI_RE = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
#: Matches escape sequences we recognise but do not act on (OSC, charset, ...).
_OTHER_ESC_RE = re.compile(r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][B0]|[=>]|.)")

#: Matches a *truncated* escape at the very end of a chunk -- a bare ESC, a CSI
#: whose final byte has not arrived, or an unterminated OSC. Such a tail must be
#: held back rather than parsed, because a stream is chunked wherever the writer
#: flushed and an escape is routinely split across two writes. Without this the
#: escape is emitted as literal text *and* the colour it carried is lost, which
#: looks like the parser mangling ordinary output.
_PARTIAL_ESC_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*|\][^\x07\x1b]*|[()]?)?\Z")

_XTERM_STEPS = (0, 95, 135, 175, 215, 255)


@dataclasses.dataclass(frozen=True)
class SgrState:
    """Text attributes selected by SGR escapes.

    Colours are either ``None`` (the theme's default), an ``int`` in ``0..15``
    naming an entry in the theme's ANSI palette, or a ``#rrggbb`` string for the
    256-colour and true-colour forms.
    """

    fg: int | str | None = None
    bg: int | str | None = None
    bold: bool = False
    faint: bool = False
    italic: bool = False
    underline: bool = False
    inverse: bool = False
    strike: bool = False

    def reset(self) -> SgrState:
        """Return a default state.

        Returns
        -------
        SgrState
        """
        return SgrState()


@dataclasses.dataclass(frozen=True)
class Text:
    """A run of characters sharing one :class:`SgrState`."""

    text: str
    state: SgrState


@dataclasses.dataclass(frozen=True)
class CarriageReturn:
    """Move the cursor to the start of the current line."""


@dataclasses.dataclass(frozen=True)
class Backspace:
    """Move the cursor back *count* characters."""

    count: int = 1


@dataclasses.dataclass(frozen=True)
class EraseLine:
    """Erase part of the current line.

    Attributes
    ----------
    mode : int
        ``0`` to the end of the line, ``1`` to the start, ``2`` the whole line.
    """

    mode: int = 0


@dataclasses.dataclass(frozen=True)
class EraseDisplay:
    """Erase part of the display.

    Attributes
    ----------
    mode : int
        ``2`` clears everything, which is what ``clear``/``cls`` emits.
    """

    mode: int = 0


AnsiEvent = typing.Union[Text, CarriageReturn, Backspace, EraseLine, EraseDisplay]


def _xterm256(index: int) -> str:
    """Return the ``#rrggbb`` colour for an xterm-256 palette *index*.

    Parameters
    ----------
    index : int
        ``0..255``. ``0..15`` are the base colours, ``16..231`` a 6x6x6 cube and
        ``232..255`` a greyscale ramp.

    Returns
    -------
    str
    """
    if index < 16:
        # Left to the theme; returned as an int by the caller instead.
        index = max(0, min(15, index))
        return f"#{index:02x}{index:02x}{index:02x}"
    if index < 232:
        index -= 16
        r = _XTERM_STEPS[(index // 36) % 6]
        g = _XTERM_STEPS[(index // 6) % 6]
        b = _XTERM_STEPS[index % 6]
        return f"#{r:02x}{g:02x}{b:02x}"
    grey = 8 + (index - 232) * 10
    grey = max(0, min(255, grey))
    return f"#{grey:02x}{grey:02x}{grey:02x}"


class AnsiParser:
    """Incremental ANSI parser.

    Holds the current :class:`SgrState` between calls, so colour set in one
    write survives into the next -- which is required, because a stream is
    chunked wherever the writer happened to flush, not at escape boundaries.
    A partial escape at the end of a chunk is held back until the rest arrives.
    """

    def __init__(self) -> None:
        self.state = SgrState()
        self._pending = ""

    def reset(self) -> None:
        """Forget the current state and any partial escape."""
        self.state = SgrState()
        self._pending = ""

    def feed(self, text: str) -> list[AnsiEvent]:
        """Parse *text* and return the events it produced.

        Parameters
        ----------
        text : str

        Returns
        -------
        list
            :class:`Text` runs interleaved with cursor events.
        """
        buffer = self._pending + text
        self._pending = ""
        events: list[AnsiEvent] = []
        plain: list[str] = []

        def flush() -> None:
            if plain:
                events.append(Text("".join(plain), self.state))
                plain.clear()

        index = 0
        length = len(buffer)
        while index < length:
            char = buffer[index]

            if char == "\r":
                flush()
                events.append(CarriageReturn())
                index += 1
                continue
            if char == "\b":
                flush()
                count = 0
                while index < length and buffer[index] == "\b":
                    count += 1
                    index += 1
                events.append(Backspace(count))
                continue
            if char != "\x1b":
                plain.append(char)
                index += 1
                continue

            match = _CSI_RE.match(buffer, index)
            if match is not None:
                flush()
                self._apply_csi(match.group(1), match.group(3), events)
                index = match.end()
                continue

            # Check for a truncated escape *before* the catch-all below, which
            # would otherwise consume the ``ESC [`` of a split sequence and
            # leave its parameters to be printed as text.
            if _PARTIAL_ESC_RE.match(buffer, index):
                self._pending = buffer[index:]
                break

            other = _OTHER_ESC_RE.match(buffer, index)
            if other is not None and other.end() > index + 1:
                index = other.end()
                continue

            index += 1

        flush()
        return events

    def _apply_csi(self, params: str, final: str, events: list[AnsiEvent]) -> None:
        """Apply one CSI sequence.

        Parameters
        ----------
        params : str
            The parameter bytes, semicolon separated.
        final : str
            The final byte, which selects the action.
        events : list
            Appended to for cursor actions.
        """
        numbers = [int(p) for p in params.split(";") if p.isdigit()] or [0]
        if final == "m":
            self.state = self._apply_sgr(numbers)
        elif final == "K":
            events.append(EraseLine(numbers[0]))
        elif final == "J":
            events.append(EraseDisplay(numbers[0]))
        elif final in "AF":
            events.append(CarriageReturn())
        # Everything else (cursor positioning, scroll regions) is a terminal
        # feature a scrollback widget has no equivalent for; dropping it is
        # correct and keeps the text intact.

    def _apply_sgr(self, numbers: list[int]) -> SgrState:
        """Return the state after applying SGR *numbers*.

        Parameters
        ----------
        numbers : list of int

        Returns
        -------
        SgrState
        """
        state = self.state
        index = 0
        while index < len(numbers):
            code = numbers[index]
            if code == 0:
                state = SgrState()
            elif code == 1:
                state = dataclasses.replace(state, bold=True)
            elif code == 2:
                state = dataclasses.replace(state, faint=True)
            elif code == 3:
                state = dataclasses.replace(state, italic=True)
            elif code == 4:
                state = dataclasses.replace(state, underline=True)
            elif code == 7:
                state = dataclasses.replace(state, inverse=True)
            elif code == 9:
                state = dataclasses.replace(state, strike=True)
            elif code in (21, 22):
                state = dataclasses.replace(state, bold=False, faint=False)
            elif code == 23:
                state = dataclasses.replace(state, italic=False)
            elif code == 24:
                state = dataclasses.replace(state, underline=False)
            elif code == 27:
                state = dataclasses.replace(state, inverse=False)
            elif code == 29:
                state = dataclasses.replace(state, strike=False)
            elif 30 <= code <= 37:
                state = dataclasses.replace(state, fg=code - 30)
            elif 40 <= code <= 47:
                state = dataclasses.replace(state, bg=code - 40)
            elif 90 <= code <= 97:
                state = dataclasses.replace(state, fg=code - 90 + 8)
            elif 100 <= code <= 107:
                state = dataclasses.replace(state, bg=code - 100 + 8)
            elif code == 39:
                state = dataclasses.replace(state, fg=None)
            elif code == 49:
                state = dataclasses.replace(state, bg=None)
            elif code in (38, 48):
                colour, consumed = self._extended_colour(numbers, index)
                index += consumed
                if colour is not None:
                    key = "fg" if code == 38 else "bg"
                    state = dataclasses.replace(state, **{key: colour})
            index += 1
        return state

    @staticmethod
    def _extended_colour(numbers: list[int], index: int) -> tuple[int | str | None, int]:
        """Decode a ``38;5;N`` or ``38;2;R;G;B`` colour.

        Parameters
        ----------
        numbers : list of int
        index : int
            Position of the ``38``/``48`` selector.

        Returns
        -------
        tuple
            ``(colour, parameters_consumed)``.
        """
        if index + 1 >= len(numbers):
            return None, 0
        mode = numbers[index + 1]
        if mode == 5 and index + 2 < len(numbers):
            value = numbers[index + 2]
            return (value if value < 16 else _xterm256(value)), 2
        if mode == 2 and index + 4 < len(numbers):
            r, g, b = numbers[index + 2], numbers[index + 3], numbers[index + 4]
            return f"#{r & 255:02x}{g & 255:02x}{b & 255:02x}", 4
        return None, 1


def strip_ansi(text: str) -> str:
    """Return *text* with every escape sequence removed.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    return _OTHER_ESC_RE.sub("", _CSI_RE.sub("", text))
