"""The κ² regime of a component moves its FRET line: static and dynamic averaging are different lines.

Dynamic κ² (``orientation_parameter.mode = "fast"``): every donor-acceptor pair transfers with the one scalar
κ² of the model, so at a given distance all molecules share one rate. Static κ² (``"slow"``): every molecule
keeps its own κ² -- from the distribution *compute κ²* left on the model, else the isotropic distribution of
fixed random orientations -- so even one distance becomes a spread of rates; E and τ_F follow a different curve.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.fret_line import find_parameter
from chisurf.core.models.tcspc import kappa2_controls as k2
from chisurf.plugins.fret_line.core.algorithms import (
    _build_component,
    compute_fret_line_for_models,
)

SWEEP = {"kind": "param", "component": 0, "name": "distance.mean.0"}


def line(mode: str, kappa2: float | None = None) -> dict:
    model = _build_component("FRET: FD (Gaussian)")
    if kappa2 is not None:
        find_parameter(model, "fret.kappa2").value = kappa2
    k2.set_orientation_mode(model, mode)
    response = compute_fret_line_for_models([model], SWEEP, 20.0, 100.0, 17, tau_d0=4.0)
    assert response["ok"], response
    return {k: np.asarray(v) for k, v in response["result"].items()}


@pytest.mark.parametrize("kappa2", [None, 0.2, 2.0])
def test_static_and_dynamic_kappa2_give_different_lines(kappa2):
    dynamic, static = line("fast", kappa2), line("slow", kappa2)
    assert np.max(np.abs(dynamic["e_fret"] - static["e_fret"])) > 0.1
    assert np.max(np.abs(dynamic["tau_f"] - static["tau_f"])) > 0.5


def test_static_kappa2_spreads_the_rates_at_short_distance():
    """At R << R0 dynamic averaging quenches the donor almost fully; the low-κ² molecules of a static
    ensemble still emit, so E is lower and τ_F longer."""
    dynamic, static = line("fast"), line("slow")
    assert dynamic["e_fret"][0] > static["e_fret"][0] + 0.02
    assert static["tau_f"][0] > dynamic["tau_f"][0] + 0.5


def test_the_dynamic_line_follows_the_scalar_kappa2_and_the_static_one_the_isotropic_ensemble():
    """The scalar κ² is the dynamic average; the static average (isotropic, nothing computed) does not
    read the scalar."""
    assert np.max(np.abs(line("fast", 0.2)["e_fret"] - line("fast", 2.0)["e_fret"])) > 0.1
    np.testing.assert_allclose(line("slow", 0.2)["e_fret"], line("slow", 2.0)["e_fret"], rtol=1e-12)


def computed_line(mode: str, k2_values, weights, kappa2: float | None = None) -> dict:
    model = _build_component("FRET: FD (Gaussian)")
    k2.apply_kappa2_distribution(model, k2_values, weights)
    if kappa2 is not None:
        find_parameter(model, "fret.kappa2").value = kappa2
    k2.set_orientation_mode(model, mode)
    response = compute_fret_line_for_models([model], SWEEP, 20.0, 100.0, 17, tau_d0=4.0)
    assert response["ok"], response
    return {k: np.asarray(v) for k, v in response["result"].items()}


def test_a_computed_kappa2_distribution_reaches_the_static_average():
    """*compute κ²*'s result is what the static average averages over: a narrow distribution
    around 0.1 is far from the isotropic line (it measured ΔE = 0.0 before the fix)."""
    narrow = computed_line("slow", [0.09, 0.1, 0.11], [1, 2, 1])
    assert np.max(np.abs(narrow["e_fret"] - line("slow")["e_fret"])) > 0.2
    # ... and close to the dynamic line at its mean, a narrow spread changes little.
    assert np.max(np.abs(narrow["e_fret"] - line("fast", 0.1)["e_fret"])) < 2e-3


def test_a_static_delta_at_two_thirds_is_the_dynamic_line():
    static = computed_line("slow", [2.0 / 3.0], [1.0])
    dynamic = line("fast", 2.0 / 3.0)
    np.testing.assert_array_equal(static["e_fret"], dynamic["e_fret"])
    np.testing.assert_array_equal(static["tau_f"], dynamic["tau_f"])


def test_show_kappa2_reports_the_distribution_the_model_uses():
    model = _build_component("FRET: FD (Gaussian)")
    assert k2.kappa2_pairs(model) == [(1.0, k2.scalar_kappa2(model))]  # dynamic: one κ²
    k2.set_orientation_mode(model, "slow")
    isotropic = k2.kappa2_pairs(model)  # static, nothing computed: the isotropic grid
    assert len(isotropic) == 128 and sum(w * v for w, v in isotropic) == pytest.approx(2 / 3, abs=5e-3)
    k2.apply_kappa2_distribution(model, [0.09, 0.1, 0.11], [1, 2, 1])
    shown = k2.kappa2_distribution(model)
    assert shown["mode"] == "slow" and shown["k2"] == [0.09, 0.1, 0.11]
    np.testing.assert_allclose(shown["p_k2"], [0.25, 0.5, 0.25])
    # Held on the native port, so a saved model carries it.
    assert model.get_state()["value_ports"]["kappa2_distribution"] == [0.25, 0.09, 0.5, 0.1, 0.25, 0.11]
