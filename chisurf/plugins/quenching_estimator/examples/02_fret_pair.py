"""Simulate a FRET pair: donor, acceptor, and the transfer between them.

Both dyes diffuse in their accessible volumes and the transfer rate
k_FRET(t) = (1/tau0) (R0 / R_DA(t))^6 is evaluated for every trajectory frame,
so the FRET decay follows where the dyes actually are. The ratio of the two
decays is the time-resolved transfer efficiency E(t) that example 04 turns into
a distance distribution.

Run it in the ChiSurf environment:

    python chisurf/plugins/quenching_estimator/examples/02_fret_pair.py

Theory: docs/concepts/fret.md, docs/concepts/dye_quenching.md.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from chisurf.plugins.quenching_estimator.api import local as quest
from chisurf.plugins.quenching_estimator.core.project import DEFAULT_FORSTER_RADIUS

STRUCTURE = Path(__file__).resolve().parent / "148l.pdb"
DONOR, ACCEPTOR = 55, 132


def fret_project(r0):
    """A donor/acceptor project on T4L. *r0* is the Forster radius in Angstrom."""
    project = quest.template(with_fret=True)
    project["pdb"] = str(STRUCTURE)
    project["attachment"] = {"chain": "E", "residue": DONOR, "atom": "CB"}
    project["fret"]["dyes"][0]["attachment"] = dict(project["attachment"])
    project["fret"]["dyes"][1]["attachment"] = {"chain": "E", "residue": ACCEPTOR, "atom": "CB"}
    project["fret"]["R0_matrix"] = [[None, r0], [r0, None]]
    project.update(t_max=400.0, n_photons=200_000, n_bins=256, random_seed=2026)
    return project


# R0 is in Angstrom, like every length in a project. A value in nanometres
# (5.2) is ten times too small and switches FRET off.
result = quest.simulate(fret_project(DEFAULT_FORSTER_RADIUS))

print(f"donor E:{DONOR}, acceptor E:{ACCEPTOR}, R0 = {DEFAULT_FORSTER_RADIUS} A")
print(f"  donor alone          QY {result.quantum_yield_donor:.3f}")
print(f"  donor with acceptor  QY {result.quantum_yield_fret:.3f}")
print(f"  transfer efficiency  E  {result.fret_efficiency:.3f}")

# E(t) = 1 - f_DA(t) / f_D0(t). Both histograms count photons per excitation,
# so their ratio needs no extra normalisation.
t = result.time
fd0 = result.donor_counts.astype(float)
fda = result.fret_counts.astype(float)
usable = (fd0 > 20.0) & (t > 0.5) & (t < 20.0)
et = 1.0 - fda[usable] / fd0[usable]
print(f"  E(t) early ({t[usable][0]:.1f} ns) {et[0]:.3f}, late ({t[usable][-1]:.1f} ns) {et[-1]:.3f}")

# A smaller Forster radius must transfer less: one more run catches a unit error.
weak = quest.simulate(fret_project(35.0))
print(f"  R0 = 35 A gives E = {weak.fret_efficiency:.3f}")
assert weak.fret_efficiency < result.fret_efficiency

fig, (ax, bx) = plt.subplots(1, 2, figsize=(10, 4))
ax.semilogy(t, np.clip(fd0, 0.1, None) / fd0.max(), label="donor only")
ax.semilogy(t, np.clip(fda, 0.1, None) / fd0.max(), label="donor + acceptor")
ax.set_xlim(0, 25)
ax.set_xlabel("time / ns")
ax.set_ylabel("counts / max(donor only)")
ax.legend()
bx.plot(t[usable], et)
bx.set_ylim(0, 1)
bx.set_xlabel("time / ns")
bx.set_ylabel("E(t)")
bx.set_title("Time-resolved transfer efficiency")
fig.tight_layout()
fig.savefig("02_fret_pair.png", dpi=120)
plt.show()
