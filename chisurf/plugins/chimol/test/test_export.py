"""Writing structures back out.

Without ``save`` chimol is a one-way street: it can show a structure but not hand
one back, so any transform, any deleted water, any renumbering is trapped in the
viewer. That made this the largest hole in replacing PyMOL, ahead of any
representation.

The writers serialise **what the viewer holds**, not the source file, which is the
whole point — re-exporting the input would discard exactly the work worth keeping.
"""

from __future__ import annotations

import numpy as np
import pytest
from chimol.io.export import (
    format_for_path,
    unscale_coordinates,
    write_mmcif,
    write_pdb,
    write_structure,
)


def _atoms(n: int = 3) -> np.ndarray:
    dtype = [
        ("atom_name", "U4"),
        ("res_name", "U4"),
        ("chain", "U2"),
        ("res_id", np.int64),
        ("element", "U2"),
    ]
    rows = [
        ("N", "ALA", "A", 1, "N"),
        ("CA", "ALA", "A", 1, "C"),
        ("O", "HOH", "B", 2, "O"),
    ][:n]
    return np.array(rows, dtype=dtype)


def _atom_records(path) -> list[str]:
    """Return the ``ATOM``/``HETATM`` lines of a written file."""
    return [line for line in path.read_text().splitlines() if line.startswith(("ATOM", "HETATM"))]


def _written_coords(path) -> np.ndarray:
    """Coordinates parsed back out of a written PDB, from its fixed columns."""
    return np.array(
        [[float(rec[30:38]), float(rec[38:46]), float(rec[46:54])] for rec in _atom_records(path)]
    )


_XYZ = np.array([[1.234, 2.345, 3.456], [4.5, 5.5, 6.5], [7.0, 8.0, 9.0]])


# --------------------------------------------------------------------------- #
# Format choice
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, expected",
    [
        ("x.pdb", "pdb"),
        ("x.ent", "pdb"),
        ("x.pqr", "pdb"),
        ("x.cif", "mmcif"),
        ("x.mmcif", "mmcif"),
        ("X.PDB", "pdb"),
        ("x.CIF", "mmcif"),
    ],
)
def test_the_extension_picks_the_format(name, expected):
    assert format_for_path(name) == expected


def test_an_unknown_extension_writes_pdb():
    """PyMOL's rule: a mistyped extension should still leave a usable file."""
    assert format_for_path("x.wat") == "pdb"
    assert format_for_path("noextension") == "pdb"


# --------------------------------------------------------------------------- #
# Scene units must not reach the file
# --------------------------------------------------------------------------- #
def test_coordinates_are_returned_to_angstrom():
    """Writing scene units would make the file load at the wrong size."""
    scene = (_XYZ - np.array([1.0, 2.0, 3.0])) * 10.0
    back = unscale_coordinates(scene, 10.0, np.array([1.0, 2.0, 3.0]))
    assert np.allclose(back, _XYZ)


def test_an_identity_transform_is_a_no_op():
    assert np.allclose(unscale_coordinates(_XYZ, 1.0, None), _XYZ)


def test_a_degenerate_scale_does_not_divide_by_zero():
    assert np.isfinite(unscale_coordinates(_XYZ, 0.0, None)).all()


# --------------------------------------------------------------------------- #
# PDB
# --------------------------------------------------------------------------- #
def test_pdb_round_trips_coordinates_exactly(tmp_path):
    path = tmp_path / "x.pdb"
    assert write_pdb(path, _atoms(), _XYZ) == 3
    back = _written_coords(path)
    assert np.allclose(back, _XYZ, atol=5e-4)  # PDB carries three decimals


def test_solvent_is_written_as_hetatm(tmp_path):
    path = tmp_path / "x.pdb"
    write_pdb(path, _atoms(), _XYZ)
    lines = _atom_records(path)
    assert lines[0].startswith("ATOM")  # ALA
    assert lines[2].startswith("HETATM")  # HOH


