"""The native structure settings bind to the existing single-file reader."""

from pathlib import Path

import numpy as np
import pytest
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


def test_constructor_source_is_lazy_and_reaches_the_actual_structure_import(tmp_path):
    """A configured source survives construction without eagerly opening a file."""
    absent = tmp_path / "not-materialized.pdb"
    reader = StructureReader(filename=str(absent), record_provenance=False)
    assert reader.filename == str(absent)
    assert reader.n_atoms == reader.n_residues == 0
    selected = StructureReader(filename=str(PDB), record_provenance=False)
    group = selected.get_data()
    assert len(group) == 1
    assert selected.filename == str(PDB)
    assert selected.n_atoms == group[0].n_atoms == 1300
    assert selected.n_residues == group[0].n_residues == 164


@pytest.mark.parametrize("source_alias", [False, True])
def test_source_free_restoration_preserves_structure_reader_facts(
    tmp_path, monkeypatch, source_alias
):
    """Native counters describe the actual cached structure when its source is gone."""
    from chisurf.core.experiments.core import Experiment
    from chisurf.core.project.session import capture_session, restore_session

    copied = tmp_path / "148l.pdb"
    copied.write_bytes(PDB.read_bytes())
    reader = StructureReader(
        experiment=Experiment(name="Structure"),
        compute_internal_coordinates=True,
        record_provenance=False,
    )
    group = reader.get_data(filename=str(copied))
    if source_alias:
        reader.filename = str(copied.parent / "unused" / ".." / copied.name)
    selected_source = reader.filename
    project = capture_session([group], [])
    copied.unlink()

    def no_source_reads(*args, **kwargs):
        """Reject source reads while restoring embedded atoms and reader facts."""
        raise AssertionError("restoration reopened the missing PDB")

    monkeypatch.setattr(StructureReader, "read", no_source_reads)
    restored = restore_session(project)
    structure = restored.datasets[0][0]
    owner = structure.data_reader
    np.testing.assert_array_equal(structure.atoms, group[0].atoms)
    assert structure.n_atoms == 1300 and structure.n_residues == 164
    assert owner.filename == selected_source
    assert owner.compute_internal_coordinates is True
    assert owner.n_atoms == structure.n_atoms
    assert owner.n_residues == structure.n_residues


def test_source_free_restoration_does_not_assign_counts_to_an_unimported_source(
    tmp_path, monkeypatch
):
    """A newly selected source cannot inherit another cached structure's counts."""
    from chisurf.core.experiments.core import Experiment
    from chisurf.core.project.session import capture_session, restore_session

    copied = tmp_path / "148l.pdb"
    copied.write_bytes(PDB.read_bytes())
    reader = StructureReader(experiment=Experiment(name="Structure"), record_provenance=False)
    group = reader.get_data(filename=str(copied))
    reader.filename = str(tmp_path / "not-imported.pdb")
    assert reader.n_atoms == reader.n_residues == 0
    project = capture_session([group], [])
    copied.unlink()

    def no_source_reads(*args, **kwargs):
        """Use cached atoms only; no selection may trigger a source read."""
        raise AssertionError("restoration reread a structure")

    monkeypatch.setattr(StructureReader, "read", no_source_reads)
    restored = restore_session(project)
    cached = restored.datasets[0][0]
    assert cached.n_atoms == 1300 and cached.n_residues == 164
    assert cached.data_reader.filename == reader.filename
    assert cached.data_reader.n_atoms == cached.data_reader.n_residues == 0


def test_structure_configuration_declares_a_native_null_controller():
    """The target row6 configuration must retire its legacy Qt controller."""
    import yaml

    entry = yaml.safe_load(Path("chisurf/core/settings/experiment_configs.yaml").read_text())[
        "structure"
    ]["readers"][0]
    assert entry["reader_class"] == "chisurf.core.experiments.modelling.StructureReader"
    assert entry.get("controller_class") is None
