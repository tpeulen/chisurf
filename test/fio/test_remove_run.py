"""The analyses of a container form a dependency graph; removing one removes what was computed from it.

A burst search is a run; BVA, 2CDE, burst-wise lifetimes, ... written into it are analyses of that
run; a fusion is a run computed from another. The Datasets workspace shows that graph as a tree and
deletes a node with everything below it, because a result whose source is gone cannot be
reproduced. Unrelated analyses and the photons stay.
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
from chisurf.core.project.analysis import analysis_graph, dependents, remove_analysis

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


def _write(raw: Path, run: str, parents=(), table="bi4_bur/m000.bur", operation="burst_selection") -> None:
    write_burst_artifact(
        raw,
        _bur(4, raw.name),
        name=f"{run}/{table}",
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type=operation,
        parameters={"run": run, "table": table},
        derived_from=parents,
    )


BURSTS = f"{OLD}/bi4_bur/m000.bur"


@pytest.fixture
def box(tmp_path: Path) -> Path:
    """Two searches; 2CDE and lifetimes of the older one (lifetimes read 2CDE as well), a fusion of
    it, and a run written from that fusion."""
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    _write(raw, OLD)
    _write(raw, NEW)
    _write(raw, OLD, [BURSTS], table="2cde fret", operation="burst_2cde")
    _write(raw, OLD, [BURSTS, f"{OLD}/2cde fret"], table="lifetimes", operation="burst_lifetime_fitting")
    _write(raw, FUSED, [BURSTS])
    _write(raw, OF_FUSED, [f"{FUSED}/bi4_bur/m000.bur"])
    return container_for(raw)


def _labels(nodes):
    return [n["label"] for n in nodes]


def test_the_graph_hangs_every_analysis_under_what_it_was_computed_from(box):
    graph = {n["label"]: n for n in analysis_graph(box)}
    assert list(graph) == [OLD, NEW, "Burst 2CDE", "Burst lifetime fitting", FUSED, OF_FUSED]
    assert graph[OLD]["parent"] is None and graph[NEW]["parent"] is None  # from the photons
    assert graph["Burst 2CDE"]["parent"] == (OLD, "")
    assert graph["Burst lifetime fitting"]["parents"] == [(OLD, ""), (OLD, "burst_2cde")]
    assert graph[FUSED]["parent"] == (OLD, "") and graph[OF_FUSED]["parent"] == (FUSED, "")
    assert graph["Burst 2CDE"]["kind"] == "table" and graph[FUSED]["kind"] == "bursts"
    assert graph["Burst 2CDE"]["address"] == run_path(box, f"{OLD}/2cde fret")


def test_the_dependents_are_everything_computed_from_it_through_any_chain(box):
    assert _labels(dependents(run_path(box, OLD))) == [
        "Burst 2CDE", "Burst lifetime fitting", FUSED, OF_FUSED
    ]
    assert _labels(dependents(run_path(box, f"{OLD}/2cde fret"))) == ["Burst lifetime fitting"]
    assert _labels(dependents(run_path(box, NEW))) == []


def test_removing_a_run_removes_what_was_computed_from_it_and_keeps_the_rest(box):
    with Measurement.open(box, writable=False) as m:
        photons = m.instrument_uid
    removed = remove_analysis(run_path(box, OLD))
    assert removed[0] == run_path(box, OLD) and len(removed) == 5
    assert list_runs(box) == [NEW]
    with Measurement.open(box, writable=False) as m:
        assert m.instrument_uid == photons  # the photons are untouched


def test_removing_an_analysis_of_a_run_leaves_the_run(box):
    remove_analysis(run_path(box, f"{OLD}/2cde fret"))
    assert _labels(analysis_graph(box)) == [OLD, NEW, FUSED, OF_FUSED]


def test_removing_a_leaf_run_leaves_its_source(box):
    remove_analysis(run_path(box, OF_FUSED))
    assert list_runs(box)[-1] == FUSED


def test_restored_rows_name_their_source_row(box, tmp_path, monkeypatch):
    """A reopened project lists ``derived_datasets`` as they are: each row is already linked to the
    row it was computed from, not only to the photons."""
    from chisurf.core.project import analysis

    monkeypatch.setattr(analysis, "containers", lambda: {"photons-1": [box]})
    rows = {d.name: d for d in analysis.derived_datasets()}
    assert rows[OLD].result_of == "photons-1"
    assert rows["Burst 2CDE"].result_of == rows[OLD].unique_identifier
    assert rows[OF_FUSED].result_of == rows[FUSED].unique_identifier
    assert rows["Burst 2CDE"].data_kind == "table"
