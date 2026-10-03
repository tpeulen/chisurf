"""Inputs of the populated captures: the FPS HIV-RT example with the structures named per body, a score set and a FlexFit set.

usage: from fixtures import make; fps, pdbs = make(folder)
Real files only: the example fps.json / PDBs of chisurf/plugins/modelling/fret/examples/fps_hiv_rt (protein_1R0A.pdb, dna.pdb).
"""
import json
import pathlib
import shutil

REPO = pathlib.Path(__file__).resolve().parents[5]
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"


def make(folder):
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("protein_1R0A.pdb", "dna.pdb"):
        shutil.copy(EXAMPLE / name, folder / name)
    payload = json.loads((EXAMPLE / "hiv_rt.fps.json").read_text())
    for name, pos in payload["Positions"].items():
        pos["pdb_path"] = str(folder / ("dna.pdb" if pos["chain_identifier"] == "P" else "protein_1R0A.pdb"))
    names = list(payload["Distances"])
    payload["χ²"] = {"all": {"distances": names}, "first_four": {"distances": names[:4]}}
    payload["FlexFit"] = {"set_1": {
        "Flexible residues": [{"chain_identifier": "A", "residue_seq_number": 6},
                              {"chain_identifier": "A", "residue_seq_number": 7}],
        "Bonds": [[{"chain_identifier": "A", "residue_seq_number": 6, "atom_name": "C"},
                   {"chain_identifier": "A", "residue_seq_number": 7, "atom_name": "N"}]]}}
    fps = folder / "hiv_rt_populated.fps.json"
    fps.write_text(json.dumps(payload, indent=4, sort_keys=True))
    return fps, [folder / "protein_1R0A.pdb", folder / "dna.pdb"]
