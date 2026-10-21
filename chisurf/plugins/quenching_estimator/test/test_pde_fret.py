"""FRET on the PDE ensemble: the transfer rate is a second sink on the grid.

The walk pairs donor and acceptor trajectories frame by frame. The PDE has no
trajectory -- its donor is a population on the AV grid -- so its FRET is the
fast-acceptor limit: :func:`.av.fret_rate_trace` (the kernel the walk's
``averaged`` regime already uses) evaluated at the occupied voxel centres, as a
rate *field*. Quenching and transfer are parallel de-excitation channels, so the
field joins the quenching sink and the same ``GridDiffusionSolver.donor_decay``
produces the D-A decay (``core/ensembles.py``).

Pinned here:

* ``fret_rate_grid`` maps the acceptor-averaged kernel onto the grid exactly
  (synthetic grids, hand-built voxel centres as the oracle);
* ``ensemble: "pde"`` accepts FRET in project validation, ``"equilibrium"``
  still does not;
* on the model, FRET enters ONLY as the sink addition -- bounds, mobility,
  weight and diffusion of the D-A maps equal the donor-only ones;
* the D-A solve lands inside its static/fast-exchange limits and below the
  donor-only lifetime, and the photon trace / efficiency round-trip through
  ``simulate_project`` unchanged.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.av import fret_rate_grid, fret_rate_trace
from chisurf.plugins.quenching_estimator.core.ensembles import FRET_ENSEMBLES
from chisurf.plugins.quenching_estimator.core.project import (
    ProjectValidationError,
    template_project,
    validate_project,
)
from chisurf.plugins.quenching_estimator.core.simulation import (
    build_donor_from_project,
    simulate_project,
)

STRUCTURE = Path(__file__).parent / "148l.pdb"

#: The pair test_fret_physics.py uses: a real acceptor within transfer range.
DONOR_ATTACHMENT = {"chain": "E", "residue": 55, "atom": "CB"}
ACCEPTOR_ATTACHMENT = {"chain": "E", "residue": 82, "atom": "CB"}


def _fret_project(ensemble, acceptor_dynamics="averaged", **overrides):
    p = template_project(with_fret=True)
    p["pdb"] = str(STRUCTURE)
    p["attachment"] = dict(DONOR_ATTACHMENT)
    p["fret"]["dyes"][0]["attachment"] = dict(DONOR_ATTACHMENT)
    p["fret"]["dyes"][1]["attachment"] = dict(ACCEPTOR_ATTACHMENT)
    p["fret"]["acceptor_dynamics"] = acceptor_dynamics
    p["ensemble"] = ensemble
    p.update(n_photons=20000, random_seed=11)
    p.update(overrides)
    return p


class TestFretRateGrid:
    """The grid kernel: the walk's acceptor-averaged rate, one value per voxel."""

    def test_the_grid_carries_the_kernel_rate_at_each_occupied_voxel(self):
        density = np.zeros((4, 4, 4))
        density[1, 1, 1] = 1.0
        density[2, 1, 1] = 1.0
        x0 = np.array([10.0, 0.0, -10.0])
        dg = 0.5
        cloud = np.array([[30.0, 0.0, 0.0], [40.0, 0.0, 0.0]])
        grid = fret_rate_grid(density, x0, dg, cloud, R0=52.0, tau0=4.0, r_min=1.0)
        origin = x0 - ((4 - 1) // 2) * dg
        total = 0.0
        for ijk in ((1, 1, 1), (2, 1, 1)):
            centre = origin + np.asarray(ijk) * dg
            oracle = fret_rate_trace(centre[None, :], cloud, 52.0, 4.0, r_min=1.0)[0]
            assert grid[ijk] == pytest.approx(float(oracle))
            total += float(oracle)
        assert grid.sum() == pytest.approx(total)
        assert not grid[density == 0].any()

    def test_an_empty_volume_is_a_zero_map(self):
        grid = fret_rate_grid(
            np.zeros((3, 3, 3)), np.zeros(3), 1.0,
            np.array([[10.0, 0.0, 0.0]]), R0=52.0, tau0=4.0,
        )
        assert not grid.any()


def test_fret_is_accepted_on_the_walk_and_the_pde():
    assert FRET_ENSEMBLES == ("walk", "pde")
    for ensemble in FRET_ENSEMBLES:
        validate_project(_fret_project(ensemble))


def test_fret_is_still_refused_on_the_equilibrium_ensemble():
    with pytest.raises(ProjectValidationError, match="equilibrium"):
        validate_project(_fret_project("equilibrium"))


@pytest.fixture(scope="module")
def pde_fret_model():
    model = build_donor_from_project(_fret_project("pde"))
    model.update_all(verbose=False)
    model.get_histogram_fret()  # the D-A solve runs lazily, as in the GUI
    return model


def test_fret_enters_only_as_the_sink_addition(pde_fret_model):
    model = pde_fret_model
    f, f_da = model.ensemble_fields, model.fret_ensemble_fields
    # FRET changes the sink and nothing else: same volume, stickiness, transport.
    np.testing.assert_array_equal(f_da.bounds, f.bounds)
    np.testing.assert_array_equal(f_da.mobility, f.mobility)
    np.testing.assert_array_equal(f_da.weight, f.weight)
    np.testing.assert_array_equal(f_da.diffusion, f.diffusion)
    k_quench = getattr(model.av, "k_quench_grid", None)
    k_fret = fret_rate_grid(
        model.av.density_fast, model.av.x0, model.av.dg, model.acceptor_av.points,
        R0=model.fret_R0_angstrom, tau0=model.tau0, r_min=model.fret_r_min,
        kappa2=model.fret_kappa2,
    )
    total = k_fret if k_quench is None else k_quench + k_fret
    np.testing.assert_allclose(f_da.unpad(f_da.rate), total, rtol=1e-12)
    np.testing.assert_allclose(f.unpad(f.rate), 0.0 if k_quench is None else k_quench)
    inside = f_da.bounds > 0
    # the transfer rate is strictly positive, so the D-A sink is everywhere at
    # least the quenching one
    assert (f_da.rate[inside] > f.rate[inside]).all()


def test_the_da_solve_lands_inside_its_limits(pde_fret_model):
    model = pde_fret_model
    da = model.fret_ensemble_lifetimes
    donor = model.ensemble_lifetimes
    # IMP.bff's D->0 and D->inf limits bracket the solve: transport moves the
    # lifetime from the static sum toward the fast-exchange one (on these maps
    # the static limit is the larger of the two).
    lo, hi = sorted((da.limits["static"], da.limits["fast_exchange"]))
    assert lo <= da.tau_x <= hi
    assert da.tau_x < donor.tau_x
    assert 0.0 < da.quantum_yield < donor.quantum_yield


def test_the_fret_channel_roundtrips_through_the_model(pde_fret_model):
    model = pde_fret_model
    dts, phs = model.photon_trace_fret
    assert phs.shape == model.photon_trace[1].shape
    x, y = model.get_histogram_fret(nbins=256, range=(0, 20))
    assert y.sum() == phs.sum()
    assert 0.0 < model.quantum_yield_fret < model.quantum_yield
    assert 0.0 < model.fret_efficiency < 1.0


def test_a_pde_fret_project_simulates_end_to_end():
    r = simulate_project(_fret_project("pde"), render_data=False)
    assert r.ensemble == "pde"
    assert r.fret_counts is not None
    assert 0.0 < r.quantum_yield_fret < r.quantum_yield_donor
    assert 0.0 < r.fret_efficiency < 1.0


def test_the_pde_refuses_a_trajectory_acceptor():
    model = build_donor_from_project(_fret_project("pde", acceptor_dynamics="trajectory"))
    model.update_all(verbose=False)
    with pytest.raises(ValueError, match="averaged"):
        model.get_histogram_fret()
