"""Importing a burst selection, and keeping the file it was imported from.

A BID selection is not a burst search: another program decided the burst
boundaries and this reads them in. The legacy output is a `bi4_bur/` folder
beside a `.bid` that nothing in it mentions, so the one thing worth recording —
*where these bursts came from* — is exactly the thing the layout drops. The
container embeds the `.bid` and makes the burst table its child.

The first test here is not about the container at all. It covers the columns
that say which BID file produced a burst, which stopped being written when the
burst table became a store: the assignment sat inside a bare
``except Exception: pass``, so the failure was silent and the table simply lost
two columns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.pto import Measurement

SPC = (
    Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")

#: Three bursts, as photon-index (start, stop) pairs.
INTERVALS = np.array([[100, 180], [900, 1010], [5000, 5120]])


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    """A `.spc` with a `.bid` beside it, in a directory of their own."""
    (tmp_path / SPC.name).write_bytes(SPC.read_bytes())
    np.savetxt(tmp_path / "m000.bid", INTERVALS, fmt="%d")
    return tmp_path / "m000.bid"


def test_the_bursts_are_tagged_with_the_file_that_defined_them(measurement: Path):
    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

    convert_bid_file(measurement, output_types={"pto"})
    with Measurement.open(measurement.with_suffix(".pto")) as m:
        table = m.get_store("bursts")
        assert "BID File" in column_names(table)
        assert list(numeric_column(table, "BID Index")) == [1, 1, 1]


def test_the_bid_file_travels_with_the_bursts(measurement: Path):
    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

    convert_bid_file(measurement, output_types={"pto"})
    with Measurement.open(measurement.with_suffix(".pto")) as m:
        bursts = m._resolve("bursts")
        assert m.parents(bursts) == [m._resolve("m000.bid")]
        assert m.tag(bursts, "_mmfdb_operation.operation_type") == "import"
        # The bytes, so the selection can be repeated without the original.
        assert m.get_blob("m000.bid") == measurement.read_bytes()


@pytest.mark.parametrize("types", [{"pto"}, {"pto", "bur"}])
def test_the_padding_never_reaches_the_container(measurement: Path, types: set):
    """Whether the `.bur` was asked for changes the table in memory, not in here.

    The padding is stated by the caller rather than detected: the BID columns
    are constant over every row, padding included, so a heuristic looking for
    all-zero even rows would conclude — correctly — that the table is not
    padded, and write three placeholder rows as if they were bursts.
    """
    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

    convert_bid_file(measurement, output_types=types)
    with Measurement.open(measurement.with_suffix(".pto")) as m:
        table = m.get_store("bursts")
        assert row_count(table) == len(INTERVALS)
        photons = numeric_column(table, "Number of Photons")
        assert np.all(photons > 0), "a padding row was written as a burst"
