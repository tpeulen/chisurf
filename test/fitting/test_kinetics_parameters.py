"""A fittable kinetic scheme, general rather than owned by one experiment.

``chisurf.core.fitting.kinetics`` is the fitting layer over the rate matrix:
the transitions as fitting parameters, so a model can *recover* a scheme rather
than only be told one. The arithmetic — and, critically, the **single flat-rate
convention** — lives in ``chisurf.core.fluorescence.kinetics``; these tests pin
that the two agree, because a second convention is exactly the bug that a shared
module is supposed to prevent.
"""

import numpy as np
import pytest

from chisurf.core.fitting.kinetics import RateMatrixMixin, RateMatrixParameters
from chisurf.core.fluorescence.kinetics import (
    rate_matrix_from_rates,
    rates_from_rate_matrix,
    transitions_per_window,
)

# -- one convention, not two -------------------------------------------------


@pytest.mark.parametrize("n_states", [2, 3, 4, 5])
def test_the_parameter_order_is_the_shared_flat_order(n_states):
    """The parameter list lines up with ``rate_matrix_from_rates`` element-wise.

    If these ever diverge, a rate vector means one thing to the scheme and
    another to the likelihood consuming it — silently, and only visible as a
    permuted kinetic scheme in the result.
    """
    scheme = RateMatrixParameters(name="k", n_states=n_states)
    values = np.arange(1.0, n_states * (n_states - 1) + 1.0)
    for parameter, value in zip(scheme._rates, values):
        parameter.value = value

    assert np.array_equal(scheme.flat_rates, values)
    assert np.array_equal(scheme.rate_matrix(), rate_matrix_from_rates(values, n_states))
    assert np.array_equal(rates_from_rate_matrix(scheme.rate_matrix()), values)


def test_the_names_say_source_and_target():
    """``k<i>_<j>`` is the rate i -> j, and sits at ``K[j-1, i-1]``."""
    scheme = RateMatrixParameters(name="k", n_states=3)
    for parameter in scheme._rates:
        parameter.value = 0.0
    scheme.rates_by_name()["k2_3"].value = 42.0
    assert scheme.rate_matrix()[2, 1] == pytest.approx(42.0)
    assert np.count_nonzero(scheme.rate_matrix()) == 1


def test_the_matrix_round_trips_through_the_parameters():
    """Writing a matrix and reading it back is the identity."""
    scheme = RateMatrixParameters(name="k", n_states=3)
    K = np.array([[0.0, 120.0, 0.0], [80.0, 0.0, 300.0], [0.0, 90.0, 0.0]])
    scheme.set_rate_matrix(K)
    assert np.array_equal(scheme.rate_matrix(), K)


def test_the_grid_view_is_the_transpose_read():
    """``rate_values`` is the full n*n row-major grid the editor binds to."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.rates_by_name()["k1_2"].value = 7.0
    scheme.rates_by_name()["k2_1"].value = 9.0
    # Row i, column j of the grid is k_ij.
    assert scheme.rate_values == pytest.approx([0.0, 7.0, 9.0, 0.0])
    scheme.rate_values = [0.0, 1.0, 2.0, 0.0]
    assert scheme.rates_by_name()["k1_2"].value == pytest.approx(1.0)
    assert scheme.rates_by_name()["k2_1"].value == pytest.approx(2.0)


# -- discovery ---------------------------------------------------------------


@pytest.mark.parametrize("n_states, n_rates", [(2, 2), (3, 6), (4, 12)])
def test_every_rate_is_a_discoverable_parameter(n_states, n_rates):
    """The optimiser must be able to see them; a dict would hide them all."""
    scheme = RateMatrixParameters(name="k", n_states=n_states)
    scheme.find_parameters()
    names = sorted(p.name for p in scheme.parameters_all)
    assert len(names) == n_rates
    assert names[0].startswith("k")


def test_rates_start_fixed_and_can_be_freed():
    """A scheme arrives inert; freeing a rate is the deliberate act."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.find_parameters()
    assert [p.name for p in scheme.parameters] == []
    scheme.rates_by_name()["k1_2"].fixed = False
    scheme.find_parameters()
    assert [p.name for p in scheme.parameters] == ["k1_2"]


# -- resizing ----------------------------------------------------------------


