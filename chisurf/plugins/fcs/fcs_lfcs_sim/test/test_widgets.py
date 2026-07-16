"""Headless GUI tests for the lifetime-FCS simulator panel."""

from __future__ import annotations

import numpy as np
import pytest
from qtpy import QtWidgets


def test_lfcs_widget_builds(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget

    widget = LifetimeFcsSimWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm rendered the parameter model, defaults are present.
    assert widget._model.tau1_ns == 1.0
    assert widget._model.tau2_ns == 4.0


def test_lfcs_widget_refresh_plot(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget

    widget = LifetimeFcsSimWidget()
    qtbot.addWidget(widget)
    datasets = [
        {"x": [1e-3, 1e-2, 1e-1], "y": [2.0, 1.5, 1.0], "species_a": 0, "species_b": 0, "name": "auto0"},
        {"x": [1e-3, 1e-2, 1e-1], "y": [3.0, 2.0, 1.0], "species_a": 1, "species_b": 1, "name": "auto1"},
        {"x": [1e-3, 1e-2, 1e-1], "y": [1.0, 1.2, 1.0], "species_a": 0, "species_b": 1, "name": "cross"},
    ]
    widget._refresh_plot(datasets)
    # three curves plotted (two autos + one cross)
    assert len(widget._plot.plotItem.listDataItems()) == 3


def test_lfcs_widget_simulate(qapp, qtbot):
    pytest.importorskip("tttrlib")
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget

    if not hasattr(pytest.importorskip("tttrlib"), "SimEngine"):
        pytest.skip("tttrlib build lacks SimEngine")

    widget = LifetimeFcsSimWidget()
    qtbot.addWidget(widget)
    widget._model.n_photons = 120_000  # keep the simulation quick for CI
    widget.simulate()
    datasets = widget._model.datasets
    # two species -> two auto-correlations + one cross-correlation
    pairs = {(d["species_a"], d["species_b"]) for d in datasets}
    assert pairs == {(0, 0), (1, 1), (0, 1)}
    assert np.isfinite(widget._model.condition_number)
    assert len(widget._plot.plotItem.listDataItems()) == 3
