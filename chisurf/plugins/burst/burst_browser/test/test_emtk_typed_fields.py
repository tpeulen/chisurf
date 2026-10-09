"""The photon-size gate of the emtk Burst Browser takes typed numbers, operated with real pointer and keyboard input."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.plugins.burst.burst_browser.gui.app import create_app
from chisurf.plugins.emtk_test_input import Driver


@pytest.fixture
def drv(tmp_path):
    rows = pd.DataFrame(
        {
            "First Photon": [0, 10, 20],
            "Last Photon": [9, 19, 29],
            "Number of Photons": [100, 200, 300],
            "E": [0.1, 0.5, 0.9],
            "S": [0.4, 0.5, 0.6],
        }
    )
    interleaved = pd.DataFrame(np.zeros((7, 5)), columns=rows.columns)
    interleaved.loc[1::2] = rows.values
    path = tmp_path / "test.bur"
    interleaved.to_csv(path, sep="\t", index=False)
    app = create_app()
    app.load_bur(path)
    app.controller._future.result(timeout=5)
    app.controller.poll()
    yield Driver(app)
    app.close()


def test_typed_size_bounds_gate_the_bursts(drv):
    model = drv.app.model
    drv.type_into_name("sz_min", "150")
    assert model.size_min == 150
    drv.type_into_name("sz_max", "250")
    assert model.size_max == 250
    np.testing.assert_array_equal(model.masked_row_indices(), [1])
    drv.type_into_name("sz_min", "-20")
    assert model.size_min == 0, "a negative photon count is clamped to the Qt minimum"
    drv.type_into_name("sz_min", "400")
    assert (model.size_min, model.size_max) == (250, 400), "bounds typed out of order are swapped"
