"""ndX constants and the simulated optics as fitting parameters.

Both are numbers that live outside a fit — ndX's correction constants and
the light-path simulator's excitation/emission probabilities — and both belong in
the Global View: visible next to every fit parameter, linkable to one, bounded
and freeable like any other. These tests pin that they are real
``FittingParameter``s, that they reach the out-of-fit registry the Global View
enumerates, and that the round trip back into the owning tool works.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.registry.parameter_groups import (
    iter_registered_parameter_groups,
    unregister_parameter_group,
)
from chisurf.plugins.core.lightpath_simulator.core.parameters import (
    LightPathParameters,
    register_lightpath_parameters,
    unregister_lightpath_parameters,
)
from chisurf.plugins.ndxplorer.parameters import (
    NdxConstants,
    bind_ndx_parameters,
    unbind_ndx_parameters,
)

NDX_CONSTANTS = {
    "gG/gR": 0.6,
    "alpha": 0.015,
    "beta": 0.005,
    "r": 1.0,
    "PhiA": 0.32,
    "PhiD": 0.8,
    "forster_radius": 52.0,
    "tauD0": 4.0,
    "Bg": 1.2,
    "Br": 0.6,
    "By": 0.6,
    "label": "not a number",
}

MATRICES = {
    "excitation": {
        "rows": ["green", "red"],
        "columns": ["AF488", "AF647"],
        "values": [[1.0, 0.055], [0.001, 1.0]],
    },
    "emission": {
        "rows": ["AF488", "AF647"],
        "columns": ["green_det", "red_det"],
        "values": [[0.92, 0.075], [0.02, 0.90]],
    },
}


class _DataSource:
    """Minimal stand-in for ndX's data source."""

    last: dict | None = None

    def compute_columns(self, constants=None, equations=None):
        """Record the constants a recompute was asked to use."""
        self.last = dict(constants or {})


class _Window:
    """Minimal stand-in for an ndX window."""

    def __init__(self):
        self.constants = dict(NDX_CONSTANTS)
        self.equations = []
        self.data_source = _DataSource()
        self.updated = 0

    def update_plots(self):
        """Count plot refreshes."""
        self.updated += 1


@pytest.fixture()
def window():
    """Return a stub ndX window with its constants set."""
    return _Window()


@pytest.fixture(autouse=True)
def _clean_registry():
    """Leave the process-global registry as clean as it was found."""
    yield
    for owner_id, *_ in list(iter_registered_parameter_groups()):
        unregister_parameter_group(owner_id)


# ---------------------------------------------------------------------------
# ndX constants
# ---------------------------------------------------------------------------


def test_constants_become_fitting_parameters(window):
    """Every numeric constant of the window is exposed as a fitting parameter."""
    group = NdxConstants(window.constants)
    names = {p.name for p in group.parameters_all}
    assert {"gG/gR", "alpha", "beta", "r", "tauD0", "forster_radius"} <= names
    assert "label" not in names  # non-numeric entries are skipped
    assert len(group.constant_names) == len(NDX_CONSTANTS) - 1

    alpha = group.parameter("alpha")
    assert alpha.value == pytest.approx(0.015)
    assert alpha.fixed is False  # visible in the Global View by default
    assert (alpha.lb, alpha.ub) == (0.0, 1.0)  # a leakage cannot leave 0…1
    # a name that is not an identifier still works
    assert group.parameter("gG/gR").value == pytest.approx(0.6)


def test_parameters_are_globally_resolvable(window):
    """Each parameter carries a process-wide identity, which is what links use."""
    from chisurf.core.base import Base

    group = NdxConstants(window.constants)
    alpha = group.parameter("alpha")
    assert Base.find_by_uuid(alpha.unique_identifier) is alpha


