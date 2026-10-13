"""ProteinMC on T4 lysozyme (148L): one FRET distance restraint pulls a CA-CA pair 15 A closer.

Runs the headless runner (ProteinMC has no window) and plots the labeling chi-square and the RMSD to
the start structure against the written frame; writes ``figures/106_protein_monte_carlo.png``.
"""
import json
import pathlib
import sys
import tempfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from chisurf.plugins.modelling.proteinmc.model import ProteinMCRunner, load_structure  # noqa: E402

PDB = REPO / "test/data/atomic_coordinates/pdb_files/148l.pdb"


def _text(value):
    return value.decode().strip() if isinstance(value, bytes) else str(value).strip()


def _position(atom):
    return {
        "atom_name": "CA",
        "chain_identifier": _text(atom["chain"]),
        "residue_seq_number": int(atom["res_id"]),
        "residue_name": _text(atom["res_name"]),
        "attachment_atom_index": int(atom["i"]),
    }


def main():
    """Write a restraint file, run 4000 trials, plot the trace."""
    atoms = load_structure(PDB).atoms
    ca = [i for i in range(len(atoms)) if _text(atoms[i]["atom_name"]) == "CA"]
    a0, a1 = atoms[ca[10]], atoms[ca[150]]
    start = float(np.linalg.norm(a0["xyz"] - a1["xyz"]))
    target = start - 15.0
    work = pathlib.Path(tempfile.mkdtemp())
    labeling = work / "restraint.fps.json"
    labeling.write_text(json.dumps({
        "Positions": {"p1": _position(a0), "p2": _position(a1)},
        "Distances": {"p1_p2": {
            "Forster_radius": 52.0, "distance_type": "RDAMean", "position1_name": "p1",
            "position2_name": "p2", "distance": target, "error_neg": 1.0, "error_pos": 1.0}},
    }))
    result = ProteinMCRunner(
        PDB,
        settings={"n_iter": 4000, "n_out": 5, "n_written": 200, "scale": 0.05, "kt": 1.5,
                  "potentials": [{"name": "dye", "weight": 1.0,
                                  "settings": {"labeling_file": str(labeling)}}]},
        output_file=work / "run.rmf3",
    ).run()
    print(f"start {start:.1f} A, target {target:.1f} A, accepted {result.accepted}, "
          f"rejected {result.rejected}, frames {result.n_frames}")
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(6.5, 4.6), sharex=True)
    top.semilogy(result.labeling_energies, color="#1f77b4")
    top.set_ylabel(r"restraint $\chi^2$")
    bottom.plot(result.rmsd, color="#d62728")
    bottom.set_ylabel("RMSD to start (Å)")
    bottom.set_xlabel("written frame")
    fig.tight_layout()
    fig.savefig(REPO / "docs/guides/figures/106_protein_monte_carlo.png", dpi=130)


if __name__ == "__main__":
    main()
