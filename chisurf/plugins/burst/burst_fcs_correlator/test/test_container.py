"""The diffusion times keep the burst they belong to.

The ``td4`` companion beside this cannot: it is merged onto the burst table by
counting rows, and its own writer builds the grid from
``df['Burst Index'].unique()`` — the bursts that produced a result. A burst the
correlator skipped is therefore a *missing* row rather than a blank one, and
every burst after it is merged against the wrong burst's diffusion time. The
file's shape and column names stay right; only the attribution is wrong, which
is why nothing notices.

These tests pin the difference: the key is written, the gaps survive it, and a
re-run does not accumulate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from chisurf.core.datastore import column_names, numeric_column
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_fcs_correlator.core.export import (
    write_fcs_container,
)

SPC = (
    Path(__file__).resolve().parents[2]
    / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna" / "m000.spc"
)

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")

SETTINGS = {"n_bins": 3, "n_casc": 20, "make_fine": False}


def _table() -> pd.DataFrame:
    """Four results with gaps at 2 and 4–6 — bursts the correlator skipped."""
    return pd.DataFrame(
        {
            "Burst Index": [0, 1, 3, 7],
            "td_mean__green-red": [0.51, 0.62, 0.48, 0.55],
            "td_peak__green-red": [0.50, 0.60, 0.47, 0.54],
        }
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / SPC.name
    path.write_bytes(SPC.read_bytes())
    return path


def test_a_skipped_burst_leaves_a_gap_and_not_a_shift(source: Path):
    written = write_fcs_container(source, _table(), parameters=SETTINGS)
    with Measurement.open(written) as m:
        table = m.get_store("burst fcs")
        assert list(numeric_column(table, "Burst Index")) == [0, 1, 3, 7]
        # The value still belongs to burst 7, not to the fourth row of a grid.
        index = list(numeric_column(table, "Burst Index")).index(7)
        assert numeric_column(table, "td_mean__green-red")[index] == pytest.approx(0.55)


def test_the_join_is_declared_rather_than_counted(source: Path):
    written = write_fcs_container(source, _table(), parameters=SETTINGS)
    with Measurement.open(written) as m:
        uid = m._f.find("burst fcs")
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "burst"
        assert m.tag(uid, "_mmfdb_edge.source_row_column") == "Burst Index"


def test_a_diffusion_time_says_it_is_milliseconds(source: Path):
    """A pair name in the suffix is not a unit, so the label cannot carry one."""
    written = write_fcs_container(source, _table(), parameters=SETTINGS)
    with Measurement.open(written) as m:
        # A unit is an attribute of the column, so the table comes back as a
        # store — a frame has nowhere to keep one.
        table = m.get_store("burst fcs")
        units = {
            name: m.column_units(table, name) for name in column_names(table)
        }
    assert units["td_mean__green-red"] == "milliseconds"
    assert units["td_peak__green-red"] == "milliseconds"
    # An index is dimensionless, which is a claim; "" would mean unknown.
    assert units["Burst Index"] == "dimensionless"


def test_rerunning_the_correlation_does_not_accumulate(source: Path):
    written = write_fcs_container(source, _table(), parameters=SETTINGS)
    with Measurement.open(written) as m:
        before = m._f.n_objects()
    for _ in range(3):
        write_fcs_container(source, _table(), parameters=SETTINGS)
    with Measurement.open(written) as m:
        assert m._f.n_objects() == before
