"""compute_bva returns a new table and leaves its input as it was.

The GUIs keep the burst table they read and recompute on it after a parameter
change; when compute_bva appended its columns in place, that second run failed
("both stores have a column 'Proximity Ratio Mean'") in both the Qt tool's auto
update and the emtk controller.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import column_names
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
from chisurf.plugins.burst.burst_bva.core.computation import compute_bva, read_burst_analysis


def test_compute_bva_twice_on_the_same_table(tmp_path):
    folder = build(tmp_path / "measurement")
    table, tttrs = read_burst_analysis(folder, "SPC-130", pattern="bi4_bur")
    before = list(column_names(table))
    kwargs = dict(
        donor_channels=[0],
        acceptor_channels=[1],
        donor_micro_time_ranges=[(0, 32768)],
        acceptor_micro_time_ranges=[(0, 32768)],
        minimum_window_length=0.01,
        number_of_photons_per_slice=10,
    )
    first = compute_bva(table, tttrs, **kwargs)
    assert list(column_names(table)) == before  # the input is untouched
    second = compute_bva(table, tttrs, **{**kwargs, "number_of_photons_per_slice": 12})
    assert "Proximity Ratio Std" in column_names(second)
    assert not np.allclose(
        np.asarray(first["Proximity Ratio Std"], float),
        np.asarray(second["Proximity Ratio Std"], float),
        equal_nan=True,
    )
    again = compute_bva(first, tttrs, **kwargs)  # a table that already has the columns
    assert list(column_names(again)).count("Proximity Ratio Std") == 1
    assert np.allclose(
        np.asarray(again["Proximity Ratio Std"], float),
        np.asarray(first["Proximity Ratio Std"], float),
        equal_nan=True,
    )
