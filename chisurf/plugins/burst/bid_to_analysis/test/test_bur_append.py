"""Converting a second BID file into an existing analysis appends, not overwrites.

The append path used to read the existing ``.bur`` back with ``pandas.read_csv``
and ``pandas.concat`` it with the newly imported bursts. It reads and merges
through the DataStore CSV reader now (``read_csv_table`` / ``concat_stores``);
this pins that the existing bursts survive the round trip and the new ones
land after them, in order.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column, row_count
from chisurf.core.fio.fluorescence.burst import read_bur_file

SPC = (
    Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")

FIRST = np.array([[100, 180], [900, 1010], [5000, 5120]])
SECOND = np.array([[6000, 6080], [7000, 7100]])


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    (tmp_path / SPC.name).write_bytes(SPC.read_bytes())
    return tmp_path


def test_reconverting_the_bid_file_appends_to_the_existing_bur(measurement: Path):
    """A second ``convert_bid_file`` call on the same measurement finds the
    ``.bur`` already there (both the output folder and the ``.bur`` name are
    keyed by the TTTR/BID stem) and must append rather than overwrite it.
    """
    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

    bid_path = measurement / "m000.bid"
    np.savetxt(bid_path, FIRST, fmt="%d")
    bur_path = convert_bid_file(bid_path, output_types={"bur"}, bid_index=1)

    # The BID tag columns ("BID Index"/"BID File") are constant over every row,
    # padding included, which defeats deinterleave_bursts's all-zero-even-row
    # heuristic -- read the raw zero-interleaved table and slice the odd (real)
    # rows directly instead, the way the ``.bur`` format itself defines them.
    table = read_bur_file(bur_path)
    assert row_count(table) == 2 * len(FIRST) + 1
    assert list(numeric_column(table, "BID Index")[1::2]) == [1, 1, 1]

    # The selection was extended and the tool re-run on the same file.
    np.savetxt(bid_path, SECOND, fmt="%d")
    convert_bid_file(bid_path, output_types={"bur"}, bid_index=2)

    combined = read_bur_file(bur_path)
    n_total = len(FIRST) + len(SECOND)
    assert row_count(combined) == 2 * n_total + 1
    # Existing rows survive the read-back untouched, and the new ones follow.
    assert list(numeric_column(combined, "BID Index")[1::2]) == [1, 1, 1, 2, 2]
    assert list(numeric_column(combined, "First Photon")[1::2]) == [
        *FIRST[:, 0].tolist(),
        *SECOND[:, 0].tolist(),
    ]
