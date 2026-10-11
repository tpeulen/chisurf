"""The pipeline hubs draw >> (fast-forward), which their help and guides 27 and 66 tell the user to press.

``BurstAnalysisHubApp`` (and the ALEX Suite built on it) did not pass ``steps=True`` to the tool hub, so the
button was never drawn and "**>>** walks the remaining steps" pointed at nothing.
"""

import pytest
from emtk.testing import Driver


@pytest.mark.parametrize(
    "factory",
    [
        "chisurf.plugins.burst.burst_analysis.gui.native:create_app",
        "chisurf.plugins.burst.alex_suite.gui.native:make_app",
    ],
)
def test_fast_forward_is_drawn(factory, tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    module, name = factory.split(":")
    app = getattr(importlib.import_module(module), name)()
    try:
        driver = Driver(app, (1400, 860))
        driver.frame(3)
        assert app.steps is True
        assert "fast_forward" in driver.ids()
    finally:
        close = getattr(app, "close", None)
        if callable(close):
            close()
