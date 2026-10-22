"""The tracking tool's example: six particles diffusing with D = 0.5 px²/frame."""

import pytest

from chisurf.plugins.microscopy.img_tracking.demo import DIFFUSION, make_demo
from chisurf.plugins.microscopy.img_tracking.gui.app import make_app
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_make_demo_writes_a_diffusing_movie():
    """The demo movie exists as a multi-page TIFF."""
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0


def test_load_example_tracks_and_fits():
    """The affordance selects the movie and tracks; the fit returns about the truth."""
    app = make_app()
    driver = Driver(app, (1200, 800))
    driver.draw(3)
    app.load_example()
    driver.settle(180.0)
    result = app.model.result
    assert result is not None
    assert len(result.tracks) >= 6
    assert result.fit is not None
    assert result.fit.diffusion_coefficient == pytest.approx(DIFFUSION, rel=0.6)
    assert app.model.filename.endswith("tracking_demo.tif")
