"""Shared test helpers of the saturation window: a driver that operates it with pointer and keys, and the layout checks.

The pointer driver and the painters are the imaging family's (``imaging_emtk.testing``) and the layout checker is the PSF
calculator's (``psf_calculator.tests.driving``): nothing is copied here, only the window's own lookups are added.
"""

from __future__ import annotations

from chisurf.plugins.calculator.psf_calculator.tests.driving import (  # noqa: F401
    ClipPainter,
    clipped_texts,
    draw_clip,
    layout_problems,
    overlaps,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import (  # noqa: F401
    Driver,
    MetricPainter,
    hermetic_env,
)

BIG = (1200, 800)
SMALL = (800, 600)


class SatDriver(Driver):
    """The imaging driver reading rectangles from the window's one registry (``item_rects``)."""

    def rect(self, name):
        self.draw(1)
        found = self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.item_rects)}"
        return tuple(found)

    def reveal(self, name):
        return self.rect(name)

    # -- the tables ---------------------------------------------------------------------------------------- #
    def control(self, table):
        """The painted table control of a spec table (``dark_rows``, ``exc_rows``, ``brightness_rows``, ``optics_rows``)."""
        self.draw(1)
        for (
            state
        ) in self.app.forms.values():  # any window of the app that draws a table of this source
            if table in state.tables:
                return state.tables[table].control
        raise AssertionError(
            f"no table {table!r} is drawn: {[list(s.tables) for s in self.app.forms.values()]}"
        )

    def cell(self, table, row, column):
        """The rectangle of a table cell: *row* is the row's position, *column* the column's key."""
        control = self.control(table)
        bx, by, bw, bh = control._body_box
        position = row - control.bar.top
        x = bx
        for col, width in zip(control._shown, control._widths):
            if col.key == column:
                return (x, by + position * control._row_h, width, control._row_h)
            x += width
        raise AssertionError(
            f"column {column!r} of {table} is not shown: {[c.key for c in control._shown]}"
        )

    def edit_cell(self, table, row, column, text, enter=True):
        """Double click the cell, replace its text, press Enter."""
        x, y, w, h = self.cell(table, row, column)
        self.app.press(x + w / 2, y + h / 2, clicks=2)
        self.draw(1)
        self.app.release()
        self.draw(1)
        control = self.control(table)
        assert control.editing is not None, f"{table}[{row}].{column} did not open for typing"
        self.select_all()
        self.type_text(text)
        if enter:
            self.enter()

    def click_cell(self, table, row, column):
        x, y, w, h = self.cell(table, row, column)
        self.click_at(x + w / 2, y + h / 2)


TABLE_FORMS = {
    "dark_rows": "k_dark",
    "exc_rows": "k_exc",
    "brightness_rows": "brightness",
    "optics_rows": "optics",
}
