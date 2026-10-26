"""Preparing a burst run of a measurement container for the 2D MFD fit.

The same measurement read two ways -- its legacy burst folder, and the run a container holds of
the same bursts -- must give the same arrays: the run is read through the reader every burst
analysis shares (ndX's), and its photons are the container's own (here linked to the ``.spc``).
"""

from __future__ import annotations

import pathlib
import shutil

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd import prepare_burst_folder

REPO = pathlib.Path(__file__).resolve().parents[2]
DATA = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
ANALYSIS = DATA / "burstwise_All 0.1000#15"
RUN = "burstwise_All 0.1000#15"

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)


@pytest.fixture
def folder_and_run(tmp_path):
    """One measurement's legacy folder, and a run of the same bursts in an analysis container."""
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    data = tmp_path / "data"
    (data / RUN / "bi4_bur").mkdir(parents=True)
    shutil.copy(DATA / "m000.spc", data / "m000.spc")
    shutil.copy(ANALYSIS / "bi4_bur" / "m000.bur", data / RUN / "bi4_bur" / "m000.bur")
    (tmp_path / "analysis").mkdir()
    container = write_container(
        data / "m000.spc",
        deinterleave_bursts(read_bur_file(ANALYSIS / "bi4_bur" / "m000.bur")),
        parameters={"search": 1},
        out_dir=tmp_path / "analysis",
        run=RUN,
        raw_data="sidecar",
    )
    return data / RUN, f"{container}/{RUN}"


def test_a_run_prepares_as_its_folder_does(folder_and_run):
    folder, run = folder_and_run
    legacy = prepare_burst_folder(folder, with_photons=True)
    prepared = prepare_burst_folder(run, with_photons=True)

    assert len(prepared) == len(legacy) > 0
    assert prepared.channels == legacy.channels
    np.testing.assert_array_equal(prepared.counts, legacy.counts)
    np.testing.assert_array_equal(prepared.first_photon, legacy.first_photon)
    np.testing.assert_allclose(prepared.duration, legacy.duration)
    # The channel definition is checked against the photons the run's container holds.
    assert prepared.verified_channels == legacy.verified_channels
    assert set(prepared.sources.origin.values()) == {"container"}
    assert prepared.summary["photons"] and all(n > 0 for n in prepared.summary["photons"].values())
