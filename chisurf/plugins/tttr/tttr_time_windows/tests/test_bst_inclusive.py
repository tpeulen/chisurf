"""A ``.bst`` row is first/last photon, both inclusive."""

import numpy as np

from chisurf.plugins.tttr.tttr_time_windows.api.io import save_bst


def test_save_bst_writes_inclusive_last_photon(tmp_path):
    """Half-open windows become inclusive rows; empty windows are dropped."""
    bids = np.array([[0, 3], [3, 3], [3, 7]])
    out = tmp_path / "w.bst"
    save_bst(bids, out)
    rows = np.loadtxt(out, dtype=np.int64, ndmin=2)
    np.testing.assert_array_equal(rows, [[0, 2], [3, 6]])
    # consecutive windows tile the photons without sharing one
    assert rows[1, 0] == rows[0, 1] + 1
