"""``BurstWorkflow.select_bursts`` writes the setup's detectors into the burst table.

The search ran without the setup's detectors, so the table it returned had no ``Number of Photons (<detector>)``
columns and no proximity ratio: ``Bursts.recurrence()`` raised "no FRET efficiency / proximity-ratio column" on every
real search (guide 27 carried it as a known defect). The detectors' names are the setup's own, so recurrence also
derives the ratio from a setup whose detectors are not called green/red.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).parents[2] / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    (tmp_path / "settings").mkdir()
    shutil.copy(DATA / "m000.spc", tmp_path / "m000.spc")
    from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow

    wf = BurstWorkflow.demo()
    yield wf, wf.register(str(tmp_path / "m000.spc"))
    wf.close()


@pytest.mark.parametrize("names", [("green", "red"), ("donor", "acceptor")])
def test_bursts_carry_per_detector_counts_and_recurrence_runs(workflow, names):
    from chisurf.core.datastore import numeric_column
    from chisurf.plugins.burst.burst_analysis.api.workflow import Setup

    wf, handle = workflow
    donor, acceptor = names
    setup = Setup.from_channels(file_type="SPC-130", **{donor: (0, 8), acceptor: (1, 9)})
    bursts = wf.select_bursts(handle, setup=setup, min_photons=20)
    n_d = numeric_column(bursts.table, f"Number of Photons ({donor})")
    n_a = numeric_column(bursts.table, f"Number of Photons ({acceptor})")
    total = numeric_column(bursts.table, "Number of Photons")
    assert n_d.size == total.size > 100
    np.testing.assert_array_equal(
        n_d + n_a, total
    )  # channels 0/8 and 1/9 are every photon of this file
    recurrence = bursts.recurrence()
    expected = n_a / (n_d + n_a)
    np.testing.assert_allclose(recurrence.efficiency, expected)
