"""The PET quenching parameters as a *posterior*, fitted the way photon data should be.

    PYTHONPATH=. python test/benchmarks/benchmark_quenching_posterior.py

IMP.bff's PRD-111 established that the quenching parameter vector is not
recoverable from one fluorescence decay and is only partly recoverable from
several. Stages 0-1 there answered that with a Levenberg-Marquardt point fit
under Gaussian weights, which is wrong three times over, and this benchmark is
the replacement. Each layer does its own job:

**The statistic.** Those fits minimised ``(F_model - F_obs) / sqrt(max(N F, 1))``
-- which is ``tttrlib``'s ``statistics::neyman`` down to the ``max(1, .)`` clamp,
and which ``tttrlib.fit_objectives_json()`` itself describes as *"biased low at
small counts because a channel that happens to fluctuate down is given more
weight"*, against ``poisson_mle`` (2I*) being *"what a TCSPC decay should
normally be fitted with"*. These decays run to essentially nothing inside the
window, so most of the axis is that regime. Here the objective is
:func:`chisurf.core.fitting.deviance_residuals`, the signed Poisson deviance,
and the data are genuine Poisson draws rather than Gaussian noise.

**The answer.** A condition number of 1e5 and a demonstrated second minimum mean
there is no unique solution to report; the content of the answer is the shape of
the posterior and its correlations. So this samples with
:class:`chisurf.core.fitting.ensemble.EnsembleSampler` and reports
:func:`chisurf.core.fitting.diagnostics.summarize` -- credible intervals with
R-hat and ESS beside them -- not an argmax with a curvature error bar.

**The prior.** ``IMP.bff.PET_QUENCHING_REFERENCE`` ships with the sentence
*"starting values meant to be calibrated against measured lifetimes, not fixed
constants"*. That is a prior, and a bounded uniform search over
``kQ_scale in [0.05, 10]`` throws it away. Here it is a log-normal centred on the
published values, which is what that sentence means.

**Staged, as a group fit.** :meth:`chisurf.core.fitting.fit.FitGroup.run` with
``local_first=True`` fits each member and then the shared parameters; the same
structure is used here, sampling each site's own posterior before the joint one,
so what a single site can say is visible beside what six say together.

The forward model is IMP.bff's field solver at ``flux_form="smoluchowski"``: a
mobility field must not decide where the dye sits at equilibrium, which is the
structure the Haas-Steinberg equation is written in.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import IMP
import IMP.atom
import IMP.bff
import IMP.core
from IMP.bff.quenching import maps
from IMP.bff.quenching import (
    GridDiffusionSolver,
    diffusion_stability_limit,
    equilibrium_occupancy,
)

from chisurf.core.fitting import deviance_residuals
from chisurf.core.fitting.diagnostics import convergence_warnings, summarize
from chisurf.core.fitting.ensemble import (
    AdaptiveCovarianceMove, EnsembleSampler, EnsembleSliceSampler,
)
from chisurf.core.fitting.priors import LogNormalPrior, TruncatedNormalPrior

STRUCTURE = "structure/T4L/3GUN.pdb"

#: The same six sites PRD-111 stage 0 used, spanning quencher coverage.
SITES = (
    dict(chain="A", residue=132, atom="CB", note="PRD-110 reference"),
    dict(chain="A", residue=124, atom="CB", note="TRP126 at 3.5 A -- contact"),
    dict(chain="A", residue=93, atom="CB", note="CYS97/TRP158 -- crowded"),
    dict(chain="A", residue=19, atom="CB", note="TYR18/TYR25 -- many, medium"),
    dict(chain="A", residue=65, atom="CB", note="HIS31 at 9.7 A -- sparse"),
    dict(chain="A", residue=53, atom="CB", note="CYS54, otherwise bare"),
)

#: ``contact_distance`` is **fixed, not fitted**. PRD-111 measured it at +-61 %
#: with its own eigenvector at lambda = 2.66, and a least-squares fit walked it
#: to its bound: it is uninformative rather than degenerate, and sampling it only
#: buys a flat direction that wastes walkers.
CONTACT_DISTANCE = 6.5

#: name, truth, prior. The priors are the point of the exercise, so each says
#: where it comes from.
PARAMETERS = (
    # `kQ` ships as "starting values meant to be calibrated": a factor-of-two
    # prior about the published chemistry is exactly that statement.
    ("kQ_scale", 1.0, LogNormalPrior(mu=0.0, sigma=np.log(2.0))),
    # The PET attenuation length. van der Waals contact chemistry puts it near
    # 1.5 A and it cannot be far from that without ceasing to be PET.
    ("rC", 1.5, LogNormalPrior(mu=float(np.log(1.5)), sigma=0.35)),
    # A dye's translational diffusion in water is a few A^2/ns; tethered and
    # crowded it is lower. Wide, but not uninformative.
    ("free_diffusion", 8.0, LogNormalPrior(mu=float(np.log(8.0)), sigma=0.8)),
    # Applied once per contacting atom, so it compounds; only the top of the
    # range is meaningful and the prior says so rather than the bounds alone.
    ("slow_factor", 0.985, TruncatedNormalPrior(
        mu=1.0, sigma=0.05, lb=0.80, ub=1.0)),
)
NAMES = [p[0] for p in PARAMETERS]
TRUTH = np.array([p[1] for p in PARAMETERS])
PRIORS = [p[2] for p in PARAMETERS]

#: Hard bounds. ``free_diffusion`` stops at 25 A^2/ns rather than 40: the prior
#: puts that at 2.5 sigma, and the explicit-scheme time step is set by the
#: largest D the sampler may reach, so the ceiling is most of the cost.
BOUNDS = np.array([[0.05, 10.0], [0.3, 5.0], [0.5, 25.0], [0.80, 1.0]])

TAU0 = 4.0
T_MAX = 25.0
N_TIME = 64
N_PEAK_COUNTS = 10_000


def load_atoms(pdb_path):
    model = IMP.Model()
    hierarchy = IMP.atom.read_pdb(
        pdb_path, model, IMP.atom.NonWaterNonHydrogenPDBSelector())
    dtype = [("chain", "U4"), ("res_id", "i8"), ("res_name", "U4"),
             ("atom_name", "U4"), ("coord", "f8", 3), ("radius", "f8")]
    rows = []
    for leaf in IMP.atom.get_leaves(hierarchy):
        atom = IMP.atom.Atom(leaf)
        residue = IMP.atom.get_residue(atom)
        rows.append((
            IMP.atom.get_chain(residue).get_id(), residue.get_index(),
            residue.get_residue_type().get_string(),
            atom.get_atom_type().get_string().strip(),
            IMP.core.XYZ(leaf).get_coordinates(),
            IMP.core.XYZR(leaf).get_radius(),
        ))
    return np.array(rows, dtype=dtype)


def quencher_table(kQ_scale: float, rC: float):
    return {
        residue: {atom: (float(ref["kQ"]) * kQ_scale, rC)
                  for atom in IMP.bff.QUENCHER_ATOMS[residue]}
        for residue, ref in IMP.bff.PET_QUENCHING_REFERENCE.items()
    }


class Site:
    """One labelling site: geometry once, then a decay per parameter vector."""

    def __init__(self, pdb_path, atoms, site, resolution):
        self.site = site
        self.atoms = atoms
        self.av = IMP.bff.get_av(
            np.zeros((1, 4)), np.zeros(3), 20.0, 0.5, (3.5, 3.5, 3.5),
            disc_step=resolution, pdb_path=pdb_path,
            source_info={
                "chain_identifier": site["chain"],
                "residue_seq_number": site["residue"],
                "atom_name": site["atom"],
                "simulation_type": "AV1",
                "linker_length": 20.0, "linker_width": 0.5, "radius1": 3.5,
                "allowed_sphere_radius": 2.1,
            },
        )
        self.dg = float(self.av.grid_step)
        if abs(self.dg - float(resolution)) > 1e-9:
            raise RuntimeError(f"asked for {resolution} A, got {self.dg} A")
        self.density = np.ascontiguousarray(self.av.density, dtype=np.float64)
        self.x0 = np.asarray(self.av.attachment_point, dtype=np.float64)
        self.bounds = (self.density > 0).astype(np.float64)
        self.xyz = np.ascontiguousarray(self.atoms["coord"], dtype=np.float64)
        edge = self.bounds.copy()
        edge[1:-1, 1:-1, 1:-1] = 0.0
        if edge.any():
            for name in ("density", "bounds"):
                grid = getattr(self, name)
                padded = np.zeros(tuple(n + 2 for n in grid.shape))
                padded[1:-1, 1:-1, 1:-1] = grid
                setattr(self, name, np.ascontiguousarray(padded))
        self.time = np.linspace(0.0, T_MAX, N_TIME)
        # One time step for every theta: deriving it from D_max would make the
        # discretisation error a function of the parameter being sampled.
        self.t_step = 0.5 * diffusion_stability_limit(float(BOUNDS[2, 1]), self.dg)
        self.n_evaluations = 0

    def decay(self, theta) -> np.ndarray:
        kQ_scale, rC, free_diffusion, slow_factor = theta
        self.n_evaluations += 1
        d_map = maps.diffusion_coefficient_map(
            self.density, self.x0, self.dg, self.xyz,
            free_diffusion=free_diffusion, min_distance=CONTACT_DISTANCE,
            slow_factor=slow_factor)
        kQ, rC_atoms = maps.atomic_quenching_parameters(
            self.atoms, quencher_table(kQ_scale, rC))
        rate = maps.quenching_rate_map(
            self.density, self.x0, self.dg, self.xyz, kQ, rC_atoms,
            tau0=TAU0, dye_radius=3.5)
        start = equilibrium_occupancy(d_map, self.bounds, "smoluchowski")
        solver = GridDiffusionSolver(
            d_map, self.bounds, start, rate, t_step=self.t_step, dg=self.dg,
            flux_form="smoluchowski")
        result = solver.run(max(1, int(T_MAX / self.t_step)), n_out=64)
        curve = np.interp(self.time, result.time, result.fluorescence)
        return curve / curve[0] if curve[0] > 0 else curve

    def counts(self, theta) -> np.ndarray:
        """Expected counts, which is what a Poisson likelihood compares against."""
        return self.decay(theta) * N_PEAK_COUNTS


def log_posterior(theta, sites, observed):
    """Poisson 2I* deviance plus the priors, as a log-probability."""
    if np.any(theta < BOUNDS[:, 0]) or np.any(theta > BOUNDS[:, 1]):
        return -np.inf
    log_prior = 0.0
    for value, prior in zip(theta, PRIORS):
        log_prior += float(prior.lnpdf(value))
    if not np.isfinite(log_prior):
        return -np.inf
    deviance = 0.0
    for site, data in zip(sites, observed):
        model = site.counts(theta)
        if not np.all(np.isfinite(model)):
            return -np.inf
        residuals = deviance_residuals(data, model)
        deviance += float(np.sum(residuals ** 2))
    # sum r^2 == 2I*, and the Poisson log-likelihood is -2I*/2 up to a constant.
    return log_prior - 0.5 * deviance


def residual_shape(site, data, theta) -> dict:
    """What chi-squared cannot see: whether the residuals have structure.

    A reduced chi-squared of 1.0 is reported by an under-determined fit and by a
    misfitting one alike. Sign runs and lag-1 correlation separate them: white
    residuals scatter, a wrong model leaves the curve's shape behind in them.
    """
    residuals = deviance_residuals(data, site.counts(theta))
    signs = np.sign(residuals)
    signs = signs[signs != 0]
    runs = int(1 + np.sum(signs[1:] != signs[:-1])) if signs.size else 0
    n_pos, n_neg = int(np.sum(signs > 0)), int(np.sum(signs < 0))
    n = n_pos + n_neg
    if n_pos and n_neg:
        expected = 1.0 + 2.0 * n_pos * n_neg / n
        variance = (2.0 * n_pos * n_neg * (2.0 * n_pos * n_neg - n)) / (n * n * (n - 1.0))
        z_runs = (runs - expected) / np.sqrt(variance) if variance > 0 else np.nan
    else:
        expected, z_runs = np.nan, np.nan
    centred = residuals - residuals.mean()
    denominator = float(np.sum(centred ** 2))
    lag1 = float(np.sum(centred[1:] * centred[:-1]) / denominator) if denominator else np.nan
    return {
        "reduced_2istar": float(np.sum(residuals ** 2) / max(len(residuals) - len(NAMES), 1)),
        "runs": runs, "runs_expected": float(expected), "runs_z": float(z_runs),
        "lag1_autocorrelation": lag1,
    }


def sample(sites, observed, n_walkers, n_steps, seed, label, sampler_kind="slice"):
    """Sample the posterior.

    **The proposal matters more than the step count here.** This posterior is
    strongly correlated -- PRD-111 measured a condition number around 1e5 -- and
    ChiSurf benchmarks exactly that case
    (``test/benchmarks/benchmark_sampling.py``, table in
    ``docs/development/benchmarks.md``). On an 8-D Gaussian at kappa = 100 the
    effective samples *per log-probability evaluation* are 0.0036 for the
    stretch move, 0.0085 for a differential slice and **0.0109** for an adaptive
    covariance slice -- 3x -- and the documentation notes the gap grows with the
    correlation.

    Per-evaluation is the metric that counts: one evaluation here is six forward
    solves, ~0.36 s, so the sampler choice is a straight multiplier on wall
    clock. The first run of this benchmark used the stretch move, which is the
    proposal that table says to avoid.
    """
    rng = np.random.default_rng(seed)
    start = TRUTH * np.exp(rng.normal(0.0, 0.25, size=(n_walkers, len(TRUTH))))
    start = np.clip(start, BOUNDS[:, 0] * 1.01, BOUNDS[:, 1] * 0.99)
    if sampler_kind == "stretch":
        sampler = EnsembleSampler(
            n_walkers, len(TRUTH), log_posterior, args=(sites, observed), seed=seed)
    else:
        sampler = EnsembleSliceSampler(
            n_walkers, len(TRUTH), log_posterior, args=(sites, observed),
            moves=AdaptiveCovarianceMove(), seed=seed)
    t0 = time.perf_counter()
    sampler.run_mcmc(start, n_steps)
    elapsed = time.perf_counter() - t0
    chain = np.asarray(sampler.get_chain())          # (n_steps, n_walkers, ndim)
    chain = np.transpose(chain, (1, 0, 2))           # -> (n_chains, n_draws, ndim)
    rows = summarize(chain, names=NAMES)
    print(f"\n  {label}: {n_walkers} walkers x {n_steps} steps, {elapsed:.0f} s")
    print(f"    {'parameter':<16}{'truth':>8}{'median':>10}{'68% CI':>22}"
          f"{'R-hat':>8}{'ESS':>8}")
    for row, truth in zip(rows, TRUTH):
        q = row["quantiles"]
        lo, med, hi = q["0.16"], q["0.5"], q["0.84"]
        print(f"    {row['name']:<16}{truth:>8.3f}{med:>10.3f}"
              f"{f'[{lo:.3f}, {hi:.3f}]':>22}{row['rhat']:>8.3f}{row['ess']:>8.0f}")
    for warning in convergence_warnings(rows):
        print(f"    ! {warning}")
    return chain, rows, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolution", type=float, default=2.5)
    parser.add_argument("--walkers", type=int, default=12)
    parser.add_argument("--steps", type=int, default=700)
    parser.add_argument("--site-steps", type=int, default=400,
                        help="steps for each single-site posterior (stage 1).")
    parser.add_argument("--sampler", default="slice", choices=("slice", "stretch"),
                        help="slice = adaptive-covariance ensemble slice "
                             "(default, ~3x the ESS per evaluation on a "
                             "correlated target); stretch = the affine-invariant "
                             "stretch move, for comparison.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    pdb_path = IMP.bff.get_example_path(STRUCTURE)
    atoms = load_atoms(pdb_path)
    print(f"forward model: IMP.bff field solver, flux_form=smoluchowski, "
          f"{args.resolution} A")
    print(f"statistic: Poisson 2I* (chisurf.core.fitting.deviance_residuals)")
    print(f"sampler: {args.sampler}")
    print(f"priors: " + ", ".join(f"{n}~{type(p).__name__}" for n, p in zip(NAMES, PRIORS)))
    print(f"contact_distance fixed at {CONTACT_DISTANCE} A (uninformative; see PRD-111)")

    sites = [Site(pdb_path, atoms, s, args.resolution) for s in SITES]
    rng = np.random.default_rng(args.seed)
    observed = [rng.poisson(site.counts(TRUTH)).astype(np.float64) for site in sites]
    print(f"\ndata: {len(sites)} decays, genuine Poisson draws peaking at "
          f"{N_PEAK_COUNTS} counts")

    payload = {"resolution": args.resolution, "parameters": NAMES,
               "truth": TRUTH.tolist(), "contact_distance": CONTACT_DISTANCE,
               "single_site": [], "joint": None, "residual_shape": []}

    # Staged, the way FitGroup(local_first=True) is: each member, then the group.
    for site, data in zip(sites, observed):
        tag = f"A{site.site['residue']}.CB"
        _chain, rows, seconds = sample(
            [site], [data], args.walkers, args.site_steps, args.seed,
            f"{tag} alone", args.sampler)
        payload["single_site"].append({
            "site": tag, "seconds": seconds,
            "summary": rows})

    chain, rows, seconds = sample(
        sites, observed, args.walkers, args.steps, args.seed,
        "all six jointly", args.sampler)
    posterior_median = np.array([r["quantiles"]["0.5"] for r in rows])
    payload["joint"] = {
        "seconds": seconds, "median": posterior_median.tolist(),
        "summary": rows}

    print("\n  residual shape at the posterior median "
          "(what a reduced chi-squared of 1.0 hides):")
    print(f"    {'site':<10}{'2I*/dof':>10}{'runs':>7}{'expected':>10}"
          f"{'z':>8}{'lag-1':>9}")
    for site, data in zip(sites, observed):
        shape = residual_shape(site, data, posterior_median)
        tag = f"A{site.site['residue']}.CB"
        payload["residual_shape"].append({"site": tag} | shape)
        print(f"    {tag:<10}{shape['reduced_2istar']:>10.3f}{shape['runs']:>7d}"
              f"{shape['runs_expected']:>10.1f}{shape['runs_z']:>8.2f}"
              f"{shape['lag1_autocorrelation']:>9.3f}")

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
