"""The native structure settings bind to the existing single-file reader."""

from pathlib import Path

import numpy as np
from emtk.testing import Driver

from chisurf.core.experiments.modelling.reader import StructureReader
from chisurf.emtk.reader_settings import ReaderSettingsApp

PDB = Path(__file__).parent / "data/atomic_coordinates/pdb_files/148l.pdb"


def test_structure_source_is_one_pdb_and_preserves_scientific_read():
    """Choosing a source feeds one original Structure with unchanged coordinates."""
    reader = StructureReader(record_provenance=False)
    app = ReaderSettingsApp(reader)
    try:
        source = app.sources["filename"]
        assert source.options["mode"] == "open"
        assert ".pdb" in source.options["extensions"]
        source.path = str(PDB)
        chosen = reader.read()
        explicit = StructureReader(record_provenance=False).read(filename=str(PDB))
        assert len(chosen) == 1 and chosen.data_reader is reader
        assert reader.filename == str(PDB)
        assert reader.n_atoms == 1300 and reader.n_residues == 164
        np.testing.assert_array_equal(chosen[0].atoms, explicit[0].atoms)
        assert chosen[0].filename == explicit[0].filename
    finally:
        app.close()


def test_structure_toggle_and_source_are_reachable_in_native_form():
    """The actual toggle changes its reader and drops preserve single-file semantics."""
    reader = StructureReader(record_provenance=False)
    app = ReaderSettingsApp(reader)
    try:
        driver = Driver(app, size=(760, 380))
        driver.draw()
        assert driver.rect("filename") is not None
        assert driver.rect("filename.browse") is not None
        driver.click("compute_internal_coordinates")
        assert reader.compute_internal_coordinates is True
        driver.click("compute_internal_coordinates")
        assert reader.compute_internal_coordinates is False
        assert app.on_files_dropped([str(PDB)])
        assert reader.filename == str(PDB)
        assert not app.on_files_dropped([str(PDB.parent)])
        assert not any(section["type"] == "progress" for section in app.spec["sections"])
    finally:
        app.close()


def test_explicit_structure_filename_still_wins_over_selected_input():
    """Native selection does not change the established explicit read(filename) API."""
    reader = StructureReader(record_provenance=False)
    reader.filename = "unused-selection.pdb"
    group = reader.read(filename=str(PDB))
    assert len(group) == 1
    assert Path(group[0].filename).resolve() == PDB.resolve()


def test_source_change_clears_previous_counts_and_toggle_reaches_structure(monkeypatch):
    """Counts never describe a newly selected file and the scientific option is forwarded."""
    import chisurf.core.structure

    original = chisurf.core.structure.Structure
    calls = []

    def capture(*args, **kwargs):
        """Record the scientific constructor input while loading the actual PDB."""
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(chisurf.core.structure, "Structure", capture)
    reader = StructureReader(compute_internal_coordinates=True, record_provenance=False)
    reader.read(filename=str(PDB))
    assert calls[0]["p_object"] == str(PDB)
    assert calls[0]["make_coarse"] is True
    reader.filename = "another.pdb"
    assert reader.n_atoms == reader.n_residues == 0
