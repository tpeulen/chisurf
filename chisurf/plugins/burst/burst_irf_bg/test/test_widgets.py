"""Headless tests for the Burst IRF & Background tool.

Exercises the Qt-free view-model (compute + MLE-pattern accessors) on real
single-molecule SPC data and a lightweight widget-construction smoke test.
"""

from __future__ import annotations

import pathlib

import pytest

DATA = (
    pathlib.Path(__file__).resolve().parents[3]
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)
DETECTORS = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}


def test_view_model_compute_and_mle_patterns():
    """The model extracts IRF/background and vv_vh MLE patterns from non-burst photons."""
    pytest.importorskip("tttrlib")
    if not DATA.exists():
        pytest.skip("sample SPC not available")

    from chisurf.plugins.burst.burst_irf_bg.gui.view_model import IrfBackgroundViewModel

    m = IrfBackgroundViewModel()
    m.add_files([str(DATA)])
    m.channels_provider = lambda: DETECTORS
    m.min_photons = 20
    m.micro_time_binning = 2
    m.compute()

    rows = m.results_rows()
    assert {r["detector"] for r in rows} == {"green", "red"}
    for r in rows:
        assert r["background_khz"] >= 0.0
        assert r["n_bg"] > r["n_burst"]

    series = m.irf_series()
    assert series and len(series[0]["x"]) == len(series[0]["y"])

    patterns = m.mle_patterns()
    assert set(patterns) == {"green", "red"}
    for pat in patterns.values():
        # VV/VH-stacked [parallel, perpendicular]: even length, non-empty.
        assert pat["irf"].size == pat["bg"].size
        assert pat["irf"].size % 2 == 0
        assert pat["bg"].sum() > 0


def test_compute_requires_files_and_channels():
    """can_compute reports the missing prerequisite instead of raising blindly."""
    from chisurf.plugins.burst.burst_irf_bg.gui.view_model import IrfBackgroundViewModel

    m = IrfBackgroundViewModel()
    assert m.can_compute() == "Please load TTTR files first."
    m.add_files(["/does/not/matter.spc"])
    assert "detectors" in (m.can_compute() or "")


def test_widget_creation(qapp, qtbot):
    """The AutoForm tool constructs and registers its custom sections."""
    pytest.importorskip("pyqtgraph")
    pytest.importorskip("tttrlib")
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.registry import get_section_factory
    from chisurf.plugins.burst.burst_irf_bg.gui.tool import BurstIrfBackgroundTool

    widget = BurstIrfBackgroundTool()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "IRF" in widget.windowTitle()
    assert isinstance(widget.auto_form, AutoForm)
    for key in ("irf_bg_channels", "irf_bg_run", "irf_bg_results", "path_list"):
        assert get_section_factory(key) is not None
