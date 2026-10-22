"""The FRC tool's example: a stack band-limited to 0.15 resolves near 1/0.15 px."""

import pytest

from chisurf.plugins.microscopy.img_frc.demo import CUTOFF, make_demo
from chisurf.plugins.microscopy.img_frc.gui.app import make_app
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_make_demo_writes_a_band_limited_stack():
    """The demo stack exists as a multi-page TIFF."""
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0


def test_load_example_resolves_the_band_limit():
    """The affordance loads and measures; the crossing sits at the injected cut-off."""
    app = make_app()
    driver = Driver(app, (1200, 800))
    driver.draw(3)
    app.load_example()
    driver.settle(120.0)
    result = app.model.result
    assert result is not None and result.crossed
    assert result.resolution == pytest.approx(1 / CUTOFF, rel=0.35)
    assert app.model.filename.endswith("frc_demo.tif")
