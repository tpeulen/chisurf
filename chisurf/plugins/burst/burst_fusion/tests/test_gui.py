"""Offscreen-Qt tests for the Burst Fusion tool.

Construction only proves it does not crash, so these also drive the tool into a
realistic state (a real burst folder analysed and written) and assert on what
the panels would *show* — the series the plots draw and the rows the summary
table lists.
"""

from __future__ import annotations

import os
import pathlib
import shutil

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
)
ANALYSIS = "burstwise_All 0.1000#15"
DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
    "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
}


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def folder(tmp_path):
    if not DATA.is_dir():
        pytest.skip("burst-selection test data not available")
    target = tmp_path / "data"
    shutil.copytree(DATA, target)
    return target / ANALYSIS


@pytest.fixture
def tool(qapp, folder):
    from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool

    widget = BurstFusionTool()
    widget.set_channel_settings({"detectors": DETECTORS, "windows": {"prompt": [0, 2048]}})
    widget.set_folder(str(folder))
    return widget


def test_view_spec_binds_every_source_it_names(qapp):
    """A ``source`` that is not a model *method* renders blank with no error."""
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    model = FusionViewModel()
    spec = model.view_spec()
    sources = [
        str(getattr(section, "source", ""))
        for section in spec.flat_sections()
        if getattr(section, "source", "")
    ]
    assert sources
    for source in sources:
        attribute = getattr(model, source, None)
        assert callable(attribute), f"{source!r} must be a method of the view model"
        assert attribute() is not None


def test_tool_constructs_with_help_and_guide(tool):
    """Both are toolbar *widgets*, so they are found by their button text."""
    from qtpy import QtWidgets

    labels = [
        button.text()
        for bar in tool.findChildren(QtWidgets.QToolBar)
        for button in bar.findChildren(QtWidgets.QToolButton)
    ]
    assert any("Guide" in label for label in labels), labels
    assert any("?" in label for label in labels), labels


def test_the_run_button_carries_the_canonical_object_name(tool):
    """The workflow shell drives a step by clicking its ``toolAction_run``."""
    from qtpy import QtWidgets

    assert tool.findChild(QtWidgets.QToolButton, "toolAction_run") is not None
    assert tool.findChild(QtWidgets.QToolButton, "toolAction_save") is not None


def test_analyze_populates_every_plot_and_the_summary(tool):
    tool.model.analyze()
    model = tool.model

    assert model.has_analysis()
    curve = model.p_same_series()
    assert len(curve) == 3, "the curve, the threshold line and the fused window"
    assert curve[0]["x"].size > 10

    for series in (model.proximity_series(), model.photon_series(), model.duration_series()):
        assert len(series) == 2, "before and after"
        assert np.isfinite(series[0]["y"]).all()
        assert series[1]["name"] == "fused (preview)"

    rows = {row["quantity"]: row for row in model.summary_rows()}
    assert int(rows["Bursts"]["after"]) < int(rows["Bursts"]["before"])
    assert rows["PR mean"]["after"] != "—"
    assert "P(same molecule)" in model.status_text()


def test_writing_switches_the_plots_to_what_was_written(tool):
    tool.model.analyze()
    written = tool.model.write()

    assert pathlib.Path(written).is_dir()
    assert tool.output_folder() == written
    series = tool.model.proximity_series()
    assert series[1]["name"] == "fused (written)"
    # The emitted bursts also contain the photons between the fragments, so they
    # are brighter than the preview's fragment sums.
    rows = {row["quantity"]: row for row in tool.model.summary_rows()}
    assert float(rows["Photons (mean)"]["after"]) > float(
        rows["Photons (mean)"]["before"]
    )


def test_the_written_folder_is_announced_to_the_workflow(tool):
    seen = []
    tool.model.folder_written = seen.append
    tool.model.analyze()
    written = tool.model.write()
    assert seen == [written]


def test_changing_a_setting_drops_a_stale_analysis(tool):
    tool.model.analyze()
    assert tool.model.has_analysis()
    tool.model.threshold = 0.9
    assert not tool.model.has_analysis(), "a stale preview must not survive its settings"
    assert tool.model.p_same_series() == []


def test_setting_the_folder_through_the_form_drops_the_old_analysis(tool, tmp_path):
    """AutoForm writes the attribute and *then* calls the setter.

    A guard comparing against ``self.folder`` therefore sees the new value
    already in place, returns early, and leaves the previous folder's analysis on
    screen under the new folder's name.
    """
    tool.model.analyze()
    assert tool.model.has_analysis()

    other = tmp_path / "elsewhere"
    other.mkdir()
    tool.model.folder = str(other)      # what the bound field does
    tool.model.set_folder(str(other))   # ...and then the ``call``
    assert not tool.model.has_analysis()
    assert tool.model.summary_rows() == []


def test_reapplying_the_same_folder_keeps_the_analysis(tool):
    """The workflow re-applies its context on every step change."""
    tool.model.analyze()
    tool.model.set_folder(tool.model.folder)
    assert tool.model.has_analysis()


def test_loading_the_demo_selects_a_folder_with_a_known_answer(qapp, monkeypatch, tmp_path):
    from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool

    widget = BurstFusionTool()
    monkeypatch.setattr(
        "chisurf.plugins.burst.burst_fusion.demo.demo_directory",
        lambda directory=None: tmp_path / "demo",
    )
    widget.load_demo()

    assert pathlib.Path(widget.model.folder).is_dir()
    assert widget.model.demo is not None
    assert widget.model.demo["truth"]["n_molecules"] > 0
    # The declared truth is on screen beside the result, which is the point.
    status = widget.model.status_text()
    assert "molecules" in status and str(widget.model.demo["bursts"]) in status

    widget.model.threshold = 0.7
    widget.model.analyze()
    statistics = widget.model.analysis.statistics
    assert statistics["n_bursts_after"] < statistics["n_bursts_before"]


def test_running_without_a_folder_reports_instead_of_raising(qapp):
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    model = FusionViewModel()
    assert model.can_run() == "Select a burst-analysis folder first."
    with pytest.raises(ValueError):
        model.analyze()


def test_guided_tour_steps_point_at_real_widgets(tool):
    """A tour step whose target does not resolve is shown centred and useless."""
    from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour
    from chisurf.plugins.burst.burst_fusion.gui import view_model

    guide = pathlib.Path(view_model.__file__).parent / "guide.json"
    steps = load_tour(guide)
    assert steps, "the plugin must ship a guided tour"

    tour = GuidedTour(tool, steps)
    for step in steps:
        assert tour.resolve_target(step.target) is not None, step.title
