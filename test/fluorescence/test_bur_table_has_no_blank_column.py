"""A stacked ``.bur`` table carries no column named ``""``.

The ``.bur`` format ends every line with a tab, which a delimited reader reads as
one more, unnamed field. ``load_bur_dataframe`` is what analyses (and
``BurstWorkflow.select_bursts`` -> ``Bursts.table``) read burst tables through,
and it handed that layout artefact on as a column called ``""``.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fluorescence.burst.photons import load_bur_dataframe

HEADER = "First Photon\tLast Photon\tNumber of Photons\tFirst File\tLast File\t\n"


def _bur(path, rows):
    lines = [HEADER, "0\t0\t0\t0\t0\t\n"]
    for first, last in rows:
        lines += [f"{first}\t{last}\t{last - first + 1}\tm.spc\tm.spc\t\n", "0\t0\t0\t0\t0\t\n"]
    path.write_text("".join(lines))
    return path


def test_the_trailing_tab_is_not_a_column(tmp_path):
    a = _bur(tmp_path / "a.bur", [(10, 40), (100, 160)])
    b = _bur(tmp_path / "b.bur", [(5, 25)])
    table = load_bur_dataframe([a, b])
    names = column_names(table)
    assert names == ["First Photon", "Last Photon", "Number of Photons", "First File", "Last File"]
    # The interleave stays (callers pick the real rows): 2N+1 rows per file.
    assert row_count(table) == 5 + 3
    np.testing.assert_array_equal(
        numeric_column(table, "Number of Photons"), [0, 31, 0, 61, 0, 0, 21, 0]
    )
