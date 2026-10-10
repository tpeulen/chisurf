"""The 2D-FLCS plot sources of the native model (the Qt tool tests, ported)."""

import numpy as np


def test_flc_app_builds_and_plot_sources_are_callable():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    app = make_app()
    # the declarative plot sources must be callable and return lists
    assert app.model.lifetime_series() == []
    assert app.model.correlation_series() == []


def test_plot_sources_render_after_results():
    from chisurf.plugins.fcs.flc_2d.gui.app import make_app

    model = make_app().model
    model._lifetime = {"tau": np.geomspace(0.3, 8, 10), "amp": np.ones(10)}
    model._correlation = [{"x": np.array([1e-3, 1e-2]), "y": np.array([2.0, 1.0]), "name": "auto"}]
    assert len(model.lifetime_series()) == 1
    assert len(model.correlation_series()) == 1
