"""A batch's lifetimes are written into the burst run they were fitted from, at once.

Kept only in memory, the 16 604 lifetimes of the owner's DNA13bp_3 never reached the container:
the pipeline drops Save results, so ndX showed no ``Tau`` column after Burst MLE. Now the batch
writes them itself, as members of the fitted run (``<run>/mle G|G``, derived from that run's
burst table, one row per burst -- as its 2CDE is), so ndX merges them onto that run and a
re-search (another run) does not get them. The data is the in-repository BH SPC-132
measurement, packed into a container with two runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.datastore import column_names, row_count, take_where
from chisurf.core.fio.fluorescence.burst import read_bur_file
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel
from chisurf.plugins.burst.burst_selection.api.io import write_container

from .conftest import BURST_TABLE, CHANNEL_SETTINGS

FITTED, OTHER = "fitted#1", "other#2"


@pytest.fixture(scope="module")
def container(sample_copy):
    table = read_bur_file(sample_copy / BURST_TABLE)
    raw = sample_copy / "m000.spc"
    write_container(raw, take_where(table, np.arange(row_count(table)) < 201), parameters={"run": 1}, run=FITTED)
    write_container(raw, take_where(table, np.arange(row_count(table)) < 81), parameters={"run": 2}, run=OTHER)
    return sample_copy / "m000.pto"


def _burst_table(container, run):
    with Measurement.open(container, writable=False) as m:
        return next(str(o.name) for o in m.artifacts() if str(o.name).startswith(f"{run}/") and str(o.name).endswith(".bur"))


def test_the_batch_writes_its_lifetimes_into_the_fitted_run(hermetic_env, container):
    from ndxplorer.io.pto_reader import read_run

    model = MleViewModel()
    model.set_setup(CHANNEL_SETTINGS)
    assert model.add_files([container]) == 1
    model.select_run(next(r for r in model.run_rows() if r["run_name"] == FITTED))  # not the newest
    for det in model.session.detectors:
        model.session.current_detector = det
        model.session.auto_extract()
    model.run_batch()  # no Save results
    assert "Written into 1 container" in model.status_text, model.status_text

    fitted = _burst_table(container, FITTED)
    with Measurement.open(container, writable=False) as m:
        names = {o.uid: str(o.name) for o in m._f.objects()}
        members = [n for n in names.values() if n.startswith(f"{FITTED}/mle ")]
        assert sorted(members) == [f"{FITTED}/mle G|G", f"{FITTED}/mle R|G"], sorted(names.values())
        for obj in m.artifacts():
            if str(obj.name) in members:
                assert [names[u] for u in m.parents(obj.uid)] == [fitted]
                assert m.tag(obj.uid, "_mmfdb_artifact.row_grain") == "burst"
        assert not any(n.startswith(f"{OTHER}/mle") for n in names.values())

    store, _provenance = read_run(container, table=fitted)
    columns = column_names(store)
    assert "Tau (G|G)" in columns and "Tau (R|G)" in columns, columns
    assert row_count(store) == model.n_bursts  # one row per burst, the skipped ones included
    other, _ = read_run(container, table=_burst_table(container, OTHER))
    assert not any(c.startswith("Tau") for c in column_names(other))

    # a refit replaces the run's lifetimes: one table per detector and run, never two
    model.session.det_settings["G|G"].min_photons += 1
    model.run_batch()
    with Measurement.open(container, writable=False) as m:
        again = [str(o.name) for o in m._f.objects() if str(o.name).startswith(f"{FITTED}/mle ")]
    assert sorted(again) == sorted(members)