def test_binding_publishes_the_group_to_the_global_view(window):
    """Binding a window makes its constants enumerable by the Global View."""
    group = bind_ndx_parameters(window)
    owners = {owner_id: label for owner_id, label, _ in iter_registered_parameter_groups()}
    assert "ndxplorer" in owners
    registered = [g for _, _, g in iter_registered_parameter_groups()]
    assert group in registered

    unbind_ndx_parameters()
    assert "ndxplorer" not in dict(
        (owner_id, label) for owner_id, label, _ in iter_registered_parameter_groups()
    )


def test_editing_a_parameter_reaches_the_window(window):
    """An edited value is pushed into the window, which recomputes."""
    group = bind_ndx_parameters(window)
    group.parameter("alpha").value = 0.09
    applied = group.push(window)

    assert applied["alpha"] == pytest.approx(0.09)
    assert window.constants["alpha"] == pytest.approx(0.09)
    assert window.data_source.last["alpha"] == pytest.approx(0.09)
    assert window.updated == 1


def test_refreshing_the_group_syncs_a_global_view_edit(window):
    """``update`` carries an edit made elsewhere into the window.

    The Global View writes straight into the parameter object; without this hook
    the window would keep computing with the old number.
    """
    group = bind_ndx_parameters(window)
    group.parameter("forster_radius").value = 60.0
    group.update()
    assert window.constants["forster_radius"] == pytest.approx(60.0)
    # and it is a no-op once they agree
    window.updated = 0
    group.update()
    assert window.updated == 0


def test_pull_reads_the_window_back(window):
    """Constants changed by the window itself come back into the parameters."""
    group = bind_ndx_parameters(window)
    window.constants["alpha"] = 0.11
    window.constants["new_constant"] = 3.0
    created = group.pull(window)

    assert group.parameter("alpha").value == pytest.approx(0.11)
    assert created == ["new_constant"]  # constants may appear later
    assert group.parameter("new_constant").value == pytest.approx(3.0)


def test_calibration_view_of_the_same_numbers(window):
    """The Hellenkamp view is derived, not duplicated.

    ndX's ``beta`` is the direct excitation and its ``r`` is ``1/beta``, so
    the two namings are converted rather than mirrored.
    """
    group = NdxConstants(window.constants)
    calibration = group.as_calibration()
    assert calibration.delta == pytest.approx(0.005)  # ndx "beta"
    assert calibration.beta == pytest.approx(1.0)  # 1 / ndx "r"
    assert calibration.gamma == pytest.approx((0.32 / 0.8) / 0.6)
    assert calibration.r0 == pytest.approx(52.0)


# ---------------------------------------------------------------------------
# the simulated optical path
# ---------------------------------------------------------------------------


def test_optics_become_fitting_parameters():
    """Excitation/emission probabilities and quantum yields are parameters."""
    group = LightPathParameters(
        MATRICES,
        quantum_yields={"AF488": 0.92, "AF647": 0.33},
        detection_efficiencies={"green_det": 1.0, "red_det": 0.72},
    )
    names = {p.name for p in group.parameters_all}
    assert "em[AF488→red_det]" in names  # the leakage path
    assert "ex[green→AF647]" in names  # the direct-excitation path
    assert {"QY[AF488]", "g[red_det]"} <= names
    assert {"gamma (optics)", "alpha (optics)", "delta (optics)"} <= names
    assert group.parameter("qy", "AF647").value == pytest.approx(0.33)
    assert group.parameter("qy", "AF647").fixed is False
    # the three derived factors stay fixed: they are read-outs, recomputed below
    assert group._gamma.fixed is True


def test_optics_imply_the_correction_factors():
    """gamma, alpha and delta follow from the probabilities, and track them."""
    group = LightPathParameters(
        MATRICES,
        quantum_yields={"AF488": 0.92, "AF647": 0.33},
        detection_efficiencies={"green_det": 1.0, "red_det": 0.72},
    )
    factors = group.update_factors()
    assert factors["delta"] == pytest.approx(0.055)  # ex ratio
    # Hellenkamp alpha = I_DA/I_DD = gR*cRD / (gG*cGD) — ratio to the green channel
    assert factors["alpha"] == pytest.approx(0.72 * 0.075 / 0.92)
    assert factors["gamma"] == pytest.approx((0.72 * 0.90 * 0.33) / (0.92 * 0.92))
    assert group.gamma == pytest.approx(factors["gamma"])

    # editing an optical quantity changes what the optics predict
    group.parameter("qy", "AF647").value = 0.66
    assert group.update_factors()["gamma"] == pytest.approx(2.0 * factors["gamma"])


