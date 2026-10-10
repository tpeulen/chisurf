"""Burst FCS correlates a run of a measurement's ``.pto`` and writes the diffusion times back into it.

The Runs table lists the burst searches of the container among the inputs; the one picked is the burst table that is
correlated, over the container's own photons. The data is the demonstration stream (8 bursts, two detectors) packed into
a container with a full run and a run of its first three bursts.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import numeric_column
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_fcs_correlator import demo
from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms as core
from chisurf.plugins.burst.burst_fcs_correlator.gui.controller import BurstFcsController
from chisurf.plugins.burst.burst_selection.api.io import write_container
from chisurf.plugins.core.pto_inspector.core import with_run_picker

from .driving import BIG, BurstDriver, hermetic_env

FULL, FIRST3 = "runFull#1", "runFirst3#2"
PAIRS = [{"pair_name": "ACF_0", "chs_a": [0], "chs_b": [0]}]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


def burst_table(ranges) -> pd.DataFrame:
    """A burst table as the container stores it: zero rows between the bursts, as a ``.bur`` has them."""
    n = len(ranges)
    table = pd.DataFrame(
        {"First Photon": np.zeros(2 * n + 1), "Last Photon": np.zeros(2 * n + 1), "First File": ["0"] * (2 * n + 1)}
    )
    table.loc[1::2, "First Photon"] = [a for a, _ in ranges]
    table.loc[1::2, "Last Photon"] = [b for _, b in ranges]
    table.loc[1::2, "First File"] = demo.SPC_FILENAME
    return table


@pytest.fixture
def container(tmp_path) -> Path:
    """``<tmp>/burst_fcs_demo.pto``: the demo's photons with a full and a three-burst search."""
    raw = demo.make_demo(tmp_path / "demo").parent / demo.SPC_FILENAME
    ranges = demo.photon_stream()[3]
    write_container(raw, burst_table(ranges), parameters={"run": 1}, run=FULL)
    write_container(raw, burst_table(ranges[:3]), parameters={"run": 2}, run=FIRST3)
    return raw.with_suffix(".pto")


def wait(ctrl: BurstFcsController, timeout: float = 60.0) -> None:
    end = time.monotonic() + timeout
    while ctrl._future is not None and time.monotonic() < end:
        time.sleep(0.02)
        ctrl.poll()
    assert ctrl._future is None and not ctrl.running


def test_a_run_of_a_container_has_one_range_per_burst_row(container):
    raw, ranges = core.parse_burst_container(f"{container}/{FIRST3}")
    assert raw == container.resolve() and len(ranges) == 3
    assert all(stop > start for start, stop in ranges)


def test_picking_a_run_correlates_that_run_and_writes_into_the_container(container):
    ctrl = BurstFcsController()
    try:
        ctrl.apply_pairs(__import__("json").dumps(PAIRS))
        ctrl.add_files([str(container)])
        rows = ctrl.run_rows()
        assert [r["run_name"] for r in rows] == [FULL, FIRST3]
        ctrl.select_run(rows[1])
        assert ctrl.files == [f"{container}/{FIRST3}"]
        ctrl._on_run()
        wait(ctrl)
        assert {c["burst_index"] for c in ctrl._curves} <= {0, 1, 2}
        assert ctrl._curves, ctrl.status
        with Measurement.open(container, writable=False) as m:
            table = m.get_store("burst fcs")
        assert set(numeric_column(table, "Burst Index")) <= {0.0, 1.0, 2.0}
        assert not list(container.parent.glob("**/td4"))

        ctrl.select_run(rows[0])
        assert ctrl._curves == [] and ctrl.files == [f"{container}/{FULL}"]
        ctrl._on_run()
        wait(ctrl)
        assert max(c["burst_index"] for c in ctrl._curves) > 2
    finally:
        ctrl.close()


def test_the_view_spec_has_the_run_picker_once():
    import json

    from chisurf.plugins.burst.burst_fcs_correlator.gui import app

    section = json.loads((Path(app.__file__).parent / "burst_fcs_emtk.view.json").read_text(encoding="utf-8"))["files"]
    assert with_run_picker(section) == section


def test_clicking_a_run_in_the_window_selects_it(container):
    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    try:
        drv = BurstDriver(app, BIG)
        assert drv.drop(container)
        drv.draw(3)
        assert app.controller.files == [str(container)]
        drv.click_text(FULL)
        drv.draw(2)
        assert app.controller.files == [f"{container}/{FULL}"]
        drv.click_text(FIRST3)
        drv.draw(2)
        assert app.controller.files == [f"{container}/{FIRST3}"]
    finally:
        app.close()
