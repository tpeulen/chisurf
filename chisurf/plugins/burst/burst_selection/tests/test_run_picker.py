"""Burst Selection's Runs table and *Decay from selected bursts*, on a container with a real photon stream."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import tttrlib

SPC = Path(__file__).resolve().parents[5] / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
RUN = "countrate_All 0.1000#60"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no instrument test data")


@pytest.fixture
def model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    (tmp_path / "settings").mkdir()
    from chisurf.core.fio.fluorescence.burst_container import container_for
    from chisurf.plugins.burst.burst_selection.api.io import write_container
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    raw = tmp_path / "m000.spc"
    shutil.copy(SPC, raw)
    n_photons = len(tttrlib.TTTR(str(raw), "SPC-130"))
    edges = np.linspace(0, n_photons - 1, 9).astype(int)
    n = 4
    table = pd.DataFrame(
        {
            "First Photon": np.zeros(2 * n + 1),
            "Last Photon": np.zeros(2 * n + 1),
            "First File": ["0"] * (2 * n + 1),
        }
    )
    table.loc[1::2, "First Photon"] = edges[0:8:2]
    table.loc[1::2, "Last Photon"] = edges[1:8:2]
    table.loc[1::2, "First File"] = "m000.spc"
    write_container(raw, table, parameters={"min_photons": 3}, run=RUN)
    m = BurstSelectionModel(client=object())
    m.files = [container_for(raw)]
    return m


def test_the_runs_table_lists_the_container_of_the_file_on_show(model):
    rows = model.run_rows()
    assert [r["run_name"] for r in rows] == [RUN] and rows[0]["rows"] == 4
    model.select_run(rows[0])
    assert model.run_path.endswith(f"m000.pto/{RUN}")


def test_decay_from_selected_bursts_writes_the_decay_beside_the_run(model):
    from chisurf.core.fio.analysis_path import read_tables
    from chisurf.core.datastore import numeric_column

    verdict = model.write_decay()
    assert verdict.startswith("Decay of "), verdict
    decay = read_tables(model.run_path)["sub-ensemble decay"]
    assert numeric_column(decay, "Counts").sum() > 0
    assert str(int(numeric_column(decay, "Counts").sum())) in verdict


def test_without_a_container_there_is_no_run_to_take_a_decay_from(tmp_path):
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    m = BurstSelectionModel(client=object())
    assert m.run_rows() == []
    assert "No run to take a decay from" in m.write_decay()
