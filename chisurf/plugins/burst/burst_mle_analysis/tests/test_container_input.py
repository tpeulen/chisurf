"""Burst MLE reads a run of a measurement's ``.pto`` and writes its fits back into it.

The container branch is the one BVA, 2CDE and H2MM take: the bursts and the photons are in the one file, the Runs table
picks which burst search is fitted, and the results are an object of that container -- no ``b?4`` folder beside it.
The data is the in-repository BH SPC-132 measurement, packed into a container with two runs of different size.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import row_count, take_where
from chisurf.core.fio.fluorescence.burst import read_bur_file
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel
from chisurf.plugins.burst.burst_selection.api.io import write_container
from chisurf.plugins.core.pto_inspector.core import with_run_picker

from .conftest import BURST_TABLE, CHANNEL_SETTINGS

BIG, SMALL_RUN = "runBig#1", "runSmall#2"
SMALL_N = 41  # table rows (20 bursts after the zero interleave)


@pytest.fixture(scope="module")
def container(sample_copy: Path) -> Path:
    """``m000.pto`` with a big and a small burst search of the measurement's own photons."""
    table = read_bur_file(sample_copy / BURST_TABLE)
    raw = sample_copy / "m000.spc"
    write_container(raw, table, parameters={"run": 1}, run=BIG)
    write_container(
        raw,
        take_where(table, np.arange(row_count(table)) < SMALL_N),
        parameters={"run": 2},
        run=SMALL_RUN,
    )
    return sample_copy / "m000.pto"


@pytest.fixture
def model(hermetic_env, container) -> MleViewModel:
    m = MleViewModel()
    m.set_setup(CHANNEL_SETTINGS)
    assert m.add_files([container]) == 1
    return m


def test_a_container_among_the_burst_files_lists_its_runs(model, container):
    assert model.run_container == str(container)
    rows = model.run_rows()
    assert [r["run_name"] for r in rows] == [BIG, SMALL_RUN]
    assert rows[0]["rows"] > rows[1]["rows"] == SMALL_N // 2


def test_picking_a_run_makes_that_run_the_burst_table(model, container):
    rows = model.run_rows()
    model.select_run(rows[1])
    assert [str(p) for p in model.session.bur_files] == [f"{container}/{SMALL_RUN}"]
    assert model.n_bursts == rows[1]["rows"]
    model.select_run(rows[0])
    assert model.n_bursts == rows[0]["rows"]
    # the photons are the container's own: no loose raw file was looked for
    assert list(model.session.tttr_paths.values()) == [container.resolve()]
    assert model.session.current_tttr() is not None


def test_the_picked_run_is_fitted_and_written_into_the_container(model, container):
    model.select_run(model.run_rows()[1])
    for det in model.session.detectors:
        model.session.current_detector = det
        model.session.auto_extract()
    model.run_batch()
    assert model.burst_results, model.status_text
    assert {str(r["First File"]) for r in model.burst_results} == {str(container.resolve())}

    assert model.export_results() >= 1
    with Measurement.open(container, writable=False) as m:
        names = [str(o.name) for o in m.artifacts()]
    assert any(n.endswith("mle green") for n in names), names
    assert not list(container.parent.glob("**/bg4")), "a container run must not write a b?4 folder"


def test_a_burst_table_of_the_other_run_is_not_fitted(model):
    rows = model.run_rows()
    model.select_run(rows[1])
    small = model.n_bursts
    model.select_run(rows[0])
    assert model.n_bursts > small


def test_the_view_spec_has_the_run_picker_once(model):
    import json

    from chisurf.plugins.burst.burst_mle_analysis.gui import native

    spec = json.loads(
        (Path(native.__file__).parent / "mle_native.view.json").read_text(encoding="utf-8")
    )
    assert with_run_picker(spec) == spec


def test_legacy_burst_files_still_load(hermetic_env, sample_copy):
    m = MleViewModel()
    m.set_setup(CHANNEL_SETTINGS)
    assert m.add_files([sample_copy / BURST_TABLE]) == 1
    assert m.run_container == "" and m.run_rows() == []
    assert not engine._is_container(m.session.bur_files[0])


def test_clicking_a_run_in_the_app_fits_that_run(hermetic_env, container):
    """Drop the container, click the small run's row in the Runs table: the burst table becomes that run."""
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
    from chisurf.plugins.emtk_test_input import Driver

    window = create_app()
    try:
        drv = Driver(window)
        window.model.set_setup(CHANNEL_SETTINGS)
        assert drv.drop(container)
        drv.draw()
        assert drv.drawn("Runs") or drv.drawn(BIG)
        # a bare container opens its newest run; the clicks pick the others
        drv.click_text(BIG)
        drv.draw()
        big = window.model.n_bursts
        assert window.model.run_path.endswith(f"m000.pto/{BIG}") and big > SMALL_N // 2
        drv.click_text(SMALL_RUN)
        drv.draw()
        assert window.model.n_bursts == SMALL_N // 2
        assert window.model.run_path.endswith(f"m000.pto/{SMALL_RUN}")
    finally:
        window.close()