def test_columns_are_where_a_reader_expects_them(tmp_path):
    path = tmp_path / "x.pdb"
    write_pdb(path, _atoms(), _XYZ)
    record = next(r for r in _atom_records(path) if r.startswith("ATOM"))
    assert record[12:16].strip() == "N"
    assert record[17:20].strip() == "ALA"
    assert record[21:22] == "A"
    assert int(record[22:26]) == 1
    assert record[76:78].strip() == "N"


def test_a_four_character_atom_name_starts_in_column_13(tmp_path):
    """A long atom name starts one column earlier.

    PDB puts short names in column 14 and four-character ones in 13; misplacing
    this is the classic way to produce a file other tools misread.
    """
    atoms = _atoms(1)
    atoms["atom_name"][0] = "HD11"
    path = tmp_path / "x.pdb"
    write_pdb(path, atoms, _XYZ[:1])
    record = next(r for r in _atom_records(path) if r.startswith("ATOM"))
    assert record[12:16] == "HD11"


def test_a_selection_writes_only_its_atoms(tmp_path):
    path = tmp_path / "x.pdb"
    mask = np.array([True, False, True])
    assert write_pdb(path, _atoms(), _XYZ, mask=mask) == 2


def test_serials_are_renumbered_from_one(tmp_path):
    """A subset must not carry gaps in its serials."""
    path = tmp_path / "x.pdb"
    write_pdb(path, _atoms(), _XYZ, mask=np.array([False, True, True]))
    serials = [int(r[6:11]) for r in _atom_records(path)]
    assert serials == [1, 2]


def test_the_file_ends_with_END(tmp_path):
    path = tmp_path / "x.pdb"
    write_pdb(path, _atoms(), _XYZ)
    assert path.read_text().rstrip().endswith("END")


def test_a_title_is_written(tmp_path):
    path = tmp_path / "x.pdb"
    write_pdb(path, _atoms(), _XYZ, title="a lysozyme")
    assert "TITLE" in path.read_text()


def test_mismatched_coordinates_are_refused(tmp_path):
    with pytest.raises(ValueError):
        write_pdb(tmp_path / "x.pdb", _atoms(3), _XYZ[:2])


def test_a_mismatched_mask_is_refused(tmp_path):
    with pytest.raises(ValueError):
        write_pdb(tmp_path / "x.pdb", _atoms(3), _XYZ, mask=np.ones(2, bool))


def test_missing_fields_fall_back_rather_than_failing(tmp_path):
    """A raw-coordinate object has no residue names; it must still export."""
    bare = np.array([(1.0,)] * 3, dtype=[("unused", float)])
    path = tmp_path / "x.pdb"
    assert write_pdb(path, bare, _XYZ) == 3


# --------------------------------------------------------------------------- #
# mmCIF
# --------------------------------------------------------------------------- #
def test_mmcif_has_an_atom_site_loop(tmp_path):
    path = tmp_path / "x.cif"
    assert write_mmcif(path, _atoms(), _XYZ) == 3
    text = path.read_text()
    assert text.startswith("data_")
    assert "loop_" in text
    assert "_atom_site.Cartn_x" in text


def test_mmcif_carries_large_residue_numbers(tmp_path):
    """The reason to have it: PDB has only four columns for the number."""
    atoms = _atoms(1)
    atoms["res_id"][0] = 123456
    path = tmp_path / "x.cif"
    write_mmcif(path, atoms, _XYZ[:1])
    assert "123456" in path.read_text()


