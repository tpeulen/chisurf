"""Tests for the Burst Fusion tool (Qt-free view model and native emtk app).

These drive the tool into a realistic state (a real burst folder analysed and written) and assert on what
the panels would *show* — the series the plots draw and the rows the summary
table lists.
"""

from __future__ import annotations

import pathlib
import shutil

import numpy as np
import pytest

DATA = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
ANALYSIS = "burstwise_All 0.1000#15"
DETECTORS = {
    "green": {"chs": [0, 8], "micro_time_ranges": [[0, 2048]]},
    "red": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
}


@pytest.fixture
def folder(tmp_path):
    if not DATA.is_dir():
        pytest.skip("burst-selection test data not available")
    target = tmp_path / "data"
    shutil.copytree(DATA, target)
    return target / ANALYSIS


class _Tool:
    """The view model with the workflow hand-off the retired Qt tool exposed."""

    def __init__(self, folder):
        from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

        self.model = FusionViewModel()
        self.model.detectors = dict(DETECTORS)
        self.model.windows = {"prompt": [0, 2048]}
        self.model.set_folder(str(folder))

    def output_folder(self):
        return self.model.written_folder


@pytest.fixture
def tool(folder):
    return _Tool(folder)


def test_view_spec_binds_every_source_it_names():
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


def test_tool_constructs_with_help_and_guide():
    """Both are in-EMTK buttons: the app carries a tour and help content."""
    from chisurf.plugins.burst.burst_fusion.gui.app import create_app

    app = create_app()
    try:
        gui = app.fusion_gui
        assert gui.tour.steps, "the plugin must ship a guided tour"
        assert gui.help_window.sections, "the plugin must ship help content"
    finally:
        app.close()


def _wait(app, timeout=120.0):
    import time

    end = time.monotonic() + timeout
    while app.controller.running or app.controller._future is not None:
        assert time.monotonic() < end, "the worker did not finish"
        time.sleep(0.01)
        app.controller.poll()


def test_the_run_button_is_the_one_that_fuses(folder):
    """Running a step must produce its output, not a preview of it.

    The controller's ``run`` is what *Run (Fuse)* and the workflow's run action
    call; if that only estimated, a user who ran the step and moved on would be
    analysing the un-fused bursts with nothing saying so.
    """
    from chisurf.plugins.burst.burst_fusion.gui.app import create_app

    app = create_app()
    try:
        app.set_channel_settings({"detectors": DETECTORS, "windows": {"prompt": [0, 2048]}})
        app.set_folder(str(folder))
        app.controller.estimate()
        _wait(app)
        assert app.model.has_analysis()
        assert app.model.written_folder == "", "estimating must write nothing"

        app.controller.run()
        _wait(app)
        assert pathlib.Path(app.model.written_folder).is_dir(), "running must write the folder"
    finally:
        app.close()


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
    assert float(rows["Photons (mean)"]["after"]) > float(rows["Photons (mean)"]["before"])


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
    tool.model.folder = str(other)  # what the bound field does
    tool.model.set_folder(str(other))  # ...and then the ``call``
    assert not tool.model.has_analysis()
    assert tool.model.summary_rows() == []


def test_reapplying_the_same_folder_keeps_the_analysis(tool):
    """The workflow re-applies its context on every step change."""
    tool.model.analyze()
    tool.model.set_folder(tool.model.folder)
    assert tool.model.has_analysis()


def test_loading_the_demo_selects_a_folder_with_a_known_answer(monkeypatch, tmp_path):
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    widget = _Tool.__new__(_Tool)
    widget.model = FusionViewModel()
    monkeypatch.setattr(
        "chisurf.plugins.burst.burst_fusion.demo.demo_folder",
        lambda: tmp_path / "demo",
    )
    widget.model.load_demo()

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


def test_running_without_a_folder_reports_instead_of_raising():
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    model = FusionViewModel()
    assert model.can_run() == "Select a burst-analysis folder first."
    with pytest.raises(ValueError):
        model.analyze()
