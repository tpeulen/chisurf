"""The editor of a BFF-described model renders from the description alone."""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("IMP.bff")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _model():
    import chisurf.core.curve
    import chisurf.core.data
    import chisurf.core.fitting.fit as fitting
    from chisurf.core.models.description import for_family

    x = np.arange(128) * 0.048
    data = chisurf.core.data.DataCurve(x=x, y=np.full(128, 10.0), ey=np.full(128, 3.0))
    fit = fitting.Fit(model_class=for_family("tcspc_lifetime"), data=data)
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=np.exp(-0.5 * ((x - 1.0) / 0.08) ** 2)))
    model.set_scalar("period", 12.5)
    return model


def test_the_editor_renders_and_follows_the_topology(qapp):
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget

    model = _model()
    assert model.problem is not None, model.missing
    widget = AutoModelWidget(model)
    assert widget._layout.count() == len(model.view_spec().sections) + 1

    assert len(model.lifetimes.visible_parameters()) == 2
    model.structure = "lifetime.components.3"
    widget.rebuild()
    assert len(model.lifetimes.visible_parameters()) == 6
