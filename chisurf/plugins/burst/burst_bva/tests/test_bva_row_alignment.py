"""BVA results must stay addressed by original burst-table row.

A ``.bur`` table is interleaved --- every other row is a sentinel whose
``First File`` names no measurement --- so roughly half the rows carry no
result. Appending one value per *processed* row makes the column shorter than
the table, which either raises on assignment or, worse, silently shifts one
burst's result onto another.

This replaces ``test_bva_numpy_fallback.py``. That file pinned the same
property on the in-tree NumPy path, which has since been deleted: on real
photons it agreed with the compiled engine to **3e-16** once its burst slice
was corrected from ``[first:last]`` to ``[first:last+1]`` --- as written it
dropped the last photon of every burst. The property is worth keeping; the
second implementation was not.
"""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.core.datastore import numeric_column, row_count, store_from_arrays
from chisurf.plugins.burst.burst_bva.core.computation import compute_bva

DONOR, ACCEPTOR = 0, 1
#: Photon routing channels; two bursts of six are carved out of these below.
CHANNELS = [0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1]


@pytest.fixture()
def photons():
    """A real in-memory TTTR — the compiled engine will not take a stand-in."""
    channels = np.asarray(CHANNELS, dtype=np.int8)
    n = channels.size
    data = tttrlib.TTTR()
    data.append_events(
        np.arange(n, dtype=np.uint64),
        np.zeros(n, dtype=np.uint16),
        channels,
        np.zeros(n, dtype=np.int8),
        False,
        0,
    )
    data.header.set_macro_time_resolution(1e-8)
    return {"m000.spc": data}


@pytest.fixture()
def interleaved_table():
    """Two real bursts with a sentinel row between and after them."""
    return store_from_arrays(
        {
            "First File": np.array(["m000.spc", "0", "m000.spc", "0"]),
            "First Photon": np.array([0, 0, 6, 0]),
            "Last Photon": np.array([5, 0, 11, 0]),
        }
    )


def _proximity_ratio(first: int, last: int) -> float:
    """Acceptor fraction over the *inclusive* photon range, computed directly."""
    segment = np.asarray(CHANNELS[first : last + 1])
    n_acceptor = int((segment == ACCEPTOR).sum())
    return n_acceptor / segment.size


def test_results_keep_their_own_row(photons, interleaved_table):
    """Sentinel rows come back NaN and the real bursts stay on their own rows."""
    result = compute_bva(
        interleaved_table,
        photons,
        donor_channels=[DONOR],
        acceptor_channels=[ACCEPTOR],
        donor_micro_time_ranges=[(0, 4096)],
        acceptor_micro_time_ranges=[(0, 4096)],
        number_of_photons_per_slice=2,
    )

    means = numeric_column(result, "Proximity Ratio Mean")
    stds = numeric_column(result, "Proximity Ratio Std")

    assert len(means) == row_count(interleaved_table)
    assert np.isnan(means[1]) and np.isnan(means[3])
    assert np.isnan(stds[1]) and np.isnan(stds[3])
    # A shifted result would put the second burst's value on row 1.
    assert np.isfinite(means[0]) and np.isfinite(means[2])


def test_the_whole_burst_is_used(photons, interleaved_table):
    """``Last Photon`` is inclusive, and every photon in the burst counts.

    This is the check the deleted NumPy path failed: it sliced ``[first:last]``
    and so dropped each burst's last photon, which moved the mean by ~1/N.
    Averaging the per-slice ratios over a burst whose slices all have the same
    size gives the burst's own acceptor fraction, so the answer is arithmetic
    rather than a recorded number.
    """
    result = compute_bva(
        interleaved_table,
        photons,
        donor_channels=[DONOR],
        acceptor_channels=[ACCEPTOR],
        donor_micro_time_ranges=[(0, 4096)],
        acceptor_micro_time_ranges=[(0, 4096)],
        number_of_photons_per_slice=2,
    )
    means = numeric_column(result, "Proximity Ratio Mean")

    for row, (first, last) in ((0, (0, 5)), (2, (6, 11))):
        assert means[row] == pytest.approx(_proximity_ratio(first, last)), (
            f"row {row}: photons {first}..{last} inclusive"
        )
