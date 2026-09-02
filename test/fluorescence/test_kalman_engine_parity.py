"""Kalman burst search: the engine is the only path.

The compiled ``tttrlib`` search (``burst_search_kalman``) is the sole
implementation. The in-tree Python recursion was a fallback for a build whose
``tttrlib`` predates the engine; since the tree pins its engines, the fallback
was dead code and was deleted in PRD-133 (the fallback audit). This test now
covers only the engine path.

Run on the bundled BH SPC132 single-molecule measurement (~174 k photons, real
burst counts) rather than a synthetic array.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst import kalman as kalman_mod

_SPC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection" / "tests"
    / "data" / "bh_spc132_sm_dna" / "m000.spc"
)

_PARAMS = dict(min_ph=20, dt=1e-3, q=20.0, r_scale=1.0, z_thresh=3.0,
               min_len=2, merge_gap=20, per_channel=True)


@pytest.fixture(scope="module")
def tttr():
    assert _SPC.exists(), _SPC
    return tttrlib.TTTR(str(_SPC), "SPC-130")


def test_engine_bursts_are_well_formed(tttr):
    """Inclusive ``[start, stop]`` photon indices, ordered and in range."""
    bursts = kalman_mod.kalman_burst_search(tttr, **_PARAMS)
    assert len(bursts) > 0
    assert (bursts[:, 0] <= bursts[:, 1]).all()
    assert bursts[:, 0].min() >= 0
    assert bursts[:, 1].max() < len(tttr)
    # ``Number of Photons == stop - start + 1``: the inclusive-stop convention
    # the .bur writer and the companion readers share.
    assert (bursts[:, 1] - bursts[:, 0] + 1 >= _PARAMS["min_ph"]).all()


def test_mask_matches_the_burst_ranges(tttr):
    """``kalman_filter`` is exactly ``kalman_burst_search`` as a photon mask."""
    bursts = kalman_mod.kalman_burst_search(tttr, **_PARAMS)
    mask = kalman_mod.kalman_filter(tttr, **_PARAMS)

    assert mask.dtype == np.bool_ and mask.shape == (len(tttr),)
    expected = np.zeros(len(tttr), dtype=bool)
    for start, stop in bursts:
        expected[start:stop + 1] = True  # inclusive stop
    np.testing.assert_array_equal(mask, expected)


def test_empty_result_when_no_bursts():
    """An empty TTTR produces an empty burst array and an all-False mask."""
    empty = tttrlib.TTTR()
    bursts = kalman_mod.kalman_burst_search(empty, **_PARAMS)
    assert bursts.shape == (0, 2)
    mask = kalman_mod.kalman_filter(empty, **_PARAMS)
    assert mask.shape == (0,) or np.all(~mask)
