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


def test_workflow_factory_registered():
    """The 2CDE step is wired into the burst_analysis workflow shell."""
    from chisurf.plugins.burst.burst_analysis.gui import tool as wf

    roles = {step.get("role") for step in wf.STEPS} if hasattr(wf, "STEPS") else set()
    # Fall back to scanning module for the factory if STEPS is named differently.
    assert hasattr(wf, "_burst_2cde")