def test_growing_keeps_rates_and_their_fixed_state():
    """Adding a state must not reconnect a scheme built out of zeros."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.rates_by_name()["k1_2"].value = 250.0
    scheme.rates_by_name()["k2_1"].fixed = False

    scheme.n_states = 3
    rates = scheme.rates_by_name()
    assert scheme.n_states == 3
    assert rates["k1_2"].value == pytest.approx(250.0)
    assert rates["k2_1"].fixed is False
    assert rates["k1_3"].fixed is True


def test_shrinking_drops_the_vanished_row_and_column():
    """Removing a state removes exactly its transitions."""
    scheme = RateMatrixParameters(name="k", n_states=3)
    scheme.n_states = 2
    assert sorted(scheme.rates_by_name()) == ["k1_2", "k2_1"]


def test_two_states_is_the_floor():
    """A one-state scheme has no transitions and is not a scheme."""
    scheme = RateMatrixParameters(name="k", n_states=1)
    assert scheme.n_states == 2


def test_setting_a_differently_sized_matrix_resizes():
    """A matrix carries its own state count."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.set_rate_matrix(np.zeros((4, 4)))
    assert scheme.n_states == 4
    assert len(scheme.rates_by_name()) == 12


def test_a_non_square_matrix_is_refused():
    """Silently reshaping would produce a plausible, wrong scheme."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    with pytest.raises(ValueError, match="square"):
        scheme.set_rate_matrix(np.zeros((2, 3)))


# -- optional dynamics -------------------------------------------------------


def test_a_zero_default_makes_an_inert_scheme():
    """A model whose dynamics are optional needs "no kinetics" as the default."""
    scheme = RateMatrixParameters(name="k", n_states=3, default_rate=0.0)
    assert scheme.any_rate is False
    assert not np.any(scheme.rate_matrix())
    scheme.rates_by_name()["k1_2"].value = 1.0
    assert scheme.any_rate is True
    # A state added later must not switch the dynamics on behind the user.
    scheme.n_states = 4
    assert scheme.rates_by_name()["k1_4"].value == 0.0


def test_clearing_zeroes_rather_than_deletes():
    """``None`` means "no kinetics", not "no parameters"."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.set_rate_matrix(None)
    assert scheme.any_rate is False
    assert len(scheme.rates_by_name()) == 2


# -- exchange speed ----------------------------------------------------------


def test_transitions_per_window_matches_the_free_function():
    """The method is the shared estimate, not a second one."""
    scheme = RateMatrixParameters(name="k", n_states=2)
    scheme.set_rate_matrix(np.array([[0.0, 300.0], [200.0, 0.0]]))
    assert scheme.transitions_per_window(2e-3) == pytest.approx(
        transitions_per_window(scheme.rate_matrix(), 2e-3)
    )
    # Escape rate of the fastest state: 300 Hz out of state 2.
    assert scheme.transitions_per_window(1.0) == pytest.approx(300.0)


# -- the mixin, for groups that hold more than rates -------------------------


def test_the_mixin_composes_with_other_fitted_quantities():
    """States usually carry something besides their rates; both stay in one group."""
    from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

    class Scheme(RateMatrixMixin, FittingParameterGroup):
        """Two states with an efficiency each, exchanging."""

        def __init__(self, **kwargs):
            super().__init__(name="scheme", **kwargs)
            self._rates: list = []
            self._n_states = 0
            self._efficiency = [
                FittingParameter(value=v, name=f"E{i + 1}") for i, v in enumerate((0.2, 0.8))
            ]
            self._rebuild_rates(2)

    scheme = Scheme()
    scheme.find_parameters()
    names = sorted(p.name for p in scheme.parameters_all)
    assert names == ["E1", "E2", "k1_2", "k2_1"]
    assert scheme.rate_matrix().shape == (2, 2)


# -- the one place a different reading survives ------------------------------


def test_flc_2d_reads_the_transpose_and_says_so():
    """2D-FLC takes ``K[source, target]``; the rest of ChiSurf takes the transpose.

    Both readings are self-consistent, so a matrix crossing between them is
    never rejected — it silently swaps the populations. That makes this worth
    pinning: the plugin delegates to the shared generator with one explicit
    transpose at its boundary, and if anyone "unifies" that away, the two
    assertions below disagree.
    """
    from chisurf.core.fluorescence.kinetics import equilibrium_populations as shared
    from chisurf.plugins.fcs.flc_2d.fit.kinetics import equilibrium_populations as flc

    K = np.array([[0.0, 300.0], [200.0, 0.0]])
    assert shared(K) == pytest.approx([0.6, 0.4])
    assert flc(K) == pytest.approx([0.4, 0.6])
    assert flc(K) == pytest.approx(shared(K.T))
