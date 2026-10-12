"""Water molecules are always stripped before any calculation.

IMP's default PDB selector drops waters, but QuEst does not rely on that
alone: :func:`quest.core.structure.reader._strip_waters` removes every atom
whose residue name identifies it as water (``HOH``, ``WAT``, ``TIP3``,
``SOL``, …) as a defensive guarantee. Crystallographic solvent is mobile on
the timescale a tethered dye explores, so it must never be a steric obstacle.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import numpy as np

from chisurf.plugins.quenching_estimator.core.structure.reader import (
    _WATER_RESIDUE_NAMES,
    _strip_waters,
)

# A minimal structure: two protein CA atoms and a water oxygen.
_PDB_WITH_WATER = dedent("""\
    ATOM      1  N   ALA A   1       1.000   1.000   1.000  1.00 20.00           N
    ATOM      2  CA  ALA A   1       2.000   1.000   1.000  1.00 20.00           C
    ATOM      3  N   GLY A   2       3.000   1.000   1.000  1.00 20.00           N
    ATOM      4  CA  GLY A   2       4.000   1.000   1.000  1.00 20.00           C
    HETATM    5  O   HOH A 101       5.000   5.000   5.000  1.00 50.00           O
    HETATM    6  O   HOH A 102       6.000   6.000   6.000  1.00 50.00           O
    TER       7      ALA A   2
    END
""")

_PDB_WITH_WAT = dedent("""\
    ATOM      1  N   ALA A   1       1.000   1.000   1.000  1.00 20.00           N
    ATOM      2  CA  ALA A   1       2.000   1.000   1.000  1.00 20.00           C
    HETATM    3  O   WAT A 201       7.000   7.000   7.000  1.00 50.00           O
    END
""")


def _atoms(res_name: str, count: int = 1) -> np.ndarray:
    """A minimal atom array with *count* atoms of residue type *res_name*."""
    dtype = np.dtype(
        {
            "names": [
                "i",
                "chain",
                "res_id",
                "insertion_code",
                "residue_index",
                "res_name",
                "atom_id",
                "atom_name",
                "element",
                "coord",
                "charge",
                "radius",
                "bfactor",
                "mass",
            ],
            "formats": [
                "i4",
                "|U1",
                "i4",
                "|U1",
                "i4",
                "|U5",
                "i4",
                "|U5",
                "|U1",
                "3f8",
                "f8",
                "f8",
                "f8",
                "f8",
            ],
        }
    )
    atoms = np.zeros(count, dtype=dtype)
    atoms["res_name"] = res_name
    atoms["atom_name"] = "O"
    return atoms


class TestStripWatersUnit:
    """The filter function in isolation."""

    def test_removes_hoh(self) -> None:
        atoms = _atoms("HOH", 3)
        result = _strip_waters(atoms)
        assert len(result) == 0

    def test_keeps_protein(self) -> None:
        atoms = _atoms("ALA", 5)
        result = _strip_waters(atoms)
        assert len(result) == 5

    def test_strips_mixed(self) -> None:
        dtype = _atoms("ALA").dtype
        atoms = np.zeros(4, dtype=dtype)
        atoms["res_name"] = ["ALA", "HOH", "WAT", "GLY"]
        result = _strip_waters(atoms)
        names = [str(r).strip() for r in result["res_name"]]
        assert names == ["ALA", "GLY"]

    def test_case_insensitive(self) -> None:
        dtype = _atoms("ALA").dtype
        atoms = np.zeros(3, dtype=dtype)
        atoms["res_name"] = ["hoh", "Wat", "ALA"]
        result = _strip_waters(atoms)
        assert len(result) == 1
        assert str(result["res_name"][0]).strip() == "ALA"

    def test_strips_all_known_water_names(self) -> None:
        for name in _WATER_RESIDUE_NAMES:
            atoms = _atoms(name, 1)
            result = _strip_waters(atoms)
            assert len(result) == 0, f"water residue '{name}' was not stripped"

    def test_empty_array_is_safe(self) -> None:
        atoms = _atoms("ALA", 0)
        result = _strip_waters(atoms)
        assert len(result) == 0

    def test_strips_whitespace_padded_names(self) -> None:
        dtype = _atoms("ALA").dtype
        atoms = np.zeros(2, dtype=dtype)
        atoms["res_name"] = [" HOH ", "ALA"]
        result = _strip_waters(atoms)
        assert len(result) == 1


class TestStripWatersInReader:
    """Water stripping through the full reader pipeline (requires IMP)."""

    def test_hoh_water_absent_after_read(self, tmp_path: Path) -> None:
        pdb = tmp_path / "with_water.pdb"
        pdb.write_text(_PDB_WITH_WATER)
        from chisurf.plugins.quenching_estimator.core.structure import read

        atoms = read(str(pdb), verbose=False)
        names = {str(r).strip().upper() for r in atoms["res_name"]}
        assert "HOH" not in names
        assert "ALA" in names
        assert "GLY" in names

    def test_wat_water_absent_after_read(self, tmp_path: Path) -> None:
        pdb = tmp_path / "with_wat.pdb"
        pdb.write_text(_PDB_WITH_WAT)
        from chisurf.plugins.quenching_estimator.core.structure import read

        atoms = read(str(pdb), verbose=False)
        names = {str(r).strip().upper() for r in atoms["res_name"]}
        assert "WAT" not in names
        assert "ALA" in names

    def test_148l_has_no_water(self) -> None:
        """The bundled 148L structure contains ~140 HOH records; none survive."""
        from chisurf.plugins.quenching_estimator.core.structure import Structure

        s = Structure(str(Path(__file__).parent / "148l.pdb"), make_coarse=False)
        names = {str(r).strip().upper() for r in s.atoms["res_name"]}
        for water in _WATER_RESIDUE_NAMES:
            assert water not in names, f"water '{water}' found in 148L atoms"
