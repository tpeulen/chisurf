"""A fit page's notes table gives each column its widest cell's share, so cells never overlap.

Found by the final shell parity pass (okf/plugins/emtk-ports/final-parity/shell): the What-if
page's table split its width equally, and at a docked width "18.2743 ± 0.622" ran into the "r"
column ("0.622−0.543").
"""

from __future__ import annotations

from emtk.app import ImApp
from emtk.testing import Driver

from chisurf.emtk.fit_pages.pages import emtk_notes as N


def test_cells_stay_in_their_columns_at_a_narrow_width():
    from emtk import im

    table = N.Table(["parameter", "would be", "free", "r", "width"], bold=(1,))
    table.rows = [
        ["a1", "18.2743 ± 0.522", "18.2743 ± 0.622", "-0.543", "16% narrower"],
        ["n0", "4.19553e+06 ± 2.96e+03", "4.19553e+06 ± 4.41e+03", "-0.742", "33% narrower"],
    ]

    def gui():
        im.begin("notes", (0, 0, 560, 200))
        N.draw([table])
        im.end()

    driver = Driver(ImApp(gui), size=(560, 200))
    driver.frame(2)
    for row in table.rows:
        spans = []
        for cell in row:
            hit = [t for t in driver.painter.texts if t[5] == cell]
            assert hit, cell
            x, _y, w, _h = hit[-1][:4]
            spans.append((x, x + w))
        for (_a, end), (start, _b) in zip(spans, spans[1:]):
            assert end <= start + 0.5, (row, spans)
