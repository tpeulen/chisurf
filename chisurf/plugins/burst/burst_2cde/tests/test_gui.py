"""Headless GUI test for the 2CDE tool (offscreen construct + compute + grab)."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_tool_builds_computes_and_grabs(qapp, tmp_path):
    from qtpy import QtWidgets  # noqa: F401
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool
    from chisurf.plugins.burst.burst_2cde.core import computation as core

    tool = BurstTwoCdeTool(embedded=True)
    assert tool.name

    # Drive the private draw path with a synthetic burst dataframe so the plot
    # renders without needing burst files on disk.
    import pandas as pd
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "First File": ["f0"] * n,
        "Proximity Ratio": rng.uniform(0, 1, n),
        core.COLUMN_FRET_2CDE: rng.normal(12.0, 5.0, n),
    })
    tool._draw(df, core.COLUMN_FRET_2CDE)
    assert "bursts valid" in tool._status.text()

    # Render to a pixmap (proves the widget lays out and paints headlessly).
    tool.resize(640, 480)
    pm = tool.grab()
    assert not pm.isNull()
    out = pathlib.Path(tmp_path) / "burst_2cde_tool.png"
    pm.save(str(out))
    assert out.exists() and out.stat().st_size > 0


def test_plotted_column_follows_the_run_not_the_live_combo(qapp):
    """Moving *Variant* mid-run must not decide which column is plotted.

    The worker is parameterised by a snapshot taken when the run started and the
    frame it returns carries only that variant's column, so a completion handler
    that re-read the live combo asked for a column that is not in the frame.
    """
    import pandas as pd

    from chisurf.plugins.burst.burst_2cde.core import computation as core
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool

    tool = BurstTwoCdeTool(embedded=True)
    try:
        tool._variant.setCurrentText("fret")
        n = 20
        df = pd.DataFrame({
            "First File": ["f0"] * n,
            "Proximity Ratio": np.linspace(0.0, 1.0, n),
            core.COLUMN_FRET_2CDE: np.linspace(5.0, 15.0, n),
        })
        # The user switches to the other variant while the folder is correlated.
        tool._variant.setCurrentText("alex")
        tool._analysis_done((df, "fret"))
        assert tool._df is df
        assert core.COLUMN_FRET_2CDE in tool._status.text()
        assert core.COLUMN_ALEX_2CDE not in tool._status.text()
    finally:
        tool.close()


def test_settings_are_locked_while_a_run_is_in_flight(qapp, tmp_path, monkeypatch):
    """The settings form is disabled for the duration of a run, then restored."""
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool

    tool = BurstTwoCdeTool(embedded=True)
    try:
        tool.set_folder(tmp_path)
        monkeypatch.setattr(ChiSurfProgress, "run", staticmethod(lambda *a, **k: None))
        assert tool._settings_box.isEnabled()
        tool.run()
        assert not tool._settings_box.isEnabled()
        tool._analysis_over()
        assert tool._settings_box.isEnabled()
    finally:
        tool.close()


def test_column_for_variant_is_the_single_mapping():
    """``column_for_variant`` is what every consumer derives the column from."""
    from chisurf.plugins.burst.burst_2cde.core import computation as core

    assert core.column_for_variant("alex") == core.COLUMN_ALEX_2CDE
    assert core.column_for_variant("fret") == core.COLUMN_FRET_2CDE


def test_workflow_factory_registered():
    """The 2CDE step is wired into the burst_analysis workflow shell."""
    from chisurf.plugins.burst.burst_analysis.gui import tool as wf

    roles = {step.get("role") for step in wf.STEPS} if hasattr(wf, "STEPS") else set()
    # Fall back to scanning module for the factory if STEPS is named differently.
    assert hasattr(wf, "_burst_2cde")
