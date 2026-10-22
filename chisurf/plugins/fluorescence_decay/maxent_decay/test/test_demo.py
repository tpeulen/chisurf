"""The maximum-entropy tool's example: a seeded bi-exponential decay."""

import numpy as np

from chisurf.plugins.fluorescence_decay.maxent_decay.demo import (
    LIFETIMES_NS,
    demo_folder,
    make_demo,
)
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app


def test_make_demo_writes_a_two_column_decay():
    """The demo decay is the two-column text the model's load_file reads."""
    path = make_demo()
    table = np.loadtxt(path)
    assert table.shape[1] == 2
    assert table[:, 1].max() > 1000
    assert demo_folder() / "maxent_demo.dat" == path


def test_load_example_reconstructs():
    """The affordance loads the decay and reconstructs a lifetime spectrum."""
    app = make_app()
    model = app.model
    model.load_example()
    assert model.result is not None
    result = model.result
    pick = (lambda key: result[key]) if isinstance(result, dict) else (lambda key: getattr(result, key))
    amplitudes = np.asarray(pick("p"), dtype=float)
    assert amplitudes.sum() > 0
    taus = np.asarray(pick("tau"), dtype=float)
    peak = taus[int(np.argmax(amplitudes))]
    assert taus.min() <= LIFETIMES_NS[0] <= taus.max()
    assert peak < LIFETIMES_NS[1] * 3
