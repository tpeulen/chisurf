"""A sampler must draw from the stream the caller seeded, and freeze the structure.

Two defects this pins, both silent:

* ``sample_ensemble`` and the other ensemble/DE backends built their generator
  with ``np.random.default_rng(seed)``. With ``seed=None`` that draws fresh
  entropy from the OS, so ``np.random.seed(...)`` -- the only seeding a caller
  or a test has -- was ignored and the same run gave a different chain each
  time. :func:`chisurf.core.fitting.sample._rng` exists precisely to prevent
  that, and its docstring says so; three call sites did not use it.
* ``walk_mcmc`` lost its ``@frozen('fit', 'model')`` decorator when ``_rng``
  was inserted below it: the decorator stayed on the line above and ended up
  wrapping ``_rng``, which has neither a ``fit`` nor a ``model`` argument and
  therefore froze nothing. Every other sampler in the module carries it.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.fitting.sample as sample
import chisurf.core.models.parse

SIGMA = 0.05

#: Sampler entry points that run an objective and must hold the structure fixed.
SAMPLERS = [
    "walk_mcmc",
    "walk_mcmc_blocked",
    "sample_differential_evolution",
    "sample_independent_components",
    "sample_marginal_shared",
    "sample_ensemble",
    "sample_ensemble_slice",
]


def _quadratic_fit(seed: int = 1):
    """Return a converged ``c + a*x**2`` fit to noisy data with known sigma."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 64)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, SIGMA, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def test_the_default_generator_follows_the_global_seed():
    """``_rng(None)`` is reproducible under ``np.random.seed``."""
    np.random.seed(17)
    first = sample._rng(None).normal(size=8)
    np.random.seed(17)
    second = sample._rng(None).normal(size=8)

    np.testing.assert_array_equal(first, second)


def test_the_default_generator_has_the_full_generator_api():
    """A :class:`~numpy.random.Generator`, not the :mod:`numpy.random` module.

    The module has no ``integers``; the ensemble samplers draw one.
    """
    generator = sample._rng(None)

    assert isinstance(generator, np.random.Generator)
    assert generator.integers(0, 4, size=3).shape == (3,)


@pytest.mark.parametrize("name", SAMPLERS)
def test_every_sampler_freezes_the_parameter_structure(name):
    """The freeze is a decorator, so its absence is invisible until profiled."""
    function = getattr(sample, name)

    assert hasattr(function, "__wrapped__"), f"{name} is not wrapped by @frozen"


def _twice(seed: int, run):
    """Return the chains of *run* executed twice under the same global seed.

    A fresh fit each time on purpose: an ensemble spreads its walkers around
    the model's *current* parameter values, which a completed run has left at
    its last draw. Reusing the fit would compare two different starting points
    and say nothing about the seeding.
    """
    chains = []
    for _ in range(2):
        fit = _quadratic_fit()
        np.random.seed(seed)
        chains.append(np.asarray(run(fit)['chains']))
    return chains


def test_the_ensemble_chain_is_reproducible_under_a_global_seed():
    """The whole point: same seed, same chain."""
    first, second = _twice(
        3, lambda fit: sample.sample_ensemble(fit, steps=40, nwalkers=8, thin=1)
    )

    np.testing.assert_allclose(first, second)


def test_the_slice_chain_is_reproducible_under_a_global_seed():
    """The slice backend seeds itself the same way."""
    first, second = _twice(
        4, lambda fit: sample.sample_ensemble_slice(fit, steps=20, nwalkers=8, thin=1)
    )

    np.testing.assert_allclose(first, second)


def test_the_differential_evolution_chain_is_reproducible_under_a_global_seed():
    """And so does the differential-evolution backend."""
    first, second = _twice(
        5, lambda fit: sample.sample_differential_evolution(fit, steps=40, n_chains=8, thin=1)
    )

    np.testing.assert_allclose(first, second)
