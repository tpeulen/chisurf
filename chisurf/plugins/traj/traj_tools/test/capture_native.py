"""Capture a populated EMTK view of the trajectory-tools hub.

The hub is captured with a populated child session (Convert loaded with a
synthetic trajectory) so the screenshot shows a working workspace, not a
default shell. One size per process: immediate-mode window/table layout state
persists per process.

Usage: ``python -m chisurf.plugins.traj.traj_tools.test.capture_native normal|narrow``
"""
import sys
from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import make_app

SIZES = {"normal": (900, 640), "narrow": (520, 640)}


def _peptide(tmp_dir: Path, n_res: int = 3, n_frames: int = 4):
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


def main():
    size_name = sys.argv[1] if len(sys.argv) > 1 else "normal"
    width, height = SIZES[size_name]
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    dcd, pdb = _peptide(Path("/tmp"))
    app = make_app()
    app.select("Convert")
    child = app.children["Convert"]
    child.model.trajectory = str(dcd)
    child.model.topology_path = str(pdb)
    child.model.append_log("Ready to convert")
    host = NativeHost(app, size=(width, height), backend="offscreen")
    Image.fromarray(np.asarray(host.draw_frame())).save(out / f"native-{size_name}.png")
    host.close()
    print(f"wrote {out / f'native-{size_name}.png'}")


if __name__ == "__main__":
    main()
