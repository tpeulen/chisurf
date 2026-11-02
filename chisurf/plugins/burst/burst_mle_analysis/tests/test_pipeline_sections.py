"""In the pipeline Burst MLE shows no file list, no example to load and no notes on models it
cannot offer: its bursts are Burst Selection's. The standalone tool keeps all of it."""

from __future__ import annotations

from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
from chisurf.plugins.emtk_test_input import Driver

GONE = ("Load example", "unavailable here", "Folder")


def _strings(pipeline: bool) -> str:
    app = create_app()
    try:
        app.pipeline = pipeline
        return " ".join(Driver(app, (1100, 760)).draw(3).strings)
    finally:
        app.close()


def test_the_pipeline_step_draws_none_of_it(hermetic_env):
    drawn = _strings(True)
    assert not [g for g in GONE if g in drawn], drawn
    assert "Lifetime model" in drawn and "Fit model" in drawn


def test_the_standalone_tool_keeps_it(hermetic_env):
    drawn = _strings(False)
    assert "Load example" in drawn and "Folder" in drawn
