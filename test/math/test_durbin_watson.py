"""``durbin_watson`` — correctness after de-JIT-ing.

The statistic used to be ``@nb.jit(nopython=True)`` without ``cache=True``, so
it compiled the first time a fit window rendered its metrics overlay: a ~230 ms
stall on the GUI thread, once per process. It is an O(n) statistic that NumPy
evaluates in microseconds, so it is now plain NumPy. These pin the arithmetic.
"""
import numpy as np
import pytest

from chisurf.core.math.statistics import durbin_watson


def _reference(r):
    """The original loop, verbatim."""
    n_res = len(r)
    nom = 0.0
    den = float(np.sum(np.asarray(r) ** 2))
    for i in range(1, n_res):
        nom += (r[i] - r[i - 1]) ** 2
    return nom / max(1.0, den)


@pytest.mark.parametrize("n", [2, 3, 5, 64, 1024, 4096])
def test_matches_the_original_formula(n):
    r = np.random.default_rng(n).normal(size=n)
    assert durbin_watson(r) == pytest.approx(_reference(r), rel=0, abs=1e-12)


def test_uncorrelated_residuals_are_near_two():
    """White noise has DW ~ 2 -- the property the statistic exists to report."""
    r = np.random.default_rng(0).normal(size=20000)
    assert durbin_watson(r) == pytest.approx(2.0, abs=0.05)


def test_strong_positive_autocorrelation_is_near_zero():
    r = np.cumsum(np.random.default_rng(1).normal(size=20000))
    assert durbin_watson(r) < 0.5


def test_alternating_residuals_approach_four():
    """Perfect anti-correlation gives exactly 4*(n-1)/n, i.e. 4 in the limit."""
    n = 10000
    r = np.array([1.0, -1.0] * (n // 2))
    assert durbin_watson(r) == pytest.approx(4.0 * (n - 1) / n, rel=0, abs=1e-12)
    assert durbin_watson(r) == pytest.approx(4.0, abs=1e-3)


@pytest.mark.parametrize("r", [np.array([]), np.array([1.0])])
def test_degenerate_inputs_do_not_raise(r):
    assert durbin_watson(r) == 0.0


def test_accepts_a_list():
    assert durbin_watson([1.0, 2.0, 3.0]) == pytest.approx(_reference([1.0, 2.0, 3.0]))


def test_is_not_jit_compiled():
    """Guard the regression: re-adding numba reintroduces the GUI stall."""
    assert not hasattr(durbin_watson, "py_func"), (
        "durbin_watson is numba-compiled again; it renders in the plot overlay "
        "and will stall the GUI thread on first use")
