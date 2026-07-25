"""Regression tests for the PDB fallback used when the Structure reader fails.

The fallback used to return a bare coordinate array. Without residue and chain
ids the viewer cannot find segment boundaries, so it splined a single polyline
through every atom in file order -- waters included -- which rendered as a
tangle of long streaks across the molecule.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.io.structure import (
    PdbBackbone,
    _parse_pdb_backbone,
    load_structure_payload,
)

TOPDIR = pathlib.Path(__file__).resolve().parents[4]
PDB = TOPDIR / "test" / "data" / "atomic_coordinates" / "pdb_files" / "hGBP1_closed.pdb"


def _segment_count(res_ids: np.ndarray, chain_ids: np.ndarray) -> int:
    """Count trace segments the way ``MolView._update_trace`` does."""
    n = len(res_ids)
    segments = 0
    start = 0
    for i in range(n - 1):
        gap = str(chain_ids[i]).strip() != str(chain_ids[i + 1]).strip()
        if not gap:
            gap = int(res_ids[i + 1]) - int(res_ids[i]) != 1
        if gap:
            if i + 1 - start >= 2:
                segments += 1
            start = i + 1
    if n - start >= 2:
        segments += 1
    return segments


@pytest.mark.skipif(not PDB.is_file(), reason=f"missing fixture {PDB}")
def test_fallback_recovers_backbone_metadata() -> None:
    backbone = _parse_pdb_backbone(str(PDB))

    assert isinstance(backbone, PdbBackbone)
    assert backbone.trace_coords is not None
    # One CA per residue, and the metadata arrays must line up with it.
    n_res = backbone.trace_coords.shape[0]
    assert n_res > 100
    assert len(backbone.res_ids) == n_res
    assert len(backbone.res_names) == n_res
    assert len(backbone.chain_ids) == n_res
    # The CA trace is a subset of the full coordinate set.
    assert backbone.coords.shape[0] > n_res


def test_trace_breaks_at_residue_gaps_and_chain_changes(tmp_path: pathlib.Path) -> None:
    """The whole point of carrying residue ids: the trace must not be one span.

    Three residues of chain A, a numbering gap, then two more, then chain B --
    which must yield three segments rather than one polyline stitching them
    together across the molecule.
    """
    lines = []
    serial = 1
    for chain, res_id, x in [
        ("A", 1, 0.0), ("A", 2, 3.8), ("A", 3, 7.6),
        ("A", 40, 60.0), ("A", 41, 63.8),
        ("B", 1, 90.0), ("B", 2, 93.8),
    ]:
        lines.append(
            f"ATOM  {serial:5d}  CA  ALA {chain}{res_id:4d}    "
            f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           C\n"
        )
        serial += 1
    pdb = tmp_path / "gapped.pdb"
    pdb.write_text("".join(lines))

    backbone = _parse_pdb_backbone(str(pdb))

    assert _segment_count(backbone.res_ids, backbone.chain_ids) == 3


@pytest.mark.skipif(not PDB.is_file(), reason=f"missing fixture {PDB}")
def test_continuous_chain_is_not_split_spuriously() -> None:
    """The complement: a gapless chain must stay a single segment."""
    backbone = _parse_pdb_backbone(str(PDB))

    steps = np.linalg.norm(np.diff(backbone.trace_coords, axis=0), axis=1)
    assert steps.max() < 5.0, "fixture is expected to be a gapless chain"
    assert _segment_count(backbone.res_ids, backbone.chain_ids) == 1


@pytest.mark.skipif(not PDB.is_file(), reason=f"missing fixture {PDB}")
def test_payload_falls_back_to_backbone_without_a_factory() -> None:
    structure, backbone = load_structure_payload(PDB, structure_factory=None)

    assert structure is None
    assert isinstance(backbone, PdbBackbone)
    assert backbone.res_ids is not None


@pytest.mark.skipif(not PDB.is_file(), reason=f"missing fixture {PDB}")
def test_payload_falls_back_when_the_factory_raises() -> None:
    def _boom(_path: str):
        raise RuntimeError("reader unavailable")

    structure, backbone = load_structure_payload(PDB, structure_factory=_boom)

    assert structure is None
    assert backbone.trace_coords is not None


def test_ca_trace_excludes_hetatm_and_extra_models(tmp_path: pathlib.Path) -> None:
    """Waters must not land on the backbone, and the trace must not span models."""
    pdb = tmp_path / "two_models.pdb"
    pdb.write_text(
        "MODEL        1\n"
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      2  CA  GLY A   2       3.800   0.000   0.000  1.00  0.00           C\n"
        "HETATM    3  O   HOH A 501      50.000  50.000  50.000  1.00  0.00           O\n"
        "ENDMDL\n"
        "MODEL        2\n"
        "ATOM      4  CA  ALA A   1      99.000  99.000  99.000  1.00  0.00           C\n"
        "ENDMDL\n"
    )

    backbone = _parse_pdb_backbone(str(pdb))

    # Only the two CAs of the first model.
    assert backbone.trace_coords.shape[0] == 2
    assert list(backbone.res_names) == ["ALA", "GLY"]
    assert np.all(backbone.trace_coords < 50.0)
    # The water is still shown as an atom, just not as backbone.
    assert backbone.coords.shape[0] == 3


def test_no_backbone_yields_coordinates_only(tmp_path: pathlib.Path) -> None:
    pdb = tmp_path / "ligand_only.pdb"
    pdb.write_text(
        "HETATM    1  O   HOH A 501       0.000   0.000   0.000  1.00  0.00           O\n"
        "HETATM    2  O   HOH A 502       1.000   0.000   0.000  1.00  0.00           O\n"
    )

    backbone = _parse_pdb_backbone(str(pdb))

    assert backbone.coords.shape == (2, 3)
    assert backbone.trace_coords is None
    assert backbone.res_ids is None


def test_empty_file_raises(tmp_path: pathlib.Path) -> None:
    pdb = tmp_path / "empty.pdb"
    pdb.write_text("REMARK nothing here\n")

    with pytest.raises(ValueError):
        _parse_pdb_backbone(str(pdb))


# --------------------------------------------------------------------------- #
# The fallback must draw a cartoon, not a bare spring
# --------------------------------------------------------------------------- #
# When the core reader is unavailable the built-in parser is all there is. It
# used to hand over CA positions only, which left the viewer with no secondary
# structure and no ribbon orientation -- so a protein came out as a thin spring
# threading through the alpha carbons. Losing the reader should cost metadata,
# not the picture.

_FALLBACK_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="module")
def parsed():
    return _parse_pdb_backbone(str(_FALLBACK_PDB))


def test_the_parser_returns_a_structured_atom_array(parsed):
    assert parsed.atoms is not None
    fields = set(parsed.atoms.dtype.names)
    # Secondary structure needs N/CA/C/O by name; the ribbon needs the carbonyl.
    assert {"atom_name", "xyz", "res_id", "chain"} <= fields


def test_the_atom_array_is_index_aligned_with_the_coordinates(parsed):
    """Per-atom masks and colours are mapped between the two by position."""
    assert parsed.atoms.shape[0] == parsed.coords.shape[0]
    assert np.allclose(parsed.atoms["xyz"], parsed.coords)


def test_the_backbone_atoms_needed_for_a_cartoon_are_present(parsed):
    names = set(np.char.strip(parsed.atoms["atom_name"].astype(str)))
    assert {"N", "CA", "C", "O"} <= names


def test_hetero_records_survive_the_parser(parsed):
    """Waters and ligands are part of the deposited model."""
    res_names = set(np.char.strip(parsed.atoms["res_name"].astype(str)))
    assert {"NAG", "BME"} & res_names


def test_the_fallback_assigns_secondary_structure(qapp_for_fallback):
    """Without this the cartoon has nothing to shape and draws a loop tube."""
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    structure, backbone = load_structure_payload(
        _FALLBACK_PDB, structure_factory=None
    )
    assert structure is None

    view = MolView()
    view.add_coordinates(
        backbone.coords,
        name="148l",
        source_path=str(_FALLBACK_PDB),
        trace_coords=backbone.trace_coords,
        res_ids=backbone.res_ids,
        res_names=backbone.res_names,
        chain_ids=backbone.chain_ids,
        atoms=backbone.atoms,
    )

    ss = view._secondary_structure
    assert ss is not None
    codes = set(np.unique(ss))
    assert "H" in codes and "E" in codes, f"only got {codes}"
    # And the ribbon needs an up-vector per residue, or it twists arbitrarily.
    assert view._trace_ups is not None
    assert view._trace_ups.shape[0] == view._coords.shape[0]


@pytest.fixture(scope="session")
def qapp_for_fallback():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
