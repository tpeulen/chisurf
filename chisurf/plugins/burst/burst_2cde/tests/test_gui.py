"""The native 2CDE app's plot, status and variant handling (the Qt-free model and controller)."""

from __future__ import annotations

import pathlib

import numpy as np


def _frame(core, column, n=200, seed=0):
    import pandas as pd

    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "First File": ["f0"] * n,
            "Proximity Ratio": rng.uniform(0, 1, n),
            column: rng.normal(12.0, 5.0, n),
        }
    )


def test_app_draws_a_result_and_reports_valid_bursts(tmp_path):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.burst.burst_2cde.core import computation as core
    from chisurf.plugins.burst.burst_2cde.gui.app import create_app

    app = create_app()
    try:
        app.model.set_result(_frame(core, core.COLUMN_FRET_2CDE), "fret")
        assert "bursts valid" in app.model.status_text
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 640, 480)
        assert painter.strings
    finally:
        app.close()


def test_plotted_column_follows_the_run_not_the_live_variant():
    """Moving *Variant* mid-run must not decide which column is plotted.

    The worker is parameterised by a snapshot taken when the run started and the frame it returns carries only
    that variant's column, so a completion that re-read the live variant asked for a column that is not in it.
    """
    from chisurf.plugins.burst.burst_2cde.core import computation as core
    from chisurf.plugins.burst.burst_2cde.gui.view_model import TwoCdeViewModel

    model = TwoCdeViewModel()
    model.variant = "fret"
    df = _frame(core, core.COLUMN_FRET_2CDE, n=20)
    model.variant = "alex"  # the user switches while the folder is computed
    model.set_result(df, "fret")
    assert model.df is df
    assert core.COLUMN_FRET_2CDE in model.status_text
    assert core.COLUMN_ALEX_2CDE not in model.status_text


def test_a_dropped_folder_is_adopted(tmp_path, monkeypatch):
    """A folder dropped on the window is taken exactly as Browse takes one."""
    from chisurf.plugins.burst.burst_2cde.gui.app import create_app

    app = create_app()
    try:
        runs = []
        monkeypatch.setattr(app.controller, "run", lambda *a, **k: runs.append(True))
        app.controller.on_paths_dropped([pathlib.Path(tmp_path)])
        assert app.model.folder == str(tmp_path)
        assert runs == [True]
    finally:
        app.close()


def test_column_for_variant_is_the_single_mapping():
    """``column_for_variant`` is what every consumer derives the column from."""
    from chisurf.plugins.burst.burst_2cde.core import computation as core

    assert core.column_for_variant("alex") == core.COLUMN_ALEX_2CDE
    assert core.column_for_variant("fret") == core.COLUMN_FRET_2CDE


def test_the_burst_hub_lists_the_2cde_step():
    """The 2CDE step is wired into the native burst-analysis hub."""
    from chisurf.plugins.burst.burst_analysis.gui.native import STEPS

    step = next(s for s in STEPS if s.get("role") == "two_cde")
    assert step["plugin"] == "burst/burst_2cde"
