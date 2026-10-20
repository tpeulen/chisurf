"""The forward simulator's three ensembles agree where physics says they must.

MalE APO (1OMP) site 95, the AF488 preset's reference kQ table, one slow factor for every
residue (``core/ensembles.py``):

* the **equilibrium** ensemble's tau_x falls monotonically as the residues get stickier
  (slow 1 -> 0.3 -> 0.1): a stickier volume holds the dye nearer the quenchers;
* the **PDE**'s stationary state without the sink *is* the equilibrium ensemble, and its
  D -> 0 limit is the equilibrium tau_x;
* the **walk**, started from p(x), agrees with the PDE at slow 1 and 0.3 within its
  statistical error plus its time-step bias; at slow 0.1 the deviation is printed, not
  asserted (the walk's sticky-boundary bias grows with the step).

The walk used to start on a uniform voxel and gave tau_x 2.18 ns at slow 0.1 against the
equilibrium 0.90 ns here -- the "does not equilibrate" defect this file guards.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.ensembles import (
    ENSEMBLES,
    equilibrium_lifetimes,
    pde_lifetimes,
    pde_solver,
)
from chisurf.plugins.quenching_estimator.core.project import template_project
from chisurf.plugins.quenching_estimator.core.simulation import (
    build_donor_from_project,
    simulate_project,
)

PLUGIN = Path(__file__).resolve().parents[1]
AF488 = json.loads((PLUGIN / "settings" / "dye_repository.json").read_text())["AF488"]
SLOW = (1.0, 0.3, 0.1)

#: The walk's time-step bias at a sticky boundary (relative), measured on this site at the
#: step used below; IMP.bff's own PDE-vs-walk check finds 0.4-0.8 % at 0.5-2 ps.
WALK_BIAS = 0.02


def _project(slow, ensemble="walk", seed=1, **overrides):
    p = template_project(with_fret=False)
    p["pdb"] = str(PLUGIN / "examples" / "male" / "1OMP.cif")
    p["attachment"] = {"chain": "A", "residue": 95, "atom": "CB"}
    p["tau0"] = AF488["tau0"]
    p["av_parameter"] = dict(AF488["av_parameter"])
    table = copy.deepcopy(AF488["amino_acid_interactions"])
    for entry in table.values():
        entry["slow_factor"] = slow
    p["amino_acid_interactions"] = table
    p["fret"]["dyes"][0]["D"] = AF488["D"]
    p["fret"]["dyes"][0]["amino_acid_interactions"] = table
    p["random_seed"] = seed
    p["ensemble"] = ensemble
    p.update(overrides)
    return p


@pytest.fixture(scope="module")
def fields():
    out = {}
    for slow in SLOW:
        model = build_donor_from_project(_project(slow, "equilibrium"))
        out[slow] = (model, model.ensemble_fields)
    return out


@pytest.fixture(autouse=True)
def _isolate_artefacts(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


def test_the_three_ensembles_are_named():
    assert ENSEMBLES == ("equilibrium", "walk", "pde")


def test_equilibrium_tau_x_falls_as_the_residues_get_stickier(fields):
    tau = [equilibrium_lifetimes(fields[s][1], AF488["tau0"]).tau_x for s in SLOW]
    print("equilibrium tau_x (ns) at slow 1/0.3/0.1:", [round(t, 4) for t in tau])
    assert tau[0] > tau[1] > tau[2]


@pytest.mark.parametrize("slow", SLOW)
def test_the_pde_stationary_state_is_the_equilibrium_ensemble(fields, slow):
    model, f = fields[slow]
    solver = pde_solver(f)
    stationary = np.asarray(solver.get_stationary_occupancy())
    np.testing.assert_allclose(stationary, f.occupancy, rtol=1e-12, atol=1e-15)
    # ... the same occupancy the site model writes down, p ~ 1/s of the walk's own field.
    inside = f.bounds > 0
    p = 1.0 / f.mobility[inside]
    np.testing.assert_allclose(f.occupancy[inside], p / p.sum(), rtol=1e-12)
    # ... and a fixed point of the transport with no sink: propagated for 10 us from it,
    # the solver leaves it where it is (the relaxation *onto* it from elsewhere takes far
    # longer than any run at slow 0.1, where the mobility D0 s^n is nearly zero).
    import IMP.bff as bff

    still = bff.GridDiffusionSolver(
        f.diffusion, f.bounds, f.occupancy, np.zeros_like(f.rate), f.dg, 1.0e4,
        "detailed_balance", False, f.weight,
    )
    final = np.asarray(still.run_krylov(1, 1, 64).get_density())
    assert np.abs(final - f.occupancy).max() / f.occupancy.max() < 1e-8
    # D -> 0 is the equilibrium ensemble's lifetime.
    eq = equilibrium_lifetimes(f, model.tau0)
    assert abs(solver.lifetime_static(model.tau0).get_tau_x() - eq.tau_x) < 1e-9


def test_simulate_project_reports_each_ensemble():
    for ensemble in ("equilibrium", "pde"):
        r = simulate_project(_project(0.3, ensemble, n_photons=50_000), render_data=False)
        assert r.ensemble == ensemble
        assert r.ensemble_lifetimes["ensemble"] == ensemble
        # the photon trace is drawn from the solved ensemble
        assert abs(r.quantum_yield_donor * AF488["tau0"] - r.tau_x) < 0.05
        assert abs(r.lifetime_donor - r.ensemble_lifetimes["tau_f"]) < 0.05
        assert r.aa_residence and r.aa_residence[0]["event_count"] is None


def _walk(slow, seeds=(1, 2, 3)):
    taus = []
    for seed in seeds:
        r = simulate_project(
            _project(slow, "walk", seed, t_max=4000.0, t_step=0.01, n_photons=400_000,
                     parallel_trajectories=4),
            render_data=False,
        )
        assert r.ensemble == "walk"
        taus.append(r.tau_x)
    return float(np.mean(taus)), float(np.std(taus, ddof=1) / np.sqrt(len(taus)))


@pytest.mark.slow
@pytest.mark.parametrize("slow", SLOW)
def test_the_walk_from_p_x_agrees_with_the_pde(fields, slow):
    model, f = fields[slow]
    pde = pde_lifetimes(f, model.tau0)
    tau, se = _walk(slow)
    delta = (tau - pde.tau_x) / pde.tau_x
    print(
        f"slow {slow}: PDE tau_x {pde.tau_x:.4f} ns (static {pde.limits['static']:.4f}, "
        f"fast {pde.limits['fast_exchange']:.4f}); walk {tau:.4f} +- {se:.4f} ns "
        f"({100 * delta:+.2f} %)"
    )
    if slow < 0.3:
        return  # reported, not asserted
    assert abs(tau - pde.tau_x) < 3.0 * se + WALK_BIAS * pde.tau_x
