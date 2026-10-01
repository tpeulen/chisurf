"""Capture a populated EMTK view with the actual native host.

Writes ``renders/native-<size>.png`` beside the tests. One size per process:
immediate-mode window/table layout state persists per process, so a narrow
capture in a fresh process shows what a user resizing a fresh window sees.

Usage: ``python -m chisurf.plugins.traj.potential_energy.test.capture_native normal|narrow``
"""
import sys
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app

SIZES = {"normal": (760, 620), "narrow": (440, 620)}


def _peptide(tmp_dir: Path, n_res: int = 3, n_frames: int = 4):
    """Write a small ALA-peptide DCD + PDB; returns (dcd, pdb) paths."""
    from chisurf.core.fio.trajectory import write_dcd
    from chisurf.core.structure import trajectory_data as md

    dcd = tmp_dir / "peptide.dcd"
    pdb = tmp_dir / "peptide.pdb"
    elements = {
        "N": md.element.nitrogen,
        "CA": md.element.carbon,
        "C": md.element.carbon,
        "O": md.element.oxygen,
    }
    topology = md.Topology()
    chain = topology.add_chain()
    for _ in range(n_res):
        residue = topology.add_residue("ALA", chain)
        for name in ("N", "CA", "C", "O"):
            topology.add_atom(name, elements[name], residue)
    rng = np.random.default_rng(0)
    xyz = (10.0 * rng.random((n_frames, 4 * n_res, 3))).astype(np.float32)
    write_dcd(str(dcd), xyz)
    md.Trajectory(xyz=xyz, topology=topology)[0].save_pdb(str(pdb))
    return dcd, pdb


class _RadiusGyrationStub:
    """IMP-free stand-in for the radius-of-gyration potential (same interface)."""

    name = "Radius-Gyration"

    def __init__(self, structure=None):
        self.structure = structure

    def getEnergy(self):  # noqa: N802 (matches the potential interface)
        return 1.0


def main():
    size_name = sys.argv[1] if len(sys.argv) > 1 else "normal"
    width, height = SIZES[size_name]
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    dcd, pdb = _peptide(Path("/tmp"))
    app = make_app()
    app.model.set_trajectory(str(dcd))
    app.model.set_topology(str(pdb))
    app.model.add_potential(_RadiusGyrationStub(), 1.0, name="Radius of Gyration")
    app.model.append_log("Stride 1: every frame is scored")
    app.target = "energies.txt"
    host = NativeHost(app, size=(width, height), backend="offscreen")
    Image.fromarray(np.asarray(host.draw_frame())).save(out / f"native-{size_name}.png")
    host.close()
    print(f"wrote {out / f'native-{size_name}.png'}")


if __name__ == "__main__":
    main()
