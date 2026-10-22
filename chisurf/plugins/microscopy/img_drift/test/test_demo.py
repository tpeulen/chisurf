"""The drift tool's example: the injected shift is what the measurement finds."""

import numpy as np

from chisurf.plugins.microscopy.demo_stack import DRIFT_STEP
from chisurf.plugins.microscopy.img_drift.demo import N_FRAMES, TRUE_SHIFTS, make_demo
from chisurf.plugins.microscopy.img_drift.gui.app import make_app
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_make_demo_writes_a_drifting_stack():
    """The demo stack exists and carries the declared drift."""
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0
    from chisurf.core.fio.image import imread

    stack = imread(str(path))
    assert stack.shape[0] == N_FRAMES


def test_load_example_measures_the_injected_drift():
    """The affordance loads the stack the way a dropped file arrives and measures it."""
    app = make_app()
    driver = Driver(app, (1200, 800))
    driver.draw(3)
    app.load_example()
    driver.settle(120.0)
    result = app.model.result
    assert result is not None
    np.testing.assert_allclose(np.asarray(result.shifts), np.asarray(TRUE_SHIFTS), atol=1.0)
    assert app.model.filename.endswith("drift_demo.tif")