def test_pdb_wraps_a_large_residue_number(tmp_path):
    """Which is exactly the case mmCIF exists to handle."""
    atoms = _atoms(1)
    atoms["res_id"][0] = 123456
    path = tmp_path / "x.pdb"
    write_pdb(path, atoms, _XYZ[:1])
    record = next(r for r in _atom_records(path) if r.startswith("ATOM"))
    assert int(record[22:26]) == 123456 % 10000


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def test_write_structure_dispatches_on_extension(tmp_path):
    fmt, n = write_structure(tmp_path / "a.cif", _atoms(), _XYZ)
    assert (fmt, n) == ("mmcif", 3)
    fmt, n = write_structure(tmp_path / "a.pdb", _atoms(), _XYZ)
    assert (fmt, n) == ("pdb", 3)


# --------------------------------------------------------------------------- #
# The command, end to end
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def loaded(qapp):
    import pathlib

    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer
    from chimol.io.structure import _read_full_model

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test"
        / "data"
        / "atomic_coordinates"
        / "pdb_files"
        / "148l.pdb"
    )
    view = Viewer()
    view.add_structure(
        _read_full_model(cs_struct.Structure, pdb),
        name="148l",
        source_path=str(pdb),
    )

    class _Window:
        viewer = view

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages, errors = [], []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def test_save_writes_every_atom(loaded, tmp_path):
    cmd, view, messages, errors = loaded
    out = tmp_path / "all.pdb"
    cmd.do(f"save {out}")
    assert errors == []
    assert out.exists()
    written = len(_atom_records(out))
    assert written == len(view._atoms)
    assert "PDB" in messages[-1]


def test_saved_coordinates_are_angstrom_not_scene_units(loaded, tmp_path):
    """The viewer scales coordinates for rendering; a file must not carry that."""
    cmd, view, _, _ = loaded
    out = tmp_path / "a.pdb"
    cmd.do(f"save {out}")
    back = _written_coords(out)
    assert np.allclose(back, np.asarray(view._atoms["xyz"], dtype=float), atol=5e-4)


def test_save_honours_a_selection(loaded, tmp_path):
    cmd, _, messages, errors = loaded
    out = tmp_path / "part.pdb"
    cmd.do(f"save {out}, resi 10-20")
    assert errors == []
    written = len(_atom_records(out))
    assert 0 < written < 200


def test_save_writes_what_the_viewer_holds_not_the_source_file(loaded, tmp_path):
    """A transform applied in the viewer has to reach the file.

    Otherwise `save` is a file copy and every bit of work in the session is lost.
    """
    cmd, view, _, errors = loaded
    before = np.asarray(view._atoms["xyz"], dtype=float).copy()

    cmd.do("translate [100, 0, 0]")
    out = tmp_path / "moved.pdb"
    cmd.do(f"save {out}")
    assert errors == []

    back = _written_coords(out)
    # The file carries the transform, measured against where the atoms *were*.
    assert back[:, 0].mean() == pytest.approx(before[:, 0].mean() + 100.0, abs=1e-3)
    # ...and it agrees with the atom array, which a transform now also moves.
    # This used to be the opposite assertion: `_apply_rigid_transform` skipped
    # structured arrays, so `save` (reading the renderer's copy) and the atom
    # array disagreed by exactly the translation.
    assert np.allclose(back, np.asarray(view._atoms["xyz"], dtype=float), atol=5e-4)


def test_an_empty_selection_is_reported(loaded, tmp_path):
    cmd, _, _, errors = loaded
    cmd.do(f"save {tmp_path / 'none.pdb'}, resi 99999")
    assert errors and "matched no atoms" in errors[-1]


def test_save_without_a_filename_is_reported(loaded):
    cmd, _, _, errors = loaded
    cmd.do("save")
    assert errors and "Usage" in errors[-1]


def test_save_png_goes_to_the_image_path(loaded, tmp_path):
    """`.png` is an image, not a structure -- PyMOL dispatches the same way."""
    cmd, _, messages, errors = loaded
    cmd.do(f"save {tmp_path / 'shot.png'}")
    # Either it writes or it reports why; what matters is that it did not try to
    # write atom records into a PNG.
    assert not any("atoms as" in m for m in messages)
