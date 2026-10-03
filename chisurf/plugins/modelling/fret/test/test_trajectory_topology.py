"""The trajectory helpers of the pair selection read the core Topology (a chain has no ``residues`` there)."""

from pathlib import Path

from chisurf.core.structure import trajectory_data as md
from chisurf.plugins.modelling.fret.core.trajectory import build_sites, get_chain

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
TOP = REPO / "test/data/atomic_coordinates/trajectory/hgbp1/topol.pdb"


def test_build_sites_on_the_core_topology():
    traj = md.load(str(TOP))
    assert get_chain(traj.topology, "A") is not None
    sites = build_sites(traj, "A", [35, 36, 37], "CB", "CA")
    assert [s.resseq for s in sites] == [35, 36, 37]
    assert all(s.atom_name in ("CB", "CA") and s.chain_id == "A" for s in sites)
    assert traj.topology.atom(sites[0].atom_index).name == sites[0].atom_name
