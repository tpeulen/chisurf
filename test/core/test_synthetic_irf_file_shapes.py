"""IRF text table shapes retain count samples rather than interleaving time coordinates."""

import numpy as np
import pytest


@pytest.mark.parametrize("rows", [1, 5])
def test_time_count_irf_file_reads_last_column_even_for_one_row(tmp_path, rows):
    """A text table has columns even when NumPy would otherwise squeeze its sole row."""
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import _load_irf

    counts = np.arange(1, rows + 1, dtype=float)
    table = np.column_stack((np.arange(rows) * 0.032, counts))
    path = tmp_path / "response.dat"
    np.savetxt(path, table)
    np.testing.assert_array_equal(_load_irf(path), counts)


@pytest.mark.parametrize("rows", [1, 5])
def test_one_column_irf_file_retains_every_sample(tmp_path, rows):
    """Reading a time/count table must not collapse an ordinary count vector."""
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import _load_irf

    counts = np.arange(1, rows + 1, dtype=float)
    path = tmp_path / "response.dat"
    np.savetxt(path, counts)
    np.testing.assert_array_equal(_load_irf(path), counts)


def test_numpy_vector_and_single_impulse_convolution_remain_unambiguous(tmp_path):
    """NumPy vectors retain samples; a one-bin table matches an explicit one-bin response."""
    from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import (
        _load_irf,
        compute_decay,
    )

    vector = np.array([0.25, 0.75])
    path = tmp_path / "response.npy"
    np.save(path, vector)
    np.testing.assert_array_equal(_load_irf(path), vector)
    impulse = tmp_path / "impulse.dat"
    np.savetxt(impulse, [[0.0, 1.0]])
    np.testing.assert_array_equal(
        compute_decay(n_bins=16, lifetimes=[2.0], bin_width=0.1, irf=impulse)["y"],
        compute_decay(n_bins=16, lifetimes=[2.0], bin_width=0.1, irf=[1.0])["y"],
    )
