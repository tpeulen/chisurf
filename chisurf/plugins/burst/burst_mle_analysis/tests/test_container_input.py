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


def feed(app, *paths) -> bool:
    """Hand burst runs over as the workspace does (Input section / Open in… / a drag); False when
    nothing new was taken."""
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import receive_bursts

    try:
        receive_bursts(app, {"files": [str(p) for p in paths], "datasets": []})
    except ValueError:
        return False
    app.draw(
        __import__("emtk.testing", fromlist=["RecordingPainter"]).RecordingPainter(),
        0,
        0,
        1200,
        800,
    )
    return True


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
    picked = model.run_rows()[1]["run"]
    model.select_run(model.run_rows()[1])
    for det in model.session.detectors:
        model.session.current_detector = det
        model.session.auto_extract()
    model.run_batch()
    assert model.burst_results, model.status_text
    # Each batch row names the search it was fitted from, not just the container.
    assert {str(r["First File"]) for r in model.burst_results} == {
        str(container.resolve() / picked)
    }

    assert model.export_results() >= 1
    with Measurement.open(container, writable=False) as m:
        names = {o.uid: str(o.name) for o in m._f.objects()}
        fits = [o for o in m.artifacts() if str(o.name).endswith("mle G|G")]
        assert fits, list(names.values())
        # The parent is the picked search, whichever of the two is the newest.
        assert [names[u] for u in m.parents(fits[0].uid)][0].startswith(f"{picked}/")
    assert not list(container.parent.glob("**/bg4")), "a container run must not write a b?4 folder"


def test_a_burst_table_of_the_other_run_is_not_fitted(model):
    rows = model.run_rows()
    model.select_run(rows[1])
    small = model.n_bursts
    model.select_run(rows[0])
    assert model.n_bursts > small


def test_the_view_spec_has_no_run_picker_of_its_own(model):
    """The runs are rows of the Datasets workspace (the Input section lists them), so the form does
    not list a container's runs a second time."""
    from chisurf.plugins.burst.burst_mle_analysis.gui import native

    text = (Path(native.__file__).parent / "mle_native.view.json").read_text(encoding="utf-8")
    assert "run_rows" not in text and "select_run" not in text


def test_legacy_burst_files_are_refused(hermetic_env, sample_copy):
    """Q1 hard: the legacy .bur tree is not an input; only .pto containers are."""
    m = MleViewModel()
    m.set_setup(CHANNEL_SETTINGS)
    assert m.add_files([sample_copy / BURST_TABLE]) == 0
    assert m.session.bur_files == []
    assert "No new .pto" in m.status_text


def test_picking_a_run_in_the_input_section_fits_that_run(hermetic_env, container):
    """The container's runs are workspace rows (the drop puts them there); the run picked in the
    Input section is the burst table the fit reads."""
    from chisurf.core.api import dataset_container
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
    from chisurf.plugins.burst.workspace_io import register_container
    from chisurf.plugins.emtk_test_input import Driver

    held = dataset_container()
    before = list(held)
    window = create_app()
    try:
        register_container(container)
        drv = Driver(window)
        window.model.set_setup(CHANNEL_SETTINGS)
        drv.draw()
        assert drv.drawn(BIG) and drv.drawn(SMALL_RUN)
        model = window.inputs["bursts"][0]
        for run, n in ((SMALL_RUN, SMALL_N // 2), (BIG, None)):
            window.model.clear_files()
            model.workspace_input_selection = [
                r for r in model.workspace_input_rows() if r["name"] == run
            ]
            drv.click_name("workspace_input_use")
            drv.draw()
            assert [p.name for p in window.model.session.bur_files] == [run]
            if n is not None:
                assert window.model.n_bursts == n
            else:
                assert window.model.n_bursts > SMALL_N // 2
    finally:
        window.close()
        held[:] = before


def test_an_unchanged_request_is_not_fitted_again_and_restart_fits(model, monkeypatch):
    """The reuse gate of the retired Qt wizard: same files + settings -> keep the rows."""

    model.select_run(model.run_rows()[1])
    for det in model.session.detectors:
        model.session.current_detector = det
        model.session.auto_extract()
    real = engine.MleSession.run_batch
    calls = []

    def counted(self, *a, **k):
        calls.append(1)
        return real(self, *a, **k)

    monkeypatch.setattr(engine.MleSession, "run_batch", counted)
    model.run_batch()
    rows = model.burst_results
    assert rows and len(calls) == 1 and not model.restart_attention

    model.run_batch()  # nothing changed
    assert len(calls) == 1 and model.burst_results is rows
    assert model.status_text.startswith("Unchanged") and model.restart_attention

    model.run_batch(force=True)  # Restart
    assert len(calls) == 2 and not model.restart_attention

    # a changed setting is a different request
    det = next(iter(model.session.detectors))
    model.session.det_settings[det].min_photons += 1
    model.run_batch()
    assert len(calls) == 3
    assert "Unchanged" not in model.status_text
