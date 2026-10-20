"""Choose a labelling site: simulate several and compare what quenches them.

This is the question QuEst answers before an experiment: which position gives
a dye that is bright, and which one a dye that is deliberately quenched.

Run it in the ChiSurf environment:

    python chisurf/plugins/quenching_estimator/examples/03_labeling_scan.py

Theory: docs/concepts/dye_quenching.md.
"""

from pathlib import Path

import matplotlib.pyplot as plt

from chisurf.plugins.quenching_estimator.api import local as quest

STRUCTURE = Path(__file__).resolve().parent / "148l.pdb"

project = quest.template(with_fret=False)
project["pdb"] = str(STRUCTURE)
project.update(t_max=400.0, n_photons=200_000, n_bins=256, random_seed=2026)

# Candidate sites on chain E, written as fps.json positions. E:100 is buried
# at the default linker width (4.5 A): no accessible volume.
candidates = {
    f"E:{residue}": {"chain_identifier": "E", "residue_seq_number": residue, "atom_name": "CB"}
    for residue in (5, 22, 36, 55, 100, 132, 140)
}
print(f"scanning {len(candidates)} sites on {STRUCTURE.name}\n")

# scan() never raises: a buried or unlabelable site comes back as a record
# with status "failed", so one bad candidate cannot abort the scan. The
# records are keyed by site name, in the order of the candidates.
records = list(quest.scan(project, candidates).values())

header = f"{'site':>6s}  {'QY':>6s}  {'tau/ns':>6s}  {'contact':>7s}  quenched by"
print(header)
print("-" * len(header))
for record in records:
    if record["status"] != "success":
        print(f"{record['name']:>6s}  failed: {record['error'][:60]}")
        continue
    # The dominant quencher is reported even for a trace of quenching; name it
    # only where the quantum yield shows an effect.
    share = record["dominant_quencher_fraction"]
    quenched = share and record["quantum_yield"] < 0.99
    by = f"{record['dominant_quencher']} {share * 100:.0f} %" if quenched else "-"
    print(
        f"{record['name']:>6s}  {record['quantum_yield']:6.3f}  {record['lifetime']:6.2f}  "
        f"{record['contact_fraction'] * 100:6.1f}%  {by}"
    )

ok = [r for r in records if r["status"] == "success"]
assert len(ok) >= 5
assert any(r["status"] == "failed" for r in records)

print("\nA bright site (QY near 1) reports the dye faithfully; a quenched one is")
print("sensitive to its environment. Which you want depends on the experiment.")

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.bar([r["name"] for r in ok], [r["quantum_yield"] for r in ok])
ax.axhline(1.0, color="k", lw=0.6)
ax.set_ylim(0, 1.05)
ax.set_ylabel("quantum yield (1 = not quenched)")
ax.set_title("Labelling-site scan, T4 lysozyme")
fig.tight_layout()
fig.savefig("03_labeling_scan.png", dpi=120)
plt.show()
