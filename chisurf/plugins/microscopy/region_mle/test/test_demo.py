"""The region-MLE panel's example: the spot-finder demo field, detected and ready."""

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.region_mle.demo import demo_folder, make_demo
from chisurf.plugins.microscopy.region_mle.gui.app import make_app


def test_make_demo_writes_the_demo_field():
    """The demo field is the spot finder's example, read in place."""
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0
    assert path.parent == demo_folder()


def test_load_example_loads_and_detects():
    """The affordance runs the tool's own demo load on the worker."""
    app = make_app()
    driver = Driver(app, (1200, 800))
    driver.draw(3)
    app.load_example()
    driver.settle(300.0)
    model = app.model
    assert model.sel_files
    assert model.sel_irf_files
