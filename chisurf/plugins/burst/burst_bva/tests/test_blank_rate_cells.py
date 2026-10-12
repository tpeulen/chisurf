"""A burst table with an empty count-rate cell stacks with one without.

Undetermined count rates are written as empty cells (a stream with one photon has
no duration). The BVA reader typed such a column as text in that file and as
float64 in the others, then refused to stack them -- BVA on the bundled sm-DNA
folder failed with "column 'Green Count Rate (KHz)' is float64 here and str there".
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import numeric_column, row_count
from chisurf.plugins.burst.burst_bva.core.computation import read_burst_analysis

HEADER = [
    "First Photon",
    "Last Photon",
    "Number of Photons",
    "Green Count Rate (KHz)",
    "First File",
]


def _write(path, rate):
    zero = "\t".join("0" for _ in HEADER) + "\t"
    row = "\t".join(["0", "9", "10", rate, "m.spc"]) + "\t"
    path.write_text("\n".join(["\t".join(HEADER) + "\t", zero, row, zero, row, zero]) + "\n")


def test_an_empty_rate_cell_is_missing_and_the_files_stack(tmp_path):
    bur = tmp_path / "analysis" / "bi4_bur"
    bur.mkdir(parents=True)
    _write(bur / "a.bur", "12.5")
    _write(bur / "b.bur", "")
    # second burst of b has a rate: an otherwise numeric column with one blank
    text = (bur / "b.bur").read_text().splitlines()
    text[4] = text[4].replace("\t\tm.spc", "\t3.0\tm.spc")
    (bur / "b.bur").write_text("\n".join(text) + "\n")
    table, _ = read_burst_analysis(tmp_path / "analysis", "SPC-130", pattern="bi4_bur")
    assert row_count(table) == 4
    rate = numeric_column(table, "Green Count Rate (KHz)")
    np.testing.assert_array_equal(np.isnan(rate), [False, False, True, False])
    np.testing.assert_allclose(rate[[0, 1, 3]], [12.5, 12.5, 3.0])
