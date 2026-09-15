"""The FRET-line engine over BFF-described models.

A FRET line is the locus a population must occupy in the plane of efficiency
against donor lifetime. These tests check that the engine produces a line
obeying the relations that define one, that it agrees with the independent
analytic implementation in :mod:`chisurf.core.fluorescence.fret.lines`, and
that it reproduces the classic ChiSurf FRET-line tool (Gaussian, worm-like
chain, discrete distances, a lifetime, a two-state mixture), frozen in
``data/fret_line_classic_reference.json`` before the classic models were removed.
"""

import json
import pathlib

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

from chisurf.core.fluorescence.fret import fret_line as FL
from chisurf.core.fluorescence.fret.lines import static_fret_line

REFERENCE = json.loads((pathlib.Path(__file__).parent / "data" / "fret_line_classic_reference.json").read_text())

#: The classic tool's parameter names, as the reference records them, and what they are now.
CLASSIC = {"R(G,1)": "distance.mean.0", "R(G,2)": "distance.mean.1", "x(G,2)": "distance.amplitude.1",
           "s(G,1)": "distance.sigma.0", "s(G,2)": "distance.sigma.1", "xDOnly": "fret.x_donly",
           "R(d,1)": "distance.mean.0", "R(d,2)": "distance.mean.1", "x(d,2)": "distance.amplitude.1",
           "l": "chain.contour_length", "tL1": "lifetime.tau.0"}
FAMILY = {"FRET: FD (Gaussian)": "tcspc_fret_gaussian", "FRET: FD (Worm-like chain)": "tcspc_fret_worm_like_chain",
          "FRET: FD (Discrete)": "tcspc_fret_discrete", "Lifetime": "tcspc_lifetime"}


def _gaussian_line(n_points=20, parameter_range=(20.0, 100.0)):
    fl = FL.FRETLineGenerator("tcspc_fret_gaussian", n_points=n_points, parameter_range=parameter_range,
                              parameter_name="distance.mean.0")
    fl.parameter("fret.x_donly").value = 0.0
    fl.parameter("distance.mean.0").value = 55.0
    fl.parameter("distance.sigma.0").value = 10.0
    return fl


@pytest.mark.parametrize("case", sorted(REFERENCE))
def test_the_classic_fret_line_tool_is_reproduced(case):
    spec = REFERENCE[case]["spec"]
    views = []
    for component in spec["components"]:
        view = FL.model_view(FAMILY[component["model_name"]], component["n_components"])
        # The classic models' starting values the reference was computed at.
        for i in range(component["n_components"]):
            for name, value in ((f"distance.amplitude.{i}", 1.0), (f"distance.shape.{i}", 0.0)):
                try:
                    FL.find_parameter(view, name).value = value
                except KeyError:
                    pass
        try:
            FL.find_parameter(view, "fret.x_donly").value = 0.0
        except KeyError:
            pass
        for name, value in component["params"].items():
            FL.find_parameter(view, CLASSIC[name]).value = value
        views.append(view)
    target = dict(spec["sweep"])
    if target.get("name"):
        target["name"] = CLASSIC[target["name"]]
    values = np.linspace(spec["param_min"], spec["param_max"], spec["n_points"])
    got = FL.sweep(views, target, values, tau_d0=spec.get("tau_d0"))
    # The classic mixer kept a fraction off zero at the sweep's ends: a few parts in 1e9 there.
    rtol = 1e-7 if len(views) > 1 else 1e-12
    for quantity in ("tau_x", "tau_f", "e_fret"):
        np.testing.assert_allclose(got[quantity], REFERENCE[case]["result"][quantity], rtol=rtol, err_msg=quantity)


def test_lifetime_averages_obey_their_inequality():
    """<tau>_F >= <tau>_x (Cauchy-Schwarz), both below the donor-only lifetime."""
    fl = _gaussian_line()
    tau_d0 = fl.donor_species_averaged_lifetime
    assert fl.fret_fluorescence_averaged_lifetime >= fl.fret_species_averaged_lifetime
    assert fl.fret_species_averaged_lifetime > 0.0
    assert fl.fret_fluorescence_averaged_lifetime < tau_d0 * 1.001


def test_efficiency_follows_the_species_averaged_lifetime():
    fl = _gaussian_line()
    expected = 1.0 - fl.fret_species_averaged_lifetime / fl.donor_species_averaged_lifetime
    assert fl.transfer_efficiency == pytest.approx(expected, abs=1e-12)
    assert 0.0 <= fl.transfer_efficiency <= 1.0


def test_moving_the_acceptor_away_lengthens_the_lifetime():
    fl = _gaussian_line()
    fl.parameter("distance.mean.0").value = 40.0
    tau_close, e_close = fl.fret_species_averaged_lifetime, fl.transfer_efficiency
    fl.parameter("distance.mean.0").value = 70.0
    assert fl.fret_species_averaged_lifetime > tau_close
    assert fl.transfer_efficiency < e_close


def test_swept_line_is_monotonic_and_within_bounds():
    fl = _gaussian_line(n_points=25, parameter_range=(20.0, 120.0))
    fl.update()
    tau_d0 = fl.donor_species_averaged_lifetime
    assert len(fl.parameter_values) == len(fl.species_averaged_lifetimes) == 25
    assert np.all(np.diff(fl.species_averaged_lifetimes) > 0)
    assert np.all(np.diff(fl.fret_efficiencies) < 0)
    assert np.all(fl.fluorescence_averaged_lifetimes >= fl.species_averaged_lifetimes - 1e-9)
    assert np.all(fl.species_averaged_lifetimes <= tau_d0 * 1.001)


def test_conversion_function_is_a_polynomial_in_tau_f():
    fl = _gaussian_line()
    fl.update()
    string = fl.conversion_function_string
    assert string.count("*x^") == fl.polynomial_degree + 1
    assert string in fl.transfer_efficency_string and string in fl.fdfa_string
    assert np.all(np.isfinite(fl.polynom_coefficients))


def test_static_line_matches_the_analytic_line():
    """At matched lifetime: the two discretise P(R) differently, so equal R is not the same point."""
    fl = FL.StaticFRETLine(n_points=40, parameter_range=(20.0, 120.0))
    fl.update()
    tau_d0 = fl.donor_species_averaged_lifetime
    analytic = static_fret_line(tau_d0, r0=fl.parameter("fret.forster_radius").value, sigma=fl.sigma,
                                distance_range=(10.0, 200.0), n_points=400)
    inside = (fl.fluorescence_averaged_lifetimes > 0.2) & (fl.fluorescence_averaged_lifetimes < 0.95 * tau_d0)
    assert inside.any()
    difference = np.abs(fl.fret_efficiencies[inside] - analytic.efficiency_at(fl.fluorescence_averaged_lifetimes[inside]))
    assert float(np.max(difference)) < 0.02


def test_dynamic_line_lies_between_its_two_states():
    fl = FL.DynamicFRETLine(distance_1=40.0, distance_2=80.0, sigma_1=6.0, sigma_2=6.0,
                            n_points=20, parameter_range=(0.0, 10.0))
    assert fl.sigma == (6.0, 6.0)
    fl.update()
    tau_x = fl.species_averaged_lifetimes
    assert np.all(tau_x >= min(tau_x[0], tau_x[-1]) - 1e-9)
    assert np.all(tau_x <= max(tau_x[0], tau_x[-1]) + 1e-9)
    assert np.all(fl.fluorescence_averaged_lifetimes >= tau_x - 1e-9)
