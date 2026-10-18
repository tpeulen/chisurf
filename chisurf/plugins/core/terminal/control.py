"""The drawn terminal: a session's screen as an emtk control.

A retained control in emtk's classic contract (hosted by :func:`emtk.im.host_control`
in a dock or a child window): ``draw`` paints the visible rows as coloured runs
plus the caret, and the input handlers translate pointer and key events into
terminal actions -- typing, cursor keys, Ctrl chords, wheel scrollback,
selection copy. The *engine* seam is one object with ``screen``, ``write``,
``resize`` and ``alive`` (a :class:`~chisurf.plugins.core.terminal.session.PtySession`
in the app; a fake in tests), so drawing and key mapping are testable without
a process.

Cell sizes come from the painter each frame (``line_height`` and the width of
``"W"``); when they no longer fit the box the grid is resized, which is also
what tells the PTY (``TIOCSWINSZ`` → ``SIGWINCH`` in the child).
"""

from __future__ import annotations

from typing import Any

from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from emtk.keys import (
    KEY_BACKSPACE,
    KEY_DELETE,
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
    KEY_RIGHT,
    KEY_TAB,
    KEY_UP,
    letter_of,
)

__all__ = ["TerminalControl"]

#: The 16 ANSI colours, dim then bright, for dark and light themes.
_ANSI_DARK = (
    (208, 208, 208), (244, 108, 118), (152, 195, 121), (240, 198, 116),
    (110, 168, 245), (215, 137, 240), (95, 203, 216), (171, 178, 191),
    (120, 126, 140), (255, 122, 132), (170, 213, 140), (255, 220, 150),
    (130, 190, 255), (235, 165, 255), (115, 225, 240), (230, 234, 242),
)
_ANSI_LIGHT = (
    (44, 48, 58), (196, 74, 74), (98, 148, 66), (178, 128, 18),
    (46, 100, 197), (140, 62, 170), (24, 118, 138), (92, 99, 112),
    (60, 62, 76), (186, 39, 45), (98, 148, 66), (176, 118, 8),
    (26, 82, 182), (120, 44, 152), (12, 102, 124), (28, 30, 40),
)


