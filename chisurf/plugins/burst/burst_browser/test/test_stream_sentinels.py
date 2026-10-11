"""A burst table's "no photon" sentinels and trailing tab do not reach the browser's E/S.

The bundled sm-DNA burst folder (``bi4_bur``) carries no E/S column, so the browser
derives them from the gated window streams. A stream with no photon in a burst is
written as ``-1``; read as a count it gave S = (dd+da)/(dd+da-1) > 1 and E < 0
for a third of the bursts (the Burst Browser of guide 28 showed E down to -0.096
and S up to 1.106). Every ``.bur`` line also ends in a tab, which the reader turned
into a column named ``""`` that the browser's table listed.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import column_names, numeric_column
from chisurf.plugins.burst.burst_browser.view_model import BurstBrowserViewModel

HEADER = [
    "First Photon", "Last Photon", "Duration (ms)", "Number of Photons",
    "Number of Photons (green)", "Number of Photons (red)", "Number of Photons (yellow)",
    "S prompt green (kHz) | 0-2048", "S prompt red (kHz) | 0-2048",
    "S delayed yellow (kHz) | 2048-4095",
]
# donor-only burst (no red, no yellow photon), FRET burst, burst with no yellow photon
BURSTS = [
    [0, 9, 1.0, 10, 10, 0, 0, 10.0, -1.0, -1.0],
    [10, 29, 1.0, 20, 5, 10, 5, 5.0, 10.0, 5.0],
    [30, 49, 1.0, 20, 10, 10, 0, 10.0, 10.0, -1.0],
]


def _write_bur(path):
    lines = ["\t".join(HEADER) + "\t"]
    zero = "\t".join("0" for _ in HEADER) + "\t"
    for row in BURSTS:
        lines += [zero, "\t".join(str(v) for v in row) + "\t"]
    lines.append(zero)
    path.write_text("\n".join(lines) + "\n")


def test_no_photon_sentinel_is_zero_photons_and_the_trailing_tab_is_no_column(tmp_path):
    folder = tmp_path / "bi4_bur"
    folder.mkdir()
    _write_bur(folder / "m000.bur")
    model = BurstBrowserViewModel()
    model.load_folder(folder)
    names = column_names(model.table)
    assert "" not in names
    e = numeric_column(model.table, "E")
    s = numeric_column(model.table, "S")
    np.testing.assert_allclose(e, [0.0, 2 / 3, 0.5])
    np.testing.assert_allclose(s, [1.0, 0.75, 1.0])
    assert model.status_text() == "Bursts: 3 / 3 selected"
