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

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

from ndxplorer.core import chisurf_binding  # noqa: E402
from ndxplorer.core.constants_group import (  # noqa: E402
    ConstantsMapping,
    build_constants_group,
    group_to_value_dict,
)
from ndxplorer.core.parameters import register_group, unregister_group  # noqa: E402

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


@pytest.fixture()
def group():
    """The constants of an ndX window: nDXplorer's own parameter group."""
    return build_constants_group(NDX_CONSTANTS)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Leave the process-global registries as clean as they were found."""
    yield
    unregister_group("ndxplorer")
    chisurf_binding.withdraw("ndxplorer")
    for owner_id, *_ in list(iter_registered_parameter_groups()):
        unregister_parameter_group(owner_id)


def _registered(owner: str):
    return {o: g for o, _label, g in iter_registered_parameter_groups()}.get(owner)


# ---------------------------------------------------------------------------
# ndX constants: nDXplorer's group, mirrored once
# ---------------------------------------------------------------------------


def test_constants_become_fitting_parameters(group):
    """Publishing the group puts one FittingParameter per constant in the Global View."""
    from chisurf.core.fitting.parameter import FittingParameter

    assert chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    registered = _registered("ndxplorer")
    assert registered is chisurf_binding.chisurf_group(group)
    by_name = {p.name: p for p in registered.parameters_all}
    assert set(by_name) == set(NDX_CONSTANTS)
    assert all(isinstance(p, FittingParameter) for p in by_name.values())
    assert by_name["gG/gR"].value == pytest.approx(0.6)  # not an identifier: still works
    assert by_name["alpha"].value == pytest.approx(0.015)


def test_parameters_are_globally_resolvable(group):
    """Each mirror carries a process-wide identity, which is what links use."""
    from chisurf.core.base import Base

    chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    alpha = chisurf_binding.mirrored(group.parameters_all_dict["alpha"])
    assert Base.find_by_uuid(alpha.unique_identifier) is alpha


def test_the_editor_and_the_window_share_one_mirror(group):
    """ndX's editor registers the group and ChiSurf's window publishes it again.

    Both land in the slot ``ndxplorer``; the second must not replace the first
    with a copy, or the Global View would edit numbers the window never reads.
    """
    register_group(group, "ndxplorer", "ndX")  # ui/parameter_editor.py
    first = _registered("ndxplorer")
    assert chisurf_binding.publish(group, "ndxplorer", "ndX constants")  # window.py
    assert _registered("ndxplorer") is first is chisurf_binding.chisurf_group(group)


def test_withdrawing_empties_the_slot(group):
    chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    chisurf_binding.withdraw("ndxplorer")
    assert _registered("ndxplorer") is None


def test_a_global_view_edit_is_the_windows_value(group):
    """An edit of the mirror is what the window's constants read next."""
    chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    constants = ConstantsMapping(group)  # what the window computes with
    chisurf_binding.mirrored(group.parameters_all_dict["forster_radius"]).value = 60.0
    assert constants["forster_radius"] == pytest.approx(60.0)


def test_a_window_edit_reaches_the_global_view(group):
    chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    ConstantsMapping(group).update({"alpha": 0.09, "new_constant": 3.0})
    by_name = {p.name: p for p in _registered("ndxplorer").parameters_all}
    assert by_name["alpha"].value == pytest.approx(0.09)
    assert by_name["new_constant"].value == pytest.approx(3.0)  # constants may appear later


def test_calibration_view_of_the_same_numbers(group):
    """The Hellenkamp view is derived, not duplicated.

    ndX's ``beta`` is the direct excitation and its ``r`` is ``1/beta``, so
    the two namings are converted rather than mirrored.
    """
    from chisurf.plugins.ndxplorer.calibration_bridge import calibration_from_ndx_constants

    calibration = calibration_from_ndx_constants(dict(group_to_value_dict(group)))
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


def test_a_fit_parameter_can_be_linked_to_an_ndx_constant(group):
    """A fit reads its Förster radius from the window, so there is one number.

    This is what "in the Global View" is *for*: the constant keeps one owner, and
    every consumer follows it instead of carrying its own copy.
    """
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    chisurf_binding.publish(group, "ndxplorer", "ndX constants")
    calibration = CalibrationParameters()
    calibration._r0.link = chisurf_binding.mirrored(group.parameters_all_dict["forster_radius"])

    assert calibration.r0 == pytest.approx(52.0)
    group.parameters_all_dict["forster_radius"].value = 58.0  # the window's edit
    assert calibration.r0 == pytest.approx(58.0)  # the follower tracks the owner


def test_a_calibration_can_be_linked_to_the_optics():
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