def _hex_colour(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 6:
        try:
            return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
        except ValueError:
            pass
    return (0, 0, 0)


def _clamp01(cells: int) -> int:
    return max(0, min(int(cells), 15))


class TerminalControl:
    """One terminal session as a control: the grid, the caret, the keys.

    Parameters
    ----------
    session : object
        The engine seam: ``screen`` (a :class:`~chisurf.plugins.core.terminal.screen.TerminalScreen`),
        ``write(bytes)``, ``resize(columns, rows)`` and ``alive``.
    """

    #: Tab goes to the terminal (shell completion), not widget navigation.
    wants_tab = True

    def __init__(self, session: Any) -> None:
        self.session = session
        self.screen = session.screen
        self.has_focus = False
        self._drawn_revision = -1
        self._glyph_w = 8.0
        self._line_h = 16.0
        self._pad_x = 4.0
        self._pad_y = 3.0
        self._box = (0.0, 0.0, 1.0, 1.0)
        #: Viewport scroll above the live view, in lines.
        self.scroll_offset = 0
        #: ``(anchor, end)`` absolute positions of an active selection, else ``None``.
        self.selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self._selecting = False
        self._closed = False

    # ── the frame contract ────────────────────────────────────────────────

    def animating(self) -> bool:
        """New output arrived that no frame has drawn yet: keep frames coming."""
        return self.screen.revision != self._drawn_revision

    def next_frame_in(self) -> float | None:
        return 0.016 if self.animating() else None

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        from emtk.style import WINDOW_BG
        from emtk.theme import is_light

        self._box = (float(x), float(y), float(w), float(h))
        self._line_h = max(float(p.line_height()), 1.0)
        self._glyph_w = max(float(p.text_width("W")), 1.0)
        light = is_light()
        base_bg = (250, 250, 251, 255) if light else tuple(WINDOW_BG[:3]) + (255,)
        p.fill_rect(x, y, w, h, base_bg)
        self._fit_grid(w, h)
        self._drawn_revision = self.screen.revision
        base_fg = _ANSI_LIGHT[0] if light else _ANSI_DARK[0]
        cursor_row, cursor_col = self.screen.cursor
        rows_drawn = self.screen.rows
        first = self.screen.scrollback_lines - self.scroll_offset
        p.push_clip(x, y, w, h)
        try:
            for row in range(rows_drawn):
                index = first + row
                line_y = y + self._pad_y + row * self._line_h
                for run in self.screen.line_runs(index):
                    colour = self._colour_of(run.state, light, base_fg)
                    px = x + self._pad_x + run.start * self._glyph_w
                    p.text(px, line_y, len(run.text) * self._glyph_w, self._line_h,
                           0, run.text, colour)
                self._draw_selection(p, x, y, index, row)
            self._draw_caret(p, x, y, first, cursor_row, cursor_col, base_fg)
        finally:
            p.pop_clip()
        if not self._alive():
            from emtk.style import TEXT_DISABLED

            p.text(x + 6.0, y + h - self._line_h, w - 12.0, self._line_h, 0,
                   "— process exited —", TEXT_DISABLED)

    def _fit_grid(self, w: float, h: float) -> None:
        columns = max(2, int((w - 2 * self._pad_x) // self._glyph_w))
        rows = max(2, int((h - 2 * self._pad_y) // self._line_h))
        if (columns, rows) != (self.screen.columns, self.screen.rows):
            self.session.resize(columns, rows)

    def _colour_of(self, state, light: bool, base_fg: tuple) -> tuple:
        fg = state.fg
        if fg is None:
            colour = base_fg
        elif isinstance(fg, int):
            palette = _ANSI_LIGHT if light else _ANSI_DARK
            colour = palette[_clamp01(fg)]
        else:
            colour = _hex_colour(fg)
        if state.bold:
            colour = tuple(min(255, round(c * 1.12)) for c in colour)
        return tuple(int(c) for c in colour) + (255,)

    def _draw_selection(self, p, x: float, y: float, index: int, row: int) -> None:
        if self.selection is None:
            return
        (a_line, a_col), (b_line, b_col) = self.selection
        if index < min(a_line, b_line) or index > max(a_line, b_line):
            return
        if a_line == b_line:
            span = (a_col, b_col) if a_line == index else None
        elif index == min(a_line, b_line):
            col = a_col if a_line < b_line else b_col
            span = (col, self.screen.columns - 1)
        elif index == max(a_line, b_line):
            col = b_col if b_line > a_line else a_col
            span = (0, col)
        else:
            span = (0, self.screen.columns - 1)
        if span is None:
            return
        start_col, end_col = sorted(span)
        px = x + self._pad_x + start_col * self._glyph_w
        width = (end_col - start_col + 1) * self._glyph_w
        p.fill_rect(px, y + self._pad_y + row * self._line_h, width, self._line_h,
                    (66, 150, 250, 64))

    def _draw_caret(self, p, x: float, y: float, first: int,
                    row: int, col: int, base_fg: tuple) -> None:
        """A steady block caret at the cursor, when focused and in view.

        *row* is grid-relative; on screen it sits at ``row + scroll_offset``
        (a scrolled-up view pushes it down out of the box).
        """
        if not self.has_focus or not self.screen.cursor_visible or self.screen.alt:
            return
        viewport_row = row + self.scroll_offset
        if not 0 <= viewport_row < self.screen.rows:
            return
        from emtk.style import TEXT

        px = x + self._pad_x + col * self._glyph_w
        py = y + self._pad_y + viewport_row * self._line_h
        p.fill_rect(px, py, max(2.0, self._glyph_w * 0.7), self._line_h, TEXT)

    def _alive(self) -> bool:
        return bool(getattr(self.session, "alive", True))

    # ── coordinates ───────────────────────────────────────────────────────

    def _cell_at(self, px: float, py: float) -> tuple[int, int]:
        x, y, _w, _h = self._box
        col = int((px - x - self._pad_x) // self._glyph_w)
        row = int((py - y - self._pad_y) // self._line_h)
        col = max(0, min(col, self.screen.columns - 1))
        first = self.screen.scrollback_lines - self.scroll_offset
        return (first + max(0, row), col)

    # ── input: pointer ────────────────────────────────────────────────────

    def press(self, px: float, py: float, x=0.0, y=0.0, w=0.0, h=0.0,
              modifiers=0, clicks=1) -> bool:
        self.has_focus = True
        if clicks >= 3:
            self._select_line_at(px, py)
        elif clicks == 2:
            self._select_word_at(px, py)
        else:
            cell = self._cell_at(px, py)
            self.selection = (cell, cell)
            self._selecting = True
        return True

    def drag(self, px: float, py: float, x=0.0, y=0.0, w=0.0, h=0.0):
        if self._selecting and self.selection is not None:
            self.selection = (self.selection[0], self._cell_at(px, py))
        return None

    def release(self) -> None:
        self._selecting = False

    def focus_lost(self) -> None:
        self.has_focus = False

    def scroll(self, rows: int) -> int:
        """Wheel rows (negative = up, into the history), as ``TextEditor`` takes them.

        ``ControlSurface.on_wheel`` already converts notches to rows
        (``-WHEEL_ROWS * steps``), so *rows* is used as-is.
        """
        self.scroll_offset = max(0, min(self.scroll_offset - int(rows),
                                        self.screen.max_scroll_offset))
        return self.scroll_offset

    # ── selection ─────────────────────────────────────────────────────────

    def _select_word_at(self, px: float, py: float) -> None:
        line, col = self._cell_at(px, py)
        cells = self.screen._cells(line)
        def is_word(ch: str) -> bool:
            return ch.isalnum() or ch in "_-./"
        start = col
        while start > 0 and is_word(cells[start][0]):
            start -= 1
        if not is_word(cells[start][0]):
            start += 1
        end = col
        while end < len(cells) - 1 and is_word(cells[end][0]):
            end += 1
        if end > start:
            self.selection = ((line, start), (line, end))

    def _select_line_at(self, px: float, py: float) -> None:
        line, _col = self._cell_at(px, py)
        self.selection = ((line, 0), (line, self.screen.columns - 1))

    def select(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        """Set the selection from absolute positions (tests and menus)."""
        self.selection = ((int(start[0]), int(start[1])), (int(end[0]), int(end[1])))

    def copy_selection(self) -> str | None:
        if self.selection is None:
            return None
        text = self.screen.text_range(*self.selection)
        return text or None

    def clear_selection(self) -> None:
        self.selection = None

    def paste_text(self, text: str) -> None:
        """Paste: newlines become CR, the byte a terminal reads as Enter."""
        data = text.replace("\r\n", "\r").replace("\n", "\r")
        self.session.write(data.encode("utf-8"))

    # ── input: keys ───────────────────────────────────────────────────────

    _NAV = {
        KEY_UP: b"\x1b[A", KEY_DOWN: b"\x1b[B", KEY_RIGHT: b"\x1b[C", KEY_LEFT: b"\x1b[D",
        KEY_HOME: b"\x1b[H", KEY_END: b"\x1b[F",
        KEY_DELETE: b"\x1b[3~", KEY_PAGE_UP: b"\x1b[5~", KEY_PAGE_DOWN: b"\x1b[6~",
    }
    _NAV_CTRL = {
        KEY_UP: b"\x1b[1;5A", KEY_DOWN: b"\x1b[1;5B", KEY_RIGHT: b"\x1b[1;5C",
        KEY_LEFT: b"\x1b[1;5D", KEY_HOME: b"\x1b[1;5H", KEY_END: b"\x1b[1;5F",
    }

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        self.has_focus = True
        key, modifiers = int(key), int(modifiers)
        ctrl = modifiers & (CONTROL_MODIFIER | META_MODIFIER)
        alt = modifiers & ALT_MODIFIER
        if key == KEY_ESCAPE:
            if self.selection is not None:
                self.clear_selection()
            else:
                self.session.write(b"\x1b")
            return True
        if ctrl:
            if key in self._NAV_CTRL:
                self.session.write(self._NAV_CTRL[key])
                return True
            letter = letter_of(key, "" if modifiers & SHIFT_MODIFIER else text)
            if letter:
                byte = ord(letter.lower()) - 96  # C0 of the letter: Ctrl+C -> 0x03
                if 0 <= byte <= 31:
                    self.session.write(bytes([byte]))
                    return True
            if key == KEY_BACKSPACE:
                self.session.write(b"\x08")
                return True
            return True  # host shortcuts (close, paste) are not terminal bytes
        if key in self._NAV:
            self.session.write(self._NAV[key])
            return True
        if alt and text:
            self.session.write(b"\x1b" + text.encode("utf-8"))  # ESC+key: Meta
            return True
        if key in (KEY_RETURN, KEY_ENTER):
            self.session.write(b"\r")
            return True
        if key == KEY_BACKSPACE:
            self.session.write(b"\x7f")
            return True
        if key == KEY_TAB:
            self.session.write(b"\t")
            return True
        if text:
            self.session.write(text.encode("utf-8"))
            return True
        return True

    def ime_caret(self):
        """The caret's box for the input method's candidate window."""
        row, col = self.screen.cursor
        x, y, _w, _h = self._box
        viewport_row = row + self.scroll_offset
        if not 0 <= viewport_row < self.screen.rows:
            return None
        return (x + self._pad_x + col * self._glyph_w,
                y + self._pad_y + viewport_row * self._line_h,
                self._line_h)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.session, "close", None)
        if callable(close):
            close()