def test_optics_feed_the_calibration_prior():
    """The group hands itself over as the ``lightpath=`` prior, unchanged."""
    from chisurf.core.fluorescence.fret.calibration import (
        CalibrationParameters,
        set_priors_from_lightpath,
    )

    group = LightPathParameters(
        MATRICES,
        quantum_yields={"AF488": 0.92, "AF647": 0.33},
        detection_efficiencies={"green_det": 1.0, "red_det": 0.72},
    )
    calibration = CalibrationParameters()
    factors = set_priors_from_lightpath(calibration, **group.as_prior_arguments())

    assert factors["gamma"] == pytest.approx(group.gamma)
    assert factors["alpha"] == pytest.approx(group.alpha)
    assert calibration._gamma.prior is not None  # it is a prior, not a value


def test_rerunning_the_simulation_updates_the_same_group():
    """A new simulation refreshes the registered group instead of adding one."""
    group = register_lightpath_parameters(MATRICES)
    assert [owner for owner, *_ in iter_registered_parameter_groups()] == ["lightpath"]

    changed = {
        **MATRICES,
        "emission": {
            "rows": ["AF488", "AF647"],
            "columns": ["green_det", "red_det"],
            "values": [[0.92, 0.150], [0.02, 0.90]],  # twice the leakage
        },
    }
    again = register_lightpath_parameters(changed)
    assert again is group  # links into it survive
    assert group.parameter("em", "AF488", "red_det").value == pytest.approx(0.150)
    assert [owner for owner, *_ in iter_registered_parameter_groups()] == ["lightpath"]

    unregister_lightpath_parameters()
    assert list(iter_registered_parameter_groups()) == []


def test_optics_round_trip_through_the_payload():
    """The payload rebuilt from the parameters is the one that went in."""
    group = LightPathParameters(MATRICES)
    rebuilt = group.as_matrices()
    for key in ("excitation", "emission"):
        np.testing.assert_allclose(
            np.asarray(rebuilt[key]["values"], dtype=float),
            np.asarray(MATRICES[key]["values"], dtype=float),
        )
        assert rebuilt[key]["rows"] == MATRICES[key]["rows"]
        assert rebuilt[key]["columns"] == MATRICES[key]["columns"]


# ---------------------------------------------------------------------------
# the point of all this: linking them into a fit
# ---------------------------------------------------------------------------


def test_a_fit_parameter_can_be_linked_to_an_ndx_constant(window):
    """A fit reads its Förster radius from the window, so there is one number.

    This is what "in the Global View" is *for*: the constant keeps one owner, and
    every consumer follows it instead of carrying its own copy.
    """
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    group = bind_ndx_parameters(window)
    calibration = CalibrationParameters()
    calibration._r0.link = group.parameter("forster_radius")

    assert calibration.r0 == pytest.approx(52.0)
    group.parameter("forster_radius").value = 58.0
    assert calibration.r0 == pytest.approx(58.0)  # the follower tracks the owner


def test_a_calibration_can_be_linked_to_the_optics(window):
    """A fitted factor can follow an optical quantity — the prior made explicit."""
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    optics = LightPathParameters(
        MATRICES,
        quantum_yields={"AF488": 0.92, "AF647": 0.33},
        detection_efficiencies={"green_det": 1.0, "red_det": 0.72},
    )
    calibration = CalibrationParameters()
    calibration._phi_a.link = optics.parameter("qy", "AF647")

    assert calibration.phi_a == pytest.approx(0.33)
    optics.parameter("qy", "AF647").value = 0.40
    assert calibration.phi_a == pytest.approx(0.40)
