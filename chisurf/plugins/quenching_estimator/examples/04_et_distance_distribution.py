"""From E(t) to a donor-acceptor distance distribution, and when it is right.

A donor at distance R decays as exp[-t/tau0 (1 + (R0/R)^6)], so a static
mixture of distances gives

    eps(t) = f_DA(t) / f_D0(t) = sum_R p(R) exp[-t/tau0 (R0/R)^6]

which is linear in p(R). It is solved here by non-negative least squares with
a second-difference smoothness penalty, and the mean of p(R) is compared with
the Forster-averaged distance <R_DA>_E of the two static accessible volumes.

The comparison is only fair when the dyes sample their accessible volumes.
QuEst's default stickiness (slow factor 0.1) traps the Brownian walkers where
they start, so the simulated FRET follows where they got stuck, not the
volume. The script therefore runs once without stickiness and without PET
(where the two must agree) and once with the default stickiness (where they
do not).

Run it in the ChiSurf environment:

    python chisurf/plugins/quenching_estimator/examples/04_et_distance_distribution.py

Theory: docs/concepts/distance_distributions.md, docs/concepts/quenching_inference.md
(ensembles).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from chisurf.core.math import numerics
from chisurf.plugins.quenching_estimator.api import local as quest
from chisurf.plugins.quenching_estimator.core import build_donor_from_project
from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
    default_amino_acid_interactions,
)

STRUCTURE = Path(__file__).resolve().parent / "148l.pdb"
R0 = 52.0  # Angstrom
DONOR, ACCEPTOR = 55, 132


def fret_project(slow_factor):
    """Donor/acceptor project with PET switched off (kQ = 0), so E = 1 - QY_DA."""
    project = quest.template(with_fret=True)
    project["pdb"] = str(STRUCTURE)
    table = default_amino_acid_interactions(slow_factor=slow_factor)
    for entry in table.values():
        entry["kQ"] = 0.0
    project["amino_acid_interactions"] = table
    project["attachment"] = {"chain": "E", "residue": DONOR, "atom": "CB"}
    for dye in project["fret"]["dyes"]:
        dye["amino_acid_interactions"] = table
        dye["random_seed"] = 11
    project["fret"]["dyes"][0]["attachment"] = dict(project["attachment"])
    project["fret"]["dyes"][1]["attachment"] = {"chain": "E", "residue": ACCEPTOR, "atom": "CB"}
    project["fret"]["R0_matrix"] = [[None, R0], [R0, None]]
    project.update(t_max=400.0, n_photons=400_000, n_bins=256, random_seed=11)
    return project


def distance_distribution(result, tau0, r_axis):
    """p(R) from eps(t) by NNLS with a second-difference penalty."""
    t = result.time
    fd0 = result.donor_counts.astype(float)
    fda = result.fret_counts.astype(float)
    usable = (fd0 > 20.0) & (t < 20.0)  # the part of the decay with real statistics
    eps = fda[usable] / fd0[usable]
    A = np.exp(-t[usable, None] / tau0 * (R0 / r_axis[None, :]) ** 6)
    # Without the penalty NNLS answers with a few spikes.
    D = np.diff(np.eye(r_axis.size), n=2, axis=0)
    penalty = 0.05 * np.sqrt(usable.sum())
    p, _ = numerics.nnls(np.vstack([A, penalty * D]), np.concatenate([eps, np.zeros(D.shape[0])]))
    return p / p.sum()


r_axis = np.linspace(20.0, 90.0, 96)

# 1) No stickiness: the walkers sample the volume.
free = fret_project(slow_factor=1.0)
free_result = quest.simulate(free)
p_free = distance_distribution(free_result, free["tau0"], r_axis)
mean_free = float((p_free * r_axis).sum())

# The independent estimate from the static accessible volumes.
model = build_donor_from_project(free)
model.update_all(verbose=False)
rda_e = model.rda_mean_e(n_samples=20000)

# 2) Default stickiness: the walkers stay near where they start.
sticky = fret_project(slow_factor=0.1)
sticky_result = quest.simulate(sticky)
p_sticky = distance_distribution(sticky_result, sticky["tau0"], r_axis)
mean_sticky = float((p_sticky * r_axis).sum())

print(f"donor E:{DONOR}, acceptor E:{ACCEPTOR}, R0 = {R0} A")
print(f"  from the accessible volumes   <R_DA>_E = {rda_e:.1f} A")
print(f"  from E(t), no stickiness      <R>      = {mean_free:.1f} A   (E = {free_result.fret_efficiency:.3f})")
print(f"  from E(t), slow factor 0.1    <R>      = {mean_sticky:.1f} A   (E = {sticky_result.fret_efficiency:.3f})")
print("Without stickiness the decay and the volumes agree. With it, the walk does")
print("not sample the volume within t_max and the decay reports where it got stuck.")
assert abs(mean_free - rda_e) < 3.0

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(r_axis, p_free, lw=2, label=f"E(t), no stickiness: <R> = {mean_free:.0f} A")
ax.plot(r_axis, p_sticky, lw=1.5, ls="--", label=f"E(t), slow factor 0.1: <R> = {mean_sticky:.0f} A")
ax.axvline(rda_e, color="k", ls=":", label=f"<R_DA>_E from the AVs = {rda_e:.0f} A")
ax.set_xlabel("R_DA / A")
ax.set_ylabel("p(R)")
ax.set_title("Distance distribution deconvolved from E(t)")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig("04_et_distance_distribution.png", dpi=120)
plt.show()
