"""Elements read out of a PDB that has no element column.

Legacy and hand-written PDB files stop at column 66, so the element has to come
from the atom-name field. The built-in parser used to take the *first letter* of
the name, which turned iron into fluorine, chlorine into carbon, and magnesium
and zinc into ``M`` and ``Z`` -- symbols no element table contains. Consumers
take the field at face value (``select elem fe`` in
``cmd/sele_parser.py``, the metal/solvent classes in
``analysis/atom_classes.py``), so an ion simply stopped being selectable and was
coloured as something else.

The rule the guess was missing is the one the format states: the element is
right-justified in columns 13-14, so a blank or numeric column 13 means a
one-letter element -- ``" CA "`` is an alpha carbon, ``"CA  "`` is calcium.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.io.structure import (
    _element_symbol_from_pdb_line,
    _parse_pdb_backbone,
)


def _record(name_field: str, *, element: str = "", res_name: str = "UNK") -> str:
    """Build one 66- or 78-column ATOM record around a raw name field.

    Parameters
    ----------
    name_field : str
        The four characters of columns 13-16, given exactly as they sit in the
        file (leading blanks included).
    element : str, optional
        Columns 77-78. Empty -- the default -- truncates the record at column 66,
        the way a legacy file is written.
    res_name : str, optional
        Residue name for columns 18-20.

    Returns
    -------
    str
        A single ATOM record.
    """
    assert len(name_field) == 4, "columns 13-16 are four characters wide"
    line = (
        f"ATOM      1 {name_field}{res_name:>4} A   1    {0.0:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00"
    )
    return line if not element else f"{line}          {element:>2}\n"


@pytest.mark.parametrize(
    "name_field, expected",
    [
        # Column 13 blank -> one-letter element, whatever the next letter is.
        (" CA ", "C"),  # alpha carbon, not calcium
        (" N  ", "N"),
        (" O  ", "O"),
        (" CB ", "C"),
        (" CD1", "C"),
        (" NE2", "N"),
        (" OG1", "O"),
        (" SD ", "S"),
        (" C1'", "C"),
        (" OP1", "O"),
        # Column 13 occupied -> two-letter element.
        ("CA  ", "CA"),  # calcium ion
        ("FE  ", "FE"),  # iron, not fluorine
        ("MG  ", "MG"),
        ("ZN  ", "ZN"),
        ("CL  ", "CL"),  # chlorine, not carbon
        ("SE  ", "SE"),
        # Hydrogens: a digit in columns 15-16 rules a two-letter reading out.
        (" HE2", "H"),
        ("HE21", "H"),  # not helium
        ("HH11", "H"),
        ("1HB ", "H"),  # old-style leading-digit naming
        (" HG ", "H"),  # ... while HG in column 13 is mercury
        ("HG  ", "HG"),
    ],
)
def test_element_follows_the_column_rule(name_field: str, expected: str) -> None:
    assert _element_symbol_from_pdb_line(_record(name_field)) == expected


@pytest.mark.parametrize("name_field, expected", [(" ZN ", "ZN"), (" MG ", "MG")])
def test_left_padded_metal_falls_back_to_the_pair(name_field: str, expected: str) -> None:
    """``" ZN "`` breaks the column rule, but ``Z`` is not an element at all."""
    assert _element_symbol_from_pdb_line(_record(name_field)) == expected


def test_the_element_column_wins_when_it_is_present() -> None:
    """A modern record states the element; the name is not consulted."""
    assert _element_symbol_from_pdb_line(_record(" CA ", element="CA")) == "CA"
    assert _element_symbol_from_pdb_line(_record("CA  ", element="C")) == "C"


def test_a_truncated_record_does_not_raise() -> None:
    assert _element_symbol_from_pdb_line("ATOM      1  CA ") == "C"
    assert _element_symbol_from_pdb_line("ATOM") == ""


def test_a_legacy_file_keeps_its_ions_selectable(tmp_path: pathlib.Path) -> None:
    """The end-to-end symptom: ``elem fe`` matched nothing on such a file."""
    names = [" N  ", " CA ", " C  ", " O  ", "FE  ", "MG  ", "ZN  ", "CL  "]
    lines = []
    for serial, name_field in enumerate(names, start=1):
        res_name = "ALA" if serial <= 4 else name_field.strip()
        record = _record(name_field, res_name=res_name)
        lines.append(f"{record[:6]}{serial:5d}{record[11:]}\n")
    pdb = tmp_path / "legacy_no_element_column.pdb"
    pdb.write_text("".join(lines))

    atoms = _parse_pdb_backbone(str(pdb)).atoms

    elements = list(np.char.strip(atoms["element"].astype(str)))
    assert elements == ["N", "C", "C", "O", "FE", "MG", "ZN", "CL"]
