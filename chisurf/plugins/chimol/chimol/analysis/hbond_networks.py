"""Hydrogen-bond **networks**: the connected components of the contact graph.

A single hydrogen bond is a line between two atoms, and PyMOL draws it as one.
What a structural argument usually rests on is the *network* -- the catalytic
triad, the buried water wire, the ladder that holds a helix against a sheet --
and neither PyMOL nor ChimeraX names one: PyMOL's `distance ... mode=2` returns
an undifferentiated bundle of dashes, and ChimeraX's `hbonds` returns a list.
Grouping them is the part a person otherwise does by eye, and by eye is exactly
where a water-mediated path of four bonds is missed.

So the bonds come from the PyMOL-transcribed finder in
:mod:`~chimol.analysis.hbonds` -- the criteria are not re-invented here -- and
this module is only the graph on top of them:

* two bonds are in the same network when they share an **atom**; the components
  of that graph are the networks;
* a network is described by what it *spans*: how many residues, how many of
  them are water, whether it crosses chains or objects. That is what makes one
  worth looking at;
* an isolated bond is a network of one, and is kept as such rather than
  discarded -- "this contact is on its own" is a finding too.

Two options change what the components come out as, and both exist because the
default answer is misleading on a real structure:

* ``waters`` -- **bridge** (the default) keeps waters in the graph, so a
  donor-water-acceptor path is one network, which is the whole point of looking
  at ordered water; **exclude** drops water-to-anything bonds, which is what
  you want when asking about the protein alone; **only** keeps water-to-water,
  the wire itself.
* ``min_size`` -- networks with fewer than this many bonds are dropped. Every
  structure has dozens of lone surface contacts and they bury the two networks
  that matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .hbonds import HBond, HBondCriteria, find_hydrogen_bonds, type_atoms

__all__ = [
    "HBondNetwork",
    "NetworkOptions",
    "find_hbond_networks",
    "network_colors",
]

#: The residue names a structure calls water. `solvent` in the selection
#: grammar uses the same list.
WATER_RESIDUES = frozenset({"HOH", "WAT", "H2O", "DOD", "TIP", "TIP3", "SOL"})


@dataclass(frozen=True)
class NetworkOptions:
    """How the bonds are grouped.

    Attributes
    ----------
    waters : {"bridge", "exclude", "only"}
        What role water plays -- see the module docstring.
    min_size : int
        Drop networks with fewer bonds than this.
    """

    waters: str = "bridge"
    min_size: int = 1


@dataclass
class HBondNetwork:
    """One connected component of the hydrogen-bond graph.

    Attributes
    ----------
    bonds : list of HBond
        Its bonds, in the order the finder produced them.
    atoms : list of int
        Every atom involved, sorted.
    residues : list of tuple
        ``(chain, resi, resn)`` for each residue it touches, sorted.
    waters : int
        How many of those residues are water.
    chains : list of str
        The chains it spans. More than one is what makes a network interesting
        at an interface.
    """

    bonds: list[HBond]
    atoms: list[int] = field(default_factory=list)
    residues: list[tuple] = field(default_factory=list)
    waters: int = 0
    chains: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        """How many hydrogen bonds it holds."""
        return len(self.bonds)

    @property
    def spans_chains(self) -> bool:
        """Whether it reaches across more than one chain."""
        return len(self.chains) > 1

    def describe(self) -> str:
        """One line: what this network is, for a console or a panel."""
        residues = len(self.residues)
        parts = [f"{self.size} bonds", f"{residues} residues"]
        if self.waters:
            parts.append(f"{self.waters} water")
        if self.spans_chains:
            parts.append("chains " + "+".join(self.chains))
        return ", ".join(parts)


def _is_water(resn: str) -> bool:
    return str(resn).strip().upper() in WATER_RESIDUES


def _residue_of(atoms: np.ndarray, index: int) -> tuple:
    names = atoms.dtype.names or ()
    chain = str(atoms["chain"][index]) if "chain" in names else ""
    resi = atoms["res_id"][index] if "res_id" in names else -1
    resn = str(atoms["res_name"][index]) if "res_name" in names else ""
    try:
        resi = int(resi)
    except (TypeError, ValueError):
        resi = -1
    return (chain, resi, resn)


def find_hbond_networks(
    atoms: np.ndarray,
    bond_pairs,
    mask_a: np.ndarray | None = None,
    mask_b: np.ndarray | None = None,
    *,
    criteria: HBondCriteria | None = None,
    cutoff: float | None = None,
    options: NetworkOptions | None = None,
    bonds: list[HBond] | None = None,
) -> list[HBondNetwork]:
    """Group polar contacts into networks, largest first.

    Parameters
    ----------
    atoms : numpy.ndarray
        The structured atom table.
    bond_pairs : array_like or None
        Covalent bonds, for the finder's neighbour exclusion.
    mask_a, mask_b : numpy.ndarray, optional
        The two sides, as :func:`~chimol.analysis.hbonds.find_hydrogen_bonds`
        takes them.
    criteria : HBondCriteria, optional
        Defaults to the live ``h_bond_*`` settings.
    cutoff : float, optional
        Widest distance searched.
    options : NetworkOptions, optional
        How to group. Defaults to bridging waters and keeping every network.
    bonds : list of HBond, optional
        Bonds already found, to group without searching again.

    Returns
    -------
    list of HBondNetwork
        Sorted by size, largest first; ties broken by the lowest atom index so
        the order is stable between runs.
    """
    options = options or NetworkOptions()
    if bonds is None:
        typing = type_atoms(atoms, bond_pairs)
        bonds = find_hydrogen_bonds(
            atoms, bond_pairs, mask_a, mask_b,
            criteria=criteria, cutoff=cutoff, typing=typing,
        )
    if not bonds:
        return []

    water_atom = np.array(
        [_is_water(resn) for resn in _residue_names(atoms)], dtype=bool
    )
    kept = [
        bond for bond in bonds
        if _keep_bond(bond, water_atom, options.waters)
    ]
    if not kept:
        return []

    parent: dict[int, int] = {}

    def find(atom: int) -> int:
        root = atom
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(atom, atom) != root:      # path compression
            parent[atom], atom = root, parent[atom]
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[a] = b

    for bond in kept:
        parent.setdefault(bond.donor, bond.donor)
        parent.setdefault(bond.acceptor, bond.acceptor)
        union(bond.donor, bond.acceptor)

    grouped: dict[int, list[HBond]] = {}
    for bond in kept:
        grouped.setdefault(find(bond.donor), []).append(bond)

    networks = [
        _describe(atoms, group, water_atom)
        for group in grouped.values()
        if len(group) >= max(int(options.min_size), 1)
    ]
    networks.sort(key=lambda net: (-net.size, net.atoms[0] if net.atoms else 0))
    return networks


def _residue_names(atoms: np.ndarray) -> np.ndarray:
    names = atoms.dtype.names or ()
    if "res_name" in names:
        return np.asarray(atoms["res_name"])
    return np.array([""] * len(atoms))


def _keep_bond(bond: HBond, water_atom: np.ndarray, waters: str) -> bool:
    """Apply the water policy to one bond."""
    mode = str(waters).lower()
    involved = bool(water_atom[bond.donor]) + bool(water_atom[bond.acceptor])
    if mode == "exclude":
        return involved == 0
    if mode == "only":
        return involved == 2
    return True                                   # "bridge"


def _describe(
    atoms: np.ndarray, group: list[HBond], water_atom: np.ndarray
) -> HBondNetwork:
    """Fill in what a component spans."""
    indices: set[int] = set()
    for bond in group:
        indices.add(int(bond.donor))
        indices.add(int(bond.acceptor))
    residues = {_residue_of(atoms, index) for index in indices}
    return HBondNetwork(
        bonds=list(group),
        atoms=sorted(indices),
        residues=sorted(residues),
        waters=sum(1 for residue in residues if _is_water(residue[2])),
        chains=sorted({residue[0] for residue in residues if residue[0]}),
    )


#: The colours networks are drawn in, cycled. PyMOL's own qualitative set, in
#: the order its `spectrum` uses them, so a chimol figure and a PyMOL one made
#: from the same structure do not disagree about which colour means what.
NETWORK_PALETTE: tuple[str, ...] = (
    "yellow", "marine", "salmon", "palegreen", "violet", "lightorange",
    "palecyan", "wheat", "hotpink", "slate",
)


def network_colors(count: int) -> list[str]:
    """Return a colour name per network, cycling the palette.

    The largest network gets the first colour, so the same structure always
    colours the same way -- a figure that renumbers its networks between runs
    is a figure nobody can refer to.
    """
    return [NETWORK_PALETTE[index % len(NETWORK_PALETTE)] for index in range(count)]
