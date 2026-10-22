"""The IRF estimator's example: a seeded VV/VH decay with a known IRF start."""

import numpy as np

from chisurf.plugins.fluorescence_decay.irf_estimator.demo import (
    LIFETIMES_NS,
    demo_folder,
    make_demo,
)
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app


def test_make_demo_writes_a_vvvh_decay():
    """The demo decay loads in the VV/VH format and carries counts."""
    from chisurf.core.fio.vv_vh import read_vv_vh

    path = make_demo()
    data = read_vv_vh(str(path), split=True)
    vv = data["VV"] if isinstance(data, dict) else data[0]
    assert np.asarray(vv, dtype=float).max() > 100
    assert demo_folder() / "irf_demo_vvvh.dat" == path


def test_load_example_estimates_the_irf():
    """The affordance loads the decay and estimates; the lifetime lands near 1.1 ns."""
    app = make_app()
    model = app.model
    model.load_example()
    result = model.result
    assert result is not None
    assert abs(result.lifetime_ns - LIFETIMES_NS[0]) < 0.35
    assert model.status
