"""Simulate the fluorescence decay of a dye tethered to a protein.

QuEst builds the dye's accessible volume, lets the dye diffuse in it, and
quenches it by photo-induced electron transfer (PET) whenever it touches an
electron-rich side chain. The result is a decay you could compare with a TCSPC
measurement, plus the numbers that summarise it.

The structure is T4 lysozyme (PDB 148L), shipped beside this script. Run it in
the ChiSurf environment:

    python chisurf/plugins/quenching_estimator/examples/01_donor_quenching.py

Theory: docs/concepts/dye_quenching.md.
"""

from pathlib import Path

import numpy as np
from emtk.figure import Figure

from chisurf.plugins.quenching_estimator.api import local as quest

STRUCTURE = Path(__file__).resolve().parent / "148l.pdb"

# A project is a plain dictionary. The template is valid; we only point it at
# the structure and a labelling site.
project = quest.template(with_fret=False)
project["pdb"] = str(STRUCTURE)
project["attachment"] = {"chain": "E", "residue": 5, "atom": "CB"}

# Short run so the example finishes in seconds. Real work uses tens of
# microseconds (t_max, in ns) and millions of photons.
project["t_max"] = 400.0
project["n_photons"] = 200_000
project["n_bins"] = 256
project["random_seed"] = 2026

print(f"structure : {STRUCTURE.name}")
print(f"site      : E:5 (CB), tau0 = {project['tau0']} ns")

result = quest.simulate(project)

print("\n--- decay ---")
print(f"  bins               {result.time.size} over {result.time[-1]:.1f} ns")
print(f"  photons            {int(result.donor_counts.sum()):,}")
print("\n--- derived quantities ---")
print(f"  quantum yield      {result.quantum_yield_donor:.3f}   (1 = not quenched)")
print(f"  contact fraction   {result.collisions_fraction * 100:.2f} % of frames")
print(f"  accessible volume  {result.av_volume:.0f} A^3")

# Quenching is resolved per residue type. Site E:5 sits next to a tryptophan.
print("\n--- what quenches the dye ---")
for entry in quest.top_quenchers(result.aa_residence, limit=5):
    print(f"  {entry['residue_name']:>4s}  {entry['quench_rate_fraction'] * 100:5.1f} % of the quenching")

# A second site with no quencher in reach, for comparison.
far = dict(project)
far["attachment"] = {"chain": "E", "residue": 69, "atom": "CB"}
unquenched = quest.simulate(far)
print(f"\nsite E:69 quantum yield {unquenched.quantum_yield_donor:.3f}")
assert result.quantum_yield_donor < unquenched.quantum_yield_donor

# Two lifetimes, two different averages. QY x tau0 weights every excited dye
# equally; the mean photon arrival time weights each by the light it emits.
# A dye in contact with the tryptophan decays within a few hundred ps and emits
# few photons, so the light comes mostly from dyes away from it: the decay
# loses amplitude in a fast component more than it shortens.
print(f"QY x tau0                {result.quantum_yield_donor * project['tau0']:.2f} ns  (species-averaged)")
print(f"mean photon arrival time {result.lifetime_donor:.2f} ns  (intensity-averaged)")
assert result.quantum_yield_donor * project["tau0"] < result.lifetime_donor

# Both runs excite the same number of dyes, so one common scale shows the
# missing amplitude; normalising each curve to its own peak would hide it.
scale = unquenched.donor_counts.max()
fig = Figure(size=(720, 480))
ax = fig.ax()
for label, r in (("E:5, next to TRP", result), ("E:69, no quencher", unquenched)):
    c = np.clip(r.donor_counts.astype(float), 0.1, None)
    ax.line(r.time, c / scale, label=f"{label}: QY {r.quantum_yield_donor:.2f}")
ax.set_log(y=True)
ax.set_xlim(0, 25)
ax.set_labels("time / ns", "counts / peak of E:69")
ax.set_title("Donor decay at two labelling sites")
ax.legend()
fig.save("01_donor_quenching.png")
