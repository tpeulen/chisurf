"""The distance-component widgets must forward ``append`` arguments.

``GaussianWidget`` and ``DiscreteDistanceWidget`` wrap the core parameter groups
to also build an editor group box.  Both used to swallow ``*args, **kwargs`` and
call the core ``append`` with the editor defaults, so a script or the public
model API asking for ``append(mean=35.0, sigma=4.0)`` silently got a 50 A / 6 A
component — no error, just wrong numbers (PRD-46).
"""

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit

#: Every fit built here, kept alive for the whole module.
#:
#: Collecting a :class:`Fit` that owns Qt model widgets between two tests
#: intermittently kills the interpreter with a bus error while the shared
#: ``QApplication`` is still up.  The crash is a pre-existing widget-lifetime
#: hazard, not something these tests exercise, so nothing here is released
#: before the process ends.
_FITS: list = []


@pytest.fixture(scope="module")
def build_model(qapp):
    """Return a factory building a TCSPC model that stays alive."""

    def _build(model_class):
        time = np.linspace(0.0, 25.0, 64)
        data = DataCurve(x=time, y=np.ones_like(time))
        fit = Fit(model_class=model_class, data=data)
        _FITS.append(fit)
        return fit.model

    return _build


def test_gaussian_widget_append_keeps_requested_values(build_model):
    """``gaussians.append(mean=..., sigma=..., x=...)`` reaches the parameters."""
    from chisurf.gui.widgets.models.tcspc import GaussianModelWidget

    model = build_model(GaussianModelWidget)
    while len(model.gaussians) > 0:
        model.gaussians.pop()
    model.gaussians.append(mean=35.0, sigma=4.0, x=1.0)
    model.gaussians.append(mean=70.0, sigma=8.0, x=3.0)

    assert len(model.gaussians) == 2
    np.testing.assert_allclose(model.gaussians.mean, [35.0, 70.0])
    np.testing.assert_allclose(model.gaussians.sigma, [4.0, 8.0])
    np.testing.assert_allclose(model.gaussians.amplitude, [0.25, 0.75])


def test_gaussian_widget_append_defaults_unchanged(build_model):
    """The argument-free call the "add component" button makes still adds 50 A / 6 A.

    That entry point is ``append_gaussian()`` on the core group. It used to be an
    ``append()`` override on the Qt wrapper, which is why the editor's defaults
    could drift from the model's -- they now live in one place, and the
    generated editor's add button calls this method by name from the view spec.
    """
    from chisurf.gui.widgets.models.tcspc import GaussianModelWidget

    model = build_model(GaussianModelWidget)
    while len(model.gaussians) > 0:
        model.gaussians.pop()
    model.gaussians.append_gaussian()

    assert float(model.gaussians.mean[0]) == pytest.approx(50.0)
    assert float(model.gaussians.sigma[0]) == pytest.approx(6.0)


def test_freshly_built_widgets_carry_the_default_component(build_model):
    """The component both widgets seed themselves with is 50 A (6 A wide).

    Both constructors used to pass their seed positionally in *amplitude-first*
    order into an ``append`` that ignored every argument, so the scrambled order
    was invisible.
    """
    from chisurf.gui.widgets.models.tcspc import FRETrateModelWidget
    from chisurf.gui.widgets.models.tcspc import GaussianModelWidget

    gaussian = build_model(GaussianModelWidget)
    assert float(gaussian.gaussians.mean[0]) == pytest.approx(50.0)
    assert float(gaussian.gaussians.sigma[0]) == pytest.approx(6.0)

    discrete = build_model(FRETrateModelWidget)
    assert float(discrete.fret_rates.distance[0]) == pytest.approx(50.0)


def test_gaussian_widget_matches_core_model(build_model):
    """The widget and the core model give the same lifetime spectrum."""
    from chisurf.core.models.tcspc.fret import GaussianModel
    from chisurf.gui.widgets.models.tcspc import GaussianModelWidget

    def build(model_class):
        model = build_model(model_class)
        model.fret_parameters.tauD0 = 4.0
        model.fret_parameters.forster_radius = 52.0
        model.fret_parameters.xDOnly = 0.0
        model.donor.lifetimes = [4.0]
        model.donor.amplitudes = [1.0]
        while len(model.gaussians) > 0:
            model.gaussians.pop()
        model.gaussians.append(mean=35.0, sigma=4.0, x=1.0)
        return np.asarray(model.lifetime_spectrum)

    np.testing.assert_allclose(build(GaussianModelWidget), build(GaussianModel))


def test_discrete_distance_widget_append_keeps_requested_values(build_model):
    """``fret_rates.append(mean=..., x=...)`` reaches the parameters."""
    from chisurf.gui.widgets.models.tcspc import FRETrateModelWidget

    model = build_model(FRETrateModelWidget)
    while len(model.fret_rates) > 0:
        model.fret_rates.pop()
    model.fret_rates.append(mean=42.0, x=1.0)
    model.fret_rates.append(mean=84.0, x=1.0)

    assert len(model.fret_rates) == 2
    np.testing.assert_allclose(model.fret_rates.distance, [42.0, 84.0])
    np.testing.assert_allclose(model.fret_rates.amplitude, [0.5, 0.5])
