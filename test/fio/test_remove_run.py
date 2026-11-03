"""A burst run is removed from its container with every run derived from it.

The Datasets workspace deletes a run row: the run goes from the .pto, and so does every analysis
written from it (a fusion of its bursts, an analysis of that fusion), because a result whose source
is gone cannot be reproduced. Unrelated runs and the photons stay.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fio.analysis_path import list_runs, run_path
from chisurf.core.fio.fluorescence.burst_container import container_for, write_burst_artifact
from chisurf.core.fio.pto import Measurement
from chisurf.core.project.analysis import remove_run, run_dependents

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"
OLD = "countrate_All 0.1000#60"
NEW = "countrate_All 0.2000#60"
FUSED = f"{OLD} fused p0.50"
OF_FUSED = f"{FUSED} again"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


def _bur(n: int, name: str):
    first = np.zeros(2 * n + 1)
    first[1::2] = np.arange(n) * 100.0
    last = first + 50.0 * (first > 0)
    files = np.array(["0"] * (2 * n + 1), dtype=object)
    files[1::2] = name
    return store_from_arrays(
        {"First Photon": first, "Last Photon": last, "Number of Photons": last - first, "First File": files}
    )


def _write(raw: Path, run: str, parents=()) -> None:
    write_burst_artifact(
        raw,
        _bur(4, raw.name),
        name=f"{run}/bi4_bur/m000.bur",
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type="burst_selection",
        parameters={"run": run},
        derived_from=parents,
    )


@pytest.fixture
def box(tmp_path: Path) -> Path:
    """Two searches; a fusion of the older one, and a run written from that fusion."""
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    _write(raw, OLD)
    _write(raw, NEW)
    _write(raw, FUSED, [f"{OLD}/bi4_bur/m000.bur"])
    _write(raw, OF_FUSED, [f"{FUSED}/bi4_bur/m000.bur"])
    return container_for(raw)


def test_the_dependents_are_the_runs_derived_from_it_through_any_chain(box):
    assert run_dependents(run_path(box, OLD)) == [FUSED, OF_FUSED]
    assert run_dependents(run_path(box, FUSED)) == [OF_FUSED]
    assert run_dependents(run_path(box, NEW)) == []


def test_removing_a_run_removes_its_dependents_and_keeps_the_rest(box):
    with Measurement.open(box, writable=False) as m:
        photons = m.instrument_uid
    removed = remove_run(run_path(box, OLD))
    assert removed == [run_path(box, r) for r in (OLD, FUSED, OF_FUSED)]
    assert list_runs(box) == [NEW]
    with Measurement.open(box, writable=False) as m:
        assert m.instrument_uid == photons  # the photons are untouched


def test_removing_a_leaf_run_leaves_its_source(box):
    remove_run(run_path(box, OF_FUSED))
    assert list_runs(box) == [OLD, NEW, FUSED]
