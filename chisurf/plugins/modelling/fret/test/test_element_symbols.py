"""Headless tests for element assignment in ``core/av._element_symbol_from_pdb_line``.

Every AV is grown against an obstacle surface built from per-atom van-der-Waals
radii, and those radii come from an element symbol. A PDB without the (optional)
element columns 77-78 has to have it read off the atom-name field, where the
element is right-justified in columns 13-14 — ``" CA "`` is an α-carbon,
``"CA  "`` is calcium. Taking the first two letters instead gave every backbone
Cα calcium's 1.97 Å and every ``HE``/``HE21`` hydrogen helium's 1.40 Å, which
inflates the obstacle surface of exactly the atoms lining the backbone (RF-477).

Pure text parsing plus the shipped FPS screening structure — no AV backend.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from ..core.av import VDW_RADII, _element_symbol_from_pdb_line, load_structure_with_vdw

_SCREENING_PDB = (
    pathlib.Path(__file__).resolve().parents[5]
    / "examples"
    / "4w_junction"
    / "fps_test_data"
    / "test_screening"
    / "hivrt_straight_allTraj04791.pdb"
)


def _record(atom_name: str, element: str = "") -> str:
    """Return an ATOM record carrying ``atom_name`` in columns 13-16.

    Parameters
    ----------
    atom_name : str
        Exactly as it sits in the file, leading blanks included.
    element : str, optional
        Element for columns 77-78; empty writes a 66-character record.

    Returns
    -------
    str
        A single PDB ATOM line.
    """
    line = f"ATOM      1 {atom_name:<4} ALA E  18      12.000  13.000  14.000  1.00  0.00"
    return line if not element else f"{line}          {element:>2}"


@pytest.mark.parametrize(
    "atom_name, expected",
    [
        (" CA ", "C"),  # α-carbon — the case that used to read as calcium
        ("CA  ", "CA"),  # calcium ion — column 13 occupied
        (" C  ", "C"),
        (" N  ", "N"),
        (" O  ", "O"),
        (" CB ", "C"),
        (" CG1", "C"),
        (" HE ", "H"),  # ARG HE — used to read as helium
        (" HE2", "H"),
        ("HE21", "H"),  # four-character hydrogen name starting in column 13
        ("1HB ", "H"),  # numeric column 13
        ("2HG2", "H"),
        (" HG ", "H"),
        ("FE  ", "FE"),  # heme iron, spelled per the column rule
        ("MG  ", "MG"),
        ("", ""),  # nothing to parse
    ],
)
def test_element_from_atom_name_column_rule(atom_name, expected):
    """Without columns 77-78 the element is right-justified in columns 13-14."""
    assert _element_symbol_from_pdb_line(_record(atom_name)) == expected


def test_explicit_element_column_wins():
    """A file that states its elements is believed, column rule or not."""
    assert _element_symbol_from_pdb_line(_record(" CA ", element="CA")) == "CA"
    assert _element_symbol_from_pdb_line(_record("CA  ", element="C")) == "C"


@pytest.mark.parametrize("atom_name, expected", [(" ZN ", "ZN"), (" MG ", "MG")])
def test_left_padded_two_letter_element_still_resolves(atom_name, expected):
    """A non-conforming ``" ZN "`` is taken as zinc — ``"Z"`` is not an element."""
    assert _element_symbol_from_pdb_line(_record(atom_name)) == expected


def test_truncated_record_does_not_raise():
    """A line that stops inside the atom-name field is parsed, not an error."""
    assert _element_symbol_from_pdb_line("ATOM      1  CA") == "C"


def test_screening_structure_has_no_calcium_or_helium():
    """The shipped FPS screening input is all C/N/O/S/H — no metals, no noble gas."""
    if not _SCREENING_PDB.is_file():
        pytest.skip(f"missing test structure {_SCREENING_PDB}")
    radii = load_structure_with_vdw(str(_SCREENING_PDB))[:, 3]
    assert not np.any(np.isclose(radii, VDW_RADII[20]))  # calcium, 1.97 A
    assert not np.any(np.isclose(radii, VDW_RADII[2]))  # helium, 1.40 A
    # One Ca per residue used to be mis-radiused; they are carbon (1.70 A) now.
    assert np.count_nonzero(np.isclose(radii, VDW_RADII[6])) == 5691
    assert np.count_nonzero(np.isclose(radii, VDW_RADII[1])) == 8710
