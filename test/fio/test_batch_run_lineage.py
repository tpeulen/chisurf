"""A batch result is derived from the burst search it was computed from.

One `.pto` holds several burst searches (another count-rate threshold, another
gap), and a batch over many files and runs has to write each result back under
the search its rows came from. The rows used to carry only ``First File`` — the
container — so every result's parent was "the newest search", which is wrong as
soon as a second one is written: `lineage()`, the run picker and the legacy
export all followed the wrong burst grid.

Each test reads the *older* search explicitly while a newer one exists, which is
the case the old rule got wrong.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column, store_from_arrays
from chisurf.core.fio.analysis_path import resolve_run, run_path
from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container
from chisurf.core.fio.fluorescence.burst_container import container_for, write_burst_artifact
from chisurf.core.fio.fluorescence.burst_tree import RUN_COLUMN
from chisurf.core.fio.pto import Measurement

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"
OLD = "countrate_All 0.1000#60"
NEW = "countrate_All 0.2000#60"
N_OLD, N_NEW = 6, 4

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


def _bur(n: int, name: str):
    """A ``.bur`` as stored: ``2n + 1`` rows, data on the odd ones, padding reads ``0``."""
    first = np.zeros(2 * n + 1)
    first[1::2] = np.arange(n) * 100.0
    last = np.zeros(2 * n + 1)
    last[1::2] = np.arange(n) * 100.0 + 50.0
    files = np.array(["0"] * (2 * n + 1), dtype=object)
    files[1::2] = name
    return store_from_arrays(
        {
            "First Photon": first,
            "Last Photon": last,
            "Number of Photons": last - first + (first > 0),
            "First File": files,
        }
    )


@pytest.fixture
def box(tmp_path: Path) -> Path:
    """A container holding two searches; ``NEW`` is written last."""
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    for run, n in ((OLD, N_OLD), (NEW, N_NEW)):
        write_burst_artifact(
            raw,
            _bur(n, raw.name),
            name=f"{run}/bi4_bur/m000.bur",
            deinterleave=False,
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"run": run},
            derived_from=(),
        )
    return container_for(raw)


def _parent_runs(box: Path, table: str) -> dict[str, list[str]]:
    """``{artifact name: [parent names]}`` for every artifact whose table is *table*."""
    out = {}
    with Measurement.open(box, writable=False) as m:
        names = {obj.uid: str(obj.name) for obj in m._f.objects()}
        for obj in m.artifacts():
            if str(obj.name).rpartition("/")[2] == table:
                out[str(obj.name)] = [names.get(uid, "") for uid in m.parents(obj.uid)]
    return out


def _bur_of(run: str) -> str:
    return f"{run}/bi4_bur/m000.bur"


def test_the_reader_stamps_every_row_with_the_run_it_read(box: Path):
    old, _ = _read_burst_analysis_from_container(Path(run_path(box, OLD)))
    new, _ = _read_burst_analysis_from_container(box)
    assert set(np.asarray(old[RUN_COLUMN]).astype(str)) == {run_path(box, OLD)}
    # No run named: the newest search, and the rows say which one that was.
    assert set(np.asarray(new[RUN_COLUMN]).astype(str)) == {run_path(box, NEW)}
    assert resolve_run(box, operation="burst_selection") == NEW
    assert resolve_run(run_path(box, OLD)) == OLD


def test_bva_of_the_older_search_is_derived_from_it(box: Path):
    from chisurf.plugins.burst.burst_bva.core.computation import write_bva_container

    for run, n in ((OLD, N_OLD), (NEW, N_NEW)):
        df, _ = _read_burst_analysis_from_container(Path(run_path(box, run)))
        df["Proximity Ratio Mean"] = np.linspace(0.1, 0.9, n)
        df["Proximity Ratio Std"] = np.full(n, 0.05)
        # The analysis folder names the container only: the rows carry the run.
        write_bva_container(df, analysis_folder=box, parameters={"window": 5})

    parents = _parent_runs(box, "bva")
    assert parents == {f"{OLD}/bva": [_bur_of(OLD)], f"{NEW}/bva": [_bur_of(NEW)]}, parents
    with Measurement.open(box, writable=False) as m:
        stored = m.get_store(f"{OLD}/bva")
        assert RUN_COLUMN not in column_names(stored), "the run routes a row, it is not a result"
        assert len(numeric_column(stored, "Proximity Ratio Mean")) == N_OLD


def test_mle_batch_rows_carry_the_run_and_two_searches_keep_two_fits(box: Path):
    from chisurf.plugins.burst.burst_mle_analysis.engine import (
        read_burst_container,
        write_container_tables,
    )

    rows = []
    for run in (OLD, NEW):
        table, container = read_burst_container(run_path(box, run))
        identity = str(np.asarray(table["_measurement_path"], dtype=object)[0])
        assert identity == run_path(container, run), identity
        # What the batch does with an identity: one result row per burst.
        rows += [
            {"First Stem": identity, "Detector": "green", "Tau (green)": 2.0}
            for _ in range(int(len(numeric_column(table, "First Photon"))))
        ]
    write_container_tables(
        rows, {"green": ("green", "g", ["Tau (green)"])}, {"model": "same settings"}
    )

    parents = _parent_runs(box, "mle green")
    assert sorted(parents.values()) == [[_bur_of(OLD)], [_bur_of(NEW)]], (
        "the same settings on two searches are two fits, each derived from its own search",
        parents,
    )


def test_h2mm_states_are_written_under_the_search_they_came_from(box: Path):
    from chisurf.plugins.burst.burst_h2mm.core.export import write_burst_states

    class _Data:
        burst_offsets = np.array([0, 3, 6])

    burst_df, _ = _read_burst_analysis_from_container(Path(run_path(box, OLD)))
    written = write_burst_states(
        burst_df,
        [0, 2],
        _Data(),
        np.array([0, 0, 1, 1, 1, 1]),
        np.array([0.2, 0.8]),
        container=box,
        parameters={"states": 2},
    )
    assert written
    parents = _parent_runs(box, "h2mm")
    assert list(parents.values()) == [[_bur_of(OLD)]], parents


def test_burst_fcs_rows_name_their_search_through_the_burst_folder(box: Path):
    from chisurf.plugins.burst.burst_fcs_correlator.core.export import (
        write_fcs_results_container,
    )

    folder = run_path(box.resolve(), OLD)
    rows = [
        {
            "First File": str(box.resolve()),
            "Burst Folder": folder,
            "Burst Index": i,
            "pair_name": "a",
        }
        for i in (0, 2)
    ]
    from chisurf.plugins.burst.burst_fcs_correlator.core.export import RESULT_COLUMNS

    for row in rows:
        for feature in RESULT_COLUMNS:
            row[feature["source"]] = 1.0
    write_fcs_results_container(rows, {(folder, box.stem): N_OLD})
    parents = _parent_runs(box, "burst fcs")
    assert list(parents.values()) == [[_bur_of(OLD)]], parents
