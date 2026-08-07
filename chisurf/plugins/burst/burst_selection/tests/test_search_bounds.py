"""The two bounds a burst search is asked for, and used to ignore.

Both were settings the analysis carried, recorded in provenance, and printed
into the output folder's own name -- while the search ran with something else:

* ``min_photons`` was enforced by the sliding-window search alone, because it
  passes the number to ``tttrlib``'s ``burst_search``. Every other mode
  (count-rate, CUSUM, Kalman, a tttrlib-registry search) returns a photon mask,
  and the bursts were then whatever contiguous runs that mask happened to have
  -- down to two photons. A count-rate run on the bundled DNA measurement
  produced 44126 "bursts" with a median of 14 photons in a folder named
  ``countrate_All 0.1500#60``.
* ``max_gap`` was left at :func:`find_bursts`'s own default of 4, so a run
  configured to bridge nothing still bridged four photons.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import numeric_column
from chisurf.plugins.burst.burst_selection.api.io import load_tttr
from chisurf.plugins.burst.burst_selection.api.models import (
    AnalysisSettings,
    BurstDetectionSettings,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from chisurf.plugins.burst.burst_selection.api.selection import (
    analyze_file,
    apply_photon_filters,
    drop_short_bursts,
    find_bursts,
)
from chisurf.core.datastore import store_from_rows

DATA = Path(__file__).resolve().parent / "data" / "bh_spc132_sm_dna"
SPC = DATA / "m000.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _count_rate_settings(min_photons: int) -> AnalysisSettings:
    s = AnalysisSettings()
    s.output_formats = []
    s.photon_filter = PhotonFilterSettings(
        channels=[],
        filter_active=True,
        used_filter="count_rate",
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0),
    )
    s.burst_detection = BurstDetectionSettings(
        min_photons=min_photons, photon_window=10, time_window=1e-3
    )
    return s


@pytest.mark.parametrize("min_photons", [20, 60, 120])
def test_a_count_rate_search_honours_the_photon_minimum(tmp_path: Path, min_photons: int):
    """No burst in the table is smaller than the minimum that was asked for."""
    result = analyze_file(SPC, settings=_count_rate_settings(min_photons))
    table = store_from_rows(result.dataframes[str(SPC)])
    counts = numeric_column(table, "Number of Photons")
    # The interleaved zero rows are file-format padding, not bursts.
    real = counts[counts > 0]
    assert real.size, "the search found nothing to check"
    assert real.min() >= min_photons


def test_the_reported_burst_count_is_the_number_of_bursts_written(tmp_path: Path):
    """`n_bursts` used to count bursts the summarizer then dropped."""
    result = analyze_file(SPC, settings=_count_rate_settings(60))
    rows = result.dataframes[str(SPC)]
    assert result.metadata["n_bursts"] == (len(rows) - 1) // 2


def test_raising_the_minimum_can_only_remove_bursts():
    """A monotone bound: the burst list at 120 is a subset of the one at 20."""
    tttr = load_tttr(SPC)
    settings = _count_rate_settings(20)
    selected = apply_photon_filters(tttr, settings.photon_filter)
    found = find_bursts(selected, max_gap=settings.photon_filter.max_gap)
    low = {tuple(p) for p in drop_short_bursts(found, 20).tolist()}
    high = {tuple(p) for p in drop_short_bursts(found, 120).tolist()}
    assert high < low


def test_the_gap_the_settings_ask_for_is_the_gap_that_is_bridged():
    """`max_gap=0` must not bridge, which the hard-coded default of 4 did."""
    mask = np.zeros(64, dtype=np.uint8)
    mask[10:20] = 1
    mask[22:32] = 1  # a two-photon hole
    joined = find_bursts(mask, max_gap=4)
    apart = find_bursts(mask, max_gap=0)
    assert len(joined) == 1
    assert len(apart) == 2


def test_a_single_photon_run_is_never_a_burst():
    """Kept the table and the reported count in step; also plainly right."""
    start_stop = np.array([[0, 0], [5, 9]], dtype=np.int64)
    kept = drop_short_bursts(start_stop, 2)
    assert kept.tolist() == [[5, 9]]
