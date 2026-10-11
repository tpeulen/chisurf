"""The decay of a selection of bursts: exact photon counts, written as a child of its run."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import tttrlib

from chisurf.core.datastore import numeric_column, row_count
from chisurf.core.fio.analysis_path import read_tables
from chisurf.core.fio.fluorescence.burst_container import container_for
from chisurf.core.fio.pto import Measurement
from chisurf.core.fluorescence.burst.decay import (
    DECAY_NAME,
    sub_ensemble_decay,
    write_sub_ensemble_decay,
)

SPC = Path(__file__).resolve().parents[1] / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
RUN = "countrate_All 0.1000#60"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no instrument test data")


@pytest.fixture
def run(tmp_path: Path):
    """A container with a real photon stream and six bursts of known photon ranges."""
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    raw = tmp_path / "m000.spc"
    shutil.copy(SPC, raw)
    n_photons = len(tttrlib.TTTR(str(raw), "SPC-130"))
    edges = np.linspace(0, n_photons - 1, 13).astype(int)
    first = edges[0:12:2]
    last = edges[1:12:2]
    n = first.size
    table = pd.DataFrame(
        {
            "First Photon": np.zeros(2 * n + 1),
            "Last Photon": np.zeros(2 * n + 1),
            "First File": ["0"] * (2 * n + 1),
        }
    )
    table.loc[1::2, "First Photon"] = first
    table.loc[1::2, "Last Photon"] = last
    table.loc[1::2, "First File"] = "m000.spc"
    write_container(raw, table, parameters={"min_photons": 3}, run=RUN)
    return f"{container_for(raw)}/{RUN}", raw, first, last


def _expected_photons(raw: Path, first, last, keep, channels) -> int:
    chan = np.asarray(tttrlib.TTTR(str(raw), "SPC-130").routing_channels)
    return int(
        sum(np.isin(chan[f : l + 1], channels).sum() for f, l, k in zip(first, last, keep) if k)
    )


def test_the_histogram_sums_to_the_selected_photon_count(run):
    path, raw, first, last = run
    keep = np.array([True, False, True, True, False, False])
    stream = {"channels": [0, 1]}
    decay = sub_ensemble_decay(path, stream, mask=keep)
    assert numeric_column(decay, "Counts").sum() == _expected_photons(
        raw, first, last, keep, [0, 1]
    )
    everything = sub_ensemble_decay(path, stream)
    assert numeric_column(everything, "Counts").sum() == _expected_photons(
        raw, first, last, np.ones(6, bool), [0, 1]
    )


def test_rebinning_loses_no_photon(run):
    path, *_ = run
    full = sub_ensemble_decay(path, [0, 1])
    coarse = sub_ensemble_decay(path, [0, 1], n_bins=64)
    assert row_count(coarse) == 64
    assert numeric_column(coarse, "Counts").sum() == numeric_column(full, "Counts").sum()


def test_a_selection_of_nothing_is_refused(run):
    path, *_ = run
    with pytest.raises(ValueError, match="no burst"):
        sub_ensemble_decay(path, [0, 1], mask=np.zeros(6, bool))
    with pytest.raises(ValueError, match="entries for 6 bursts"):
        sub_ensemble_decay(path, [0, 1], mask=np.ones(3, bool))


def test_the_decay_reads_back_and_chains_to_its_selection(run):
    path, raw, *_ = run
    keep = np.array([True, True, False, False, True, False])
    decay = sub_ensemble_decay(path, [0, 1], mask=keep)
    container = write_sub_ensemble_decay(
        path, decay, {"channels": "0,1", "selected": keep.tolist()}
    )
    back = read_tables(path)[DECAY_NAME]
    np.testing.assert_allclose(numeric_column(back, "Counts"), numeric_column(decay, "Counts"))
    with Measurement.open(container) as m:
        uid = m._f.find(f"{RUN}/{DECAY_NAME}")
        assert m._f.object(uid).kind == "tcspc_decay"
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "histogram_bin"
        assert m.tag(uid, "_mmfdb_operation.operation_type") == "tcspc_histogram_computation"
        lineage = [step["name"] for step in m.lineage(uid)]
    assert f"{RUN}/bi4_bur/m000.bur" in lineage  # decay -> selection -> primary photons
    # a different selection is a different run, not an overwrite
    other = sub_ensemble_decay(path, [0, 1], mask=~keep)
    write_sub_ensemble_decay(path, other, {"channels": "0,1", "selected": (~keep).tolist()})
    with Measurement.open(container) as m:
        assert sum(1 for o in m.artifacts() if str(o.name).endswith(DECAY_NAME)) == 2
