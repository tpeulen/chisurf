"""The panels follow the selection, and the tool jump resolves.

Construction only proves it did not crash, so these check the wiring that a
screenshot cannot: that selecting an object moves every dependent view of the view
model, and that the tool jump resolves to a real, importable factory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.pto import Measurement

DATA = Path(__file__).resolve().parents[4].parent / "test" / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="instrument test data missing")


@pytest.fixture
def container(tmp_path: Path) -> Path:
    raw = tmp_path / "m.ptu"
    shutil.copy(PTU, raw)
    n = 16
    with Measurement.create(raw) as m:
        bursts = m.put_table(
            "bursts",
            {"First Photon": np.arange(n, dtype=np.int64), "Np": np.arange(n, dtype=np.int32)},
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"M": 10},
            derived_from=m.instrument_uid,
        )
        m.put_curve(
            "decay",
            np.arange(64.0),
            np.exp(-np.arange(64.0) / 8.0),
            artifact_kind="tcspc_decay",
            operation_type="tcspc_histogram_computation",
            x_units="nanoseconds",
            y_units="counts",
            derived_from=bursts,
        )
    return tmp_path / "m.pto"


@pytest.fixture
def model(container: Path):
    from chisurf.plugins.core.pto_inspector.gui.view_model import PtoInspectorViewModel

    vm = PtoInspectorViewModel()
    vm.set_filename(str(container))
    yield vm
    vm.close()


def test_opening_selects_the_most_recent_result(model):
    """The first object is the README; the last is what was just computed."""
    assert model.selected is not None
    assert model.selected.name == "decay"


def test_opening_something_broken_reports_rather_than_raises(tmp_path: Path):
    from chisurf.plugins.core.pto_inspector.gui.view_model import PtoInspectorViewModel

    bad = tmp_path / "bad.pto"
    bad.write_bytes(b"nope")
    vm = PtoInspectorViewModel()
    vm.set_filename(str(bad))
    assert vm.inspection is None
    assert "Cannot open" in vm.status


def test_the_table_and_the_curve_follow_the_selection(model):
    """One selection, four views: they must not disagree about what is shown."""
    bursts = next(i for i in model.inspection.infos() if i.name == "bursts")
    model.select_uid(bursts.uid)
    assert model.current_store() is not None
    assert model.curve_series() == []
    assert "not a curve" in model.curve_axes()["x_label"]

    decay = next(i for i in model.inspection.infos() if i.name == "decay")
    model.select_uid(decay.uid)
    series = model.curve_series()
    assert len(series) == 1 and len(series[0]["x"]) == 64
    assert model.curve_axes()["x_label"] == "x [ns]"


def test_a_correlation_gets_a_log_axis_and_a_decay_does_not(model, container: Path):
    """The same plot shows both; only the data can say which scale is right."""
    with Measurement.open(container, writable=True) as m:
        m.put_curve(
            "fcs",
            np.logspace(-3, 3, 32),
            np.ones(32),
            artifact_kind="fcs_correlation",
            operation_type="fcs_correlation",
            x_units="milliseconds",
            y_units="dimensionless",
        )
    model.reload()
    fcs = next(i for i in model.inspection.infos() if i.name == "fcs")
    model.select_uid(fcs.uid)
    axes = model.curve_axes()
    assert axes["x_label"] == "x [ms]"
    assert axes["log_x"] is True

    decay = next(i for i in model.inspection.infos() if i.name == "decay")
    model.select_uid(decay.uid)
    axes = model.curve_axes()
    assert axes["x_label"] == "x [ns]"
    assert axes["log_x"] is False


def test_the_detail_panel_names_the_tool_for_a_claimed_step(model):
    bursts = next(i for i in model.inspection.infos() if i.name == "bursts")
    model.select_uid(bursts.uid)
    assert model.tool_manifests(), "burst_selection must resolve to a tool"
    assert "Open tool" in model.detail_html()


def test_an_unclaimed_step_says_so_instead_of_offering_a_button(model):
    decay = next(i for i in model.inspection.infos() if i.name == "decay")
    model.select_uid(decay.uid)
    assert model.tool_manifests() == []
    assert "No installed tool claims this step" in model.detail_html()


def test_the_graph_is_valid_and_carries_the_focus(model):
    from chisurf.emtk.node_editor.validation import validate_graph_dict

    graph = model.provenance_graph()
    validate_graph_dict(graph)
    assert graph["meta"]["focus"] == str(model.selected_uid)


def test_lineage_html_keeps_its_indentation(model):
    """HTML collapses leading spaces — the one thing that made it readable."""
    decay = next(i for i in model.inspection.infos() if i.name == "decay")
    model.select_uid(decay.uid)
    assert model.lineage_html().startswith("<pre")


# -- the tool jump -----------------------------------------------------------


def test_the_jump_resolves_to_an_importable_class(model):
    """The button must open something; a bad entry point is invisible otherwise."""
    import importlib

    bursts = next(i for i in model.inspection.infos() if i.name == "bursts")
    model.select_uid(bursts.uid)
    manifest = model.tool_manifests()[0]
    module_path, attr = manifest.entrypoints.emtk.rsplit(":", 1)
    assert getattr(importlib.import_module(module_path), attr) is not None
