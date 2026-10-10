"""The run picker: rows from a container, and a choice that is a container path."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fio.analysis_path import is_container_path, read_tables
from chisurf.core.fio.fluorescence.burst_container import container_for, write_burst_artifact
from chisurf.plugins.core.pto_inspector.core import (
    RUN_PICKER_SECTION,
    RunPickerMixin,
    run_rows_for,
    with_run_picker,
)

PTU = Path(__file__).resolve().parents[1] / "data" / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="no instrument test data")


class Model(RunPickerMixin):
    run_picker_attr = "folder"

    def __init__(self, folder):
        self.folder = str(folder)
        self.events = []

    def notify(self, event):
        self.events.append(event)


@pytest.fixture
def container(tmp_path: Path) -> Path:
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    for run, threshold in (("countrate_All 0.1000#60", 60), ("countrate_All 0.2000#30", 30)):
        table = np.zeros(21)
        table[1::2] = np.arange(10) + threshold
        write_burst_artifact(
            raw,
            store_from_arrays({"Number of Photons": table}),
            name=f"{run}/bi4_bur/m000.bur",
            deinterleave=False,
            artifact_kind="burst_table",
            operation_type="burst_selection",
            algorithm="sliding_window",
            parameters={"min_photons": threshold},
            derived_from=(),
        )
    return container_for(raw)


def test_the_source_is_a_method_not_a_property():
    assert callable(Model.run_rows)
    assert not isinstance(Model.__dict__.get("run_rows", Model.run_rows), property)
    assert RUN_PICKER_SECTION["options"]["source"] == "run_rows"
    assert RUN_PICKER_SECTION["options"]["selected_call"] == "select_run"


def test_run_rows_lists_the_runs_of_a_container(container):
    rows = Model(container).run_rows()
    assert [r["run_name"] for r in rows] == ["countrate_All 0.1000#60", "countrate_All 0.2000#30"]
    assert {r["operation"] for r in rows} == {"burst_selection"}
    assert {r["algorithm"] for r in rows} == {"sliding_window"}
    assert [r["rows"] for r in rows] == [10, 10]  # bursts, not the file's 2n+1 padded rows
    assert len({r["settings_hash"] for r in rows}) == 2
    assert [r["created"] for r in rows] == [1, 2]


def test_a_vendor_file_or_nothing_lists_no_runs(tmp_path):
    assert run_rows_for(tmp_path / "m000.ptu") == []
    assert run_rows_for("") == []
    assert Model("").run_rows() == []


def test_select_run_gives_a_container_path_every_reader_accepts(container):
    model = Model(container)
    model.select_run(model.run_rows()[0])
    assert model.run_path == f"{container}/countrate_All 0.1000#60"
    assert is_container_path(model.run_path)  # not Path.is_file: the run is no file
    assert "m000.bur" in "".join(read_tables(model.run_path))
    assert model.events == ["run_selected"]
    model.select_run(None)  # a cleared selection leaves the choice alone
    assert model.run_path.endswith("#60")


def test_the_picker_is_spliced_once_under_the_input_table():
    spec = {
        "sections": [
            {"type": "panel", "title": "Files", "sections": [{"type": "custom", "key": "data_table"}]},
            {"type": "panel", "title": "Settings", "sections": []},
        ]
    }
    spliced = with_run_picker(spec)
    inner = spliced["sections"][0]["sections"]
    assert [s.get("title", s["key"]) for s in inner] == ["data_table", "Runs"]
    assert with_run_picker(spliced) == spliced
    assert "Runs" not in str(spec)  # the original is untouched


def test_a_snapshot_job_does_not_mistake_the_picker_for_a_collection():
    """`run_rows` is a list attribute on some models and the picker's method on others."""
    import time

    from chisurf.emtk.jobs import SnapshotJob

    class Busy(RunPickerMixin):
        files = ["a"]

        def __init__(self):
            self._observers = []
            self.done = False

        def notify(self, _event):
            pass

        def work(self):
            self.done = True

    model = Busy()
    job = SnapshotJob(model)
    assert job.start("work")
    end = time.monotonic() + 5
    while job.busy and time.monotonic() < end:
        time.sleep(0.01)
        job.poll()
    job.poll()
    assert job.error == "" and model.done
