"""Notes under a plot, drawn in emtk: a legend, findings, a small table.

The posterior pages wrote these as Qt rich text (``<span style='color:#888'>``,
``<b>``, ``<table>``) in a ``QLabel``. Here a note is data -- a list of
:class:`Line` and :class:`Table` -- so a test reads what the page says without
parsing HTML, and the surface draws it without a Qt widget.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Colours of the note kinds, as RGB.
MUTED = (136, 136, 136)
PLAIN = (225, 225, 225)
GOOD = (60, 143, 92)
FAIR = (176, 112, 32)
BAD = (176, 48, 48)


@dataclass
class Line:
    """One wrapped line of note text."""

    text: str
    colour: tuple = PLAIN
    bold: bool = False


@dataclass
class Table:
    """A small table: a header row, then rows of cells; ``bold`` names columns."""

    header: list
    rows: list = field(default_factory=list)
    bold: tuple = ()


def as_text(notes: list) -> str:
    """Everything *notes* says, as plain text (tests, tooltips, logs)."""
    parts = []
    for note in notes:
        if isinstance(note, Table):
            parts.append(" | ".join(note.header))
            parts += [" | ".join(row) for row in note.rows]
        else:
            parts.append(note.text)
    return "\n".join(parts)


def height(notes: list, width: float) -> float:
    """The height :func:`draw` will take for *notes* at *width*."""
    from emtk import im

    line = im.get_text_line_height_with_spacing()
    total = 0.0
    for note in notes:
        if isinstance(note, Table):
            total += line * (1 + len(note.rows)) + 4.0
        else:
            text_width = im.calc_text_size(note.text)[0]
            total += line * max(1, math.ceil(text_width / max(width - 8.0, 40.0)))
    return total


def draw(notes: list, key: str = "notes") -> None:
    """Draw *notes* at the cursor, wrapped to the available width."""
    from emtk import im

    bold_font = {"family": "sans-serif", "bold": True}
    for index, note in enumerate(notes):
        if isinstance(note, Table):
            columns = len(note.header)
            if im.begin_table(f"##{key}-{index}", columns):
                for title in note.header:
                    im.table_setup_column(title)
                im.table_headers_row()
                for row in note.rows:
                    im.table_next_row()
                    for column, cell in enumerate(row):
                        im.table_next_column()
                        if column in note.bold:
                            im.push_font(bold_font)
                            im.text(cell)
                            im.pop_font()
                        else:
                            im.text(cell)
                im.end_table()
            continue
        if note.bold:
            im.push_font(bold_font)
        im.push_text_wrap_pos(0.0)
        im.text_colored(note.colour, note.text)
        im.pop_text_wrap_pos()
        if note.bold:
            im.pop_font()


def panel_and_notes(key: str, item, notes: list) -> None:
    """Host *item* (a :class:`~chisurf.gui.plots.emtk_page.PanelItem`) over *notes*.

    The panel takes what the notes leave, so the notes are never pushed off the
    bottom of the page.
    """
    from emtk import im

    width, available = im.get_content_region_avail()
    reserve = height(notes, width) + 6.0 if notes else 0.0
    im.host_control(f"##{key}", item, (width, max(available - reserve, 60.0)))
    draw(notes, key)


class Tabs:
    """A tab bar whose current tab is page state, so code and tests can select one."""

    def __init__(self, titles) -> None:
        self.titles = tuple(titles)
        self.current = 0
        self._request = None

    def select(self, index: int) -> None:
        """Make tab *index* current on the next frame."""
        self.current = int(index)
        self._request = int(index)

    def draw(self, key: str, body) -> None:
        """Draw the bar and the current tab's body (``body(index)``)."""
        from emtk import im

        if not im.begin_tab_bar(f"##{key}"):
            return
        for index, title in enumerate(self.titles):
            flags = im.TabItemFlags.SET_SELECTED if self._request == index else 0
            if im.begin_tab_item(title, flags):
                self.current = index
                body(index)
                im.end_tab_item()
        self._request = None
        im.end_tab_bar()
