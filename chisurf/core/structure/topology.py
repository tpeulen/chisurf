"""Topology over ChiSurf's atom array: what the atoms *are*, not where.

A trajectory is coordinates plus a topology, and the coordinate half is
ChiSurf's own (:mod:`chisurf.core.fio.trajectory`). This is the other half —
atom names, elements, residues and chains — built directly on the structured
atom array that :class:`chisurf.core.structure.Structure` already produces from
a PDB or mmCIF, so nothing has to be re-parsed.

The surface deliberately matches the library this replaces (``n_atoms``,
``atoms``, ``residues``, ``chains``, ``select``, ``subset``, ``to_dataframe``),
because ~80 call sites across the trajectory plugins iterate it. Matching the
names is what lets those be ported one at a time instead of all at once.

Notes
-----
:class:`Atom` and :class:`Residue` are **views**, created on demand from rows of
the underlying array rather than stored as objects. A 5235-atom structure would
otherwise mean 5235 Python objects built at load time, most of which nobody
touches.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from .selection import select, selection_mask

__all__ = ["Atom", "Chain", "Element", "Residue", "Topology", "element"]


@dataclasses.dataclass(frozen=True)
class Chain:
    """A chain, identified by the label in the file and its position in it."""

    index: int
    chain_id: str

    def __repr__(self) -> str:
        """Return a short description of the chain."""
        return f"Chain({self.index}, {self.chain_id!r})"


@dataclasses.dataclass(frozen=True)
class Residue:
    """A residue view.

    Attributes
    ----------
    index : int
        Position among the residues, counted from zero.
    name : str
        Residue name, e.g. ``"ALA"``.
    resSeq : int
        Residue number **as written in the file**, which is not the index.
    chain : Chain
        The chain it belongs to.
    """

    index: int
    name: str
    resSeq: int
    chain: Chain

    def __repr__(self) -> str:
        """Return the residue name and number."""
        return f"Residue({self.name}{self.resSeq})"


@dataclasses.dataclass(frozen=True)
class Atom:
    """An atom view.

    Attributes
    ----------
    index : int
        Position in the topology, counted from zero.
    name : str
        Atom name, e.g. ``"CA"``.
    element : str
        Element symbol; ``""`` when the file did not say.
    serial : int
        Atom number as written in the file.
    residue : Residue
        The residue it belongs to.
    """

    index: int
    name: str
    element: str
    serial: int
    residue: Residue

    def __repr__(self) -> str:
        """Return the atom with its residue, as PyMOL-ish shorthand."""
        return f"Atom({self.residue.name}{self.residue.resSeq}-{self.name})"


@dataclasses.dataclass(frozen=True)
class Element:
    """A chemical element, as much of one as a topology needs.

    Exists so ``add_atom(name, element, residue)`` reads the same as it did
    with the library this replaces, and so ``.symbol`` / ``.atomic_number`` /
    ``.mass`` resolve. Comparing or formatting one gives the symbol, so code
    that treats an element as a string keeps working.
    """

    symbol: str
    atomic_number: int = 0
    mass: float = 0.0

    def __str__(self) -> str:
        """Return the element symbol."""
        return self.symbol

    def __eq__(self, other) -> bool:
        """Compare by symbol, so an element equals its own symbol."""
        if isinstance(other, Element):
            return self.symbol == other.symbol
        if isinstance(other, str):
            return self.symbol == other
        return NotImplemented

    def __hash__(self) -> int:
        """Hash by symbol, to match :meth:`__eq__`."""
        return hash(self.symbol)


class _ElementNamespace:
    """``element.carbon``, ``element.hydrogen`` and friends, by name or symbol."""

    _BY_NAME = {
        "hydrogen": ("H", 1, 1.008), "carbon": ("C", 6, 12.011),
        "nitrogen": ("N", 7, 14.007), "oxygen": ("O", 8, 15.999),
        "fluorine": ("F", 9, 18.998), "phosphorus": ("P", 15, 30.974),
        "sulfur": ("S", 16, 32.06), "chlorine": ("CL", 17, 35.45),
        "sodium": ("NA", 11, 22.990), "magnesium": ("MG", 12, 24.305),
        "potassium": ("K", 19, 39.098), "calcium": ("CA", 20, 40.078),
        "iron": ("FE", 26, 55.845), "zinc": ("ZN", 30, 65.38),
        "selenium": ("SE", 34, 78.971), "virtual": ("", 0, 0.0),
    }

    def __getattr__(self, name: str) -> Element:
        """Return the named element."""
        try:
            symbol, number, mass = self._BY_NAME[name.lower()]
        except KeyError:
            raise AttributeError(f"unknown element {name!r}") from None
        return Element(symbol, number, mass)

    def get_by_symbol(self, symbol: str) -> Element:
        """Return the element with this symbol."""
        wanted = str(symbol).upper()
        for _, (sym, number, mass) in self._BY_NAME.items():
            if sym == wanted:
                return Element(sym, number, mass)
        return Element(wanted)


#: ``element.carbon`` and friends, matching the spelling the tree already uses.
element = _ElementNamespace()


class Topology:
    """The atoms of a structure, and the residues and chains they form.

    Parameters
    ----------
    atoms : numpy.ndarray, optional
        ChiSurf's structured atom array (see
        :mod:`chisurf.core.fio.structure.coordinates`). Omit it to build a
        topology up with :meth:`add_chain`, :meth:`add_residue` and
        :meth:`add_atom`.
    """

    def __init__(self, atoms: np.ndarray = None):
        from chisurf.core.fio.structure.coordinates import atom_dtype

        self._atoms = (np.zeros(0, dtype=atom_dtype) if atoms is None
                       else np.asarray(atoms))
        self._residue_index = None
        self._chain_index = None
        # Only used while building; a topology read from a file never touches
        # these, and rebuilding the index arrays is what keeps the two paths
        # from disagreeing.
        self._next_chain = 0
        self._next_residue = 0

    def _invalidate(self) -> None:
        """Drop the cached residue and chain numbering."""
        self._residue_index = None
        self._chain_index = None

    # -- incremental construction -------------------------------------------
    def add_chain(self, chain_id: str = None) -> Chain:
        """Append a chain and return it.

        Parameters
        ----------
        chain_id : str, optional
            Identifier; defaults to ``A``, ``B``, ... by position.

        Returns
        -------
        Chain
        """
        index = self._next_chain
        self._next_chain += 1
        if chain_id is None:
            chain_id = chr(ord("A") + index % 26)
        return Chain(index, str(chain_id))

    def add_residue(self, name: str, chain: Chain, resSeq: int = None) -> Residue:
        """Append a residue to *chain* and return it.

        Parameters
        ----------
        name : str
            Residue name.
        chain : Chain
            The chain it belongs to.
        resSeq : int, optional
            Residue number; defaults to a one-based counter.

        Returns
        -------
        Residue
        """
        index = self._next_residue
        self._next_residue += 1
        return Residue(index, str(name), index + 1 if resSeq is None else int(resSeq), chain)

    def add_atom(self, name: str, element_: Element | str, residue: Residue) -> Atom:
        """Append an atom and return it.

        Parameters
        ----------
        name : str
            Atom name.
        element_ : Element or str
            Element, or its symbol.
        residue : Residue
            The residue it belongs to.

        Returns
        -------
        Atom
        """
        from chisurf.core.fio.structure.coordinates import atom_dtype

        symbol = getattr(element_, "symbol", None)
        if symbol is None:
            symbol = "" if element_ is None else str(element_)
        row = np.zeros(1, dtype=atom_dtype)
        index = len(self._atoms)
        row["i"] = index
        row["atom_id"] = index + 1
        row["atom_name"] = str(name)
        row["element"] = symbol
        row["res_id"] = residue.resSeq
        row["res_name"] = residue.name
        row["chain"] = residue.chain.chain_id
        row["mass"] = getattr(element_, "mass", 0.0) or 0.0
        self._atoms = np.concatenate([self._atoms, row])
        self._invalidate()
        return Atom(index, str(name), symbol, index + 1, residue)

    # -- construction --------------------------------------------------------
    @classmethod
    def from_file(cls, filename: str) -> Topology:
        """Read a topology from a PDB or mmCIF.

        Parameters
        ----------
        filename : str
            Structure file.

        Returns
        -------
        Topology
        """
        from chisurf.core.structure import Structure
        return cls(Structure(str(filename)).atoms)

    # -- geometry-free facts -------------------------------------------------
    @property
    def atom_array(self) -> np.ndarray:
        """The underlying structured array."""
        return self._atoms

    @property
    def n_atoms(self) -> int:
        """Number of atoms."""
        return int(len(self._atoms))

    @property
    def n_residues(self) -> int:
        """Number of residues."""
        return int(self._residues().max()) + 1 if self.n_atoms else 0

    @property
    def n_chains(self) -> int:
        """Number of chains."""
        return int(self._chains().max()) + 1 if self.n_atoms else 0

    def _residues(self) -> np.ndarray:
        """Return the per-atom residue index, computed once."""
        if self._residue_index is None:
            from .selection import _residue_index
            self._residue_index = _residue_index(self._atoms)
        return self._residue_index

    def _chains(self) -> np.ndarray:
        """Return the per-atom chain index, computed once."""
        if self._chain_index is None:
            from .selection import _chain_index
            self._chain_index = _chain_index(self._atoms)
        return self._chain_index

    # -- views ---------------------------------------------------------------
    def chain(self, index: int) -> Chain:
        """Return the chain at *index*."""
        rows = np.flatnonzero(self._chains() == index)
        if not rows.size:
            raise IndexError(f"no chain {index}")
        return Chain(int(index), str(self._atoms["chain"][rows[0]]))

    def residue(self, index: int) -> Residue:
        """Return the residue at *index*."""
        rows = np.flatnonzero(self._residues() == index)
        if not rows.size:
            raise IndexError(f"no residue {index}")
        row = rows[0]
        return Residue(int(index), str(self._atoms["res_name"][row]),
                       int(self._atoms["res_id"][row]),
                       self.chain(int(self._chains()[row])))

    def atom(self, index: int) -> Atom:
        """Return the atom at *index*."""
        row = self._atoms[index]
        return Atom(int(index), str(row["atom_name"]), str(row["element"]),
                    int(row["atom_id"]), self.residue(int(self._residues()[index])))

    @property
    def atoms(self):
        """Iterate the atoms."""
        return (self.atom(i) for i in range(self.n_atoms))

    @property
    def residues(self):
        """Iterate the residues."""
        return (self.residue(i) for i in range(self.n_residues))

    @property
    def chains(self):
        """Iterate the chains."""
        return (self.chain(i) for i in range(self.n_chains))

    # -- selection and subsetting -------------------------------------------
    def select(self, expression: str) -> np.ndarray:
        """Return the indices of the atoms *expression* selects.

        Parameters
        ----------
        expression : str
            Selection expression; see
            :mod:`chisurf.core.structure.selection`.

        Returns
        -------
        numpy.ndarray
            Integer indices, ascending.
        """
        return select(self._atoms, expression)

    def select_mask(self, expression: str) -> np.ndarray:
        """Return a boolean mask of the atoms *expression* selects."""
        return selection_mask(self._atoms, expression)

    def subset(self, indices) -> Topology:
        """Return a topology holding only *indices*, in that order.

        Parameters
        ----------
        indices : array_like of int
            Atom indices to keep.

        Returns
        -------
        Topology
        """
        return Topology(self._atoms[np.asarray(indices, dtype=np.intp)])

    def to_dataframe(self):
        """Return the atoms as a :class:`pandas.DataFrame`.

        Returns
        -------
        pandas.DataFrame
            One row per atom, with the residue and chain indices resolved.
        """
        import pandas as pd

        return pd.DataFrame({
            "serial": self._atoms["atom_id"],
            "name": self._atoms["atom_name"],
            "element": self._atoms["element"],
            "resSeq": self._atoms["res_id"],
            "resName": self._atoms["res_name"],
            "chainID": self._atoms["chain"],
            "resid": self._residues(),
            "chainid": self._chains(),
        })

    # -- dunders -------------------------------------------------------------
    def __len__(self) -> int:
        """Return the number of atoms."""
        return self.n_atoms

    def __eq__(self, other) -> bool:
        """Return whether two topologies describe the same atoms."""
        if not isinstance(other, Topology):
            return NotImplemented
        if self.n_atoms != other.n_atoms:
            return False
        # Compare what identifies an atom, not the coordinates: two frames of
        # the same molecule have the same topology and different positions.
        fields = ("chain", "res_id", "res_name", "atom_name", "element")
        return all(np.array_equal(self._atoms[f], other._atoms[f]) for f in fields)

    def __repr__(self) -> str:
        """Return the atom, residue and chain counts."""
        return (f"<Topology: {self.n_atoms} atoms, {self.n_residues} residues, "
                f"{self.n_chains} chains>")
