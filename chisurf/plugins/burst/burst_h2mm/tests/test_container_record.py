"""An H2MM run is recorded in the measurement's container -- and only there -- and the
state-split burst MLE reads the photons' states back from it."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.burst_states import UNASSIGNED, container_state_array


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import open_measurement
    from chisurf.plugins.burst.burst_h2mm.core.export import write_burst_states
    from chisurf.plugins.burst.burst_h2mm.core.h2mm import BurstPhotons
    from chisurf.plugins.burst.burst_h2mm.core.photons import PhotonMeta

    from .test_export import _dataset_via_tttrlib

    out = tmp_path_factory.mktemp("rec")
    raw = out / "m.ptu"
    # any photon file makes the container; the H2MM tables only need its identity
    import shutil
    from pathlib import Path

    sample = Path(__file__).parents[2] / "burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    shutil.copy(sample, out / "m.spc")
    with open_measurement(out / "m.spc"):
        pass
    container = out / "m.pto"
    # two analysed bursts of four in the burst table (rows 1 and 3)
    data = BurstPhotons(
        streams=np.array([0, 1, 0, 1, 1], dtype=np.int8),
        gap_slot=np.array([0, 0, -1, 0, -1], dtype=np.int16),
        burst_offsets=np.array([0, 3, 5], dtype=np.int64),
        unique_dt=np.array([10], dtype=np.int64),
        n_streams=2,
    )
    meta = PhotonMeta(
        macro_time=np.arange(5, dtype=np.int64) * 10,
        micro_time=np.array([5, 6, 7, 8, 9]),
        channel=np.array([0, 1, 0, 1, 1]),
        burst_id=np.array([0, 0, 0, 1, 1]),
        photon_index=np.array([100, 101, 102, 300, 301]),
    )
    burst_df = store_from_arrays({"First File": np.array(["m.spc"] * 4, dtype=object)})
    path = np.array([0, 1, 1, 0, 0])
    written = write_burst_states(
        burst_df, [1, 3], data, path, np.array([0.2, 0.8]), out, container=container,
        photon_meta=meta,
    )
    return container, written, out


def test_the_states_are_in_the_container_and_nothing_beside_it(recorded):
    container, written, out = recorded
    assert written and all(str(w).endswith(".pto") for w in written)
    assert not list(out.glob("*.h5")) and not (out / "h2mm").exists()
    states, n_states = container_state_array(container, 400)
    assert n_states == 2
    assert states[[100, 101, 102, 300, 301]].tolist() == [0, 1, 1, 0, 0]
    assert (states[:100] == UNASSIGNED).all()


def test_a_container_without_an_h2mm_run_has_no_states(tmp_path):
    states, n = container_state_array(tmp_path / "none.pto", 10)
    assert states is None and n == 0
