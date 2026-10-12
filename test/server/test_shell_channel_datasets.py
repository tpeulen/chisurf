"""Datasets the emtk shell reads arrive on its server as what they are.

The shell reads a file in its own process and sends the server the codec's
record of it (``dataset.load`` with ``curve_data``). Two things went wrong on the
way, both invisible until the session was recorded or a structure was drawn:

* a reader that read two files arrived as two reader objects with one UID and
  two configurations (each record carries the reader as it was at that read),
  so recording the session failed with "inconsistent reader identity";
* a structure has no curve arrays, so nothing was sent and the server made an
  empty ``DataCurve`` named after the file -- ProteinMC's model then held that
  curve as its structure, and its Structure page handed it to chimol.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from chisurf.server.session import SessionState

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
PDB = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"


def _reader(experiment: str, name: str):
    sys.path.insert(0, str(Path(__file__).parent))
    from test_model_sections_service import _reader as reader

    return reader(experiment, name)


def _load(state: SessionState, reader, path: Path) -> dict:
    """What ``ChiSurfAPI.load_dataset`` sends in server mode: the client's read, as a record."""
    from chisurf.core.api import _extract_curve_data
    from chisurf.server.services.datasets import add_dataset

    data = reader.get_data(filename=str(path))
    result = add_dataset(
        state,
        curve_data=_extract_curve_data(data),
        reader_name=type(reader).__name__,
        filename=str(path),
    )
    assert result["ok"], result
    return result


def test_two_files_read_by_one_reader_are_one_reader_on_the_server():
    from chisurf.core.project.session import capture_session, restore_session

    state = SessionState()
    reader = _reader("TCSPC", "TXT/CSV")
    _load(state, reader, TCSPC / "Prompt.txt")
    _load(state, reader, TCSPC / "Decay_577D.txt")
    first, second = state.datasets
    assert first.data_reader is second.data_reader
    assert first.experiment is second.experiment
    # The reader is the client's as it is now: it last read the decay.
    assert Path(first.data_reader.filename).name == "Decay_577D.txt"

    restored = restore_session(capture_session(state.datasets, state.fits))
    assert len(restored.datasets) == 2
    # A restored group keeps its type (the emtk dataset list showed it blank after an undo).
    assert [group.experiment.name for group in restored.datasets] == ["TCSPC", "TCSPC"]


def test_a_structure_arrives_as_a_structure_and_proteinmc_models_it():
    from chisurf.core.project.session import capture_session
    from chisurf.core.structure import Structure
    from chisurf.server.services.fits import fit_create

    state = SessionState()
    _load(state, _reader("Modelling", "StructureReader"), PDB)
    dataset = state.datasets[0]
    members = list(dataset)
    assert len(members) == 1 and isinstance(members[0], Structure)
    assert members[0].n_atoms > 1000

    created = fit_create(state, dataset_index=0, model_name="ProteinMC")
    assert created["ok"], created
    assert isinstance(state.fits[0].model.structure, Structure)
    assert capture_session(state.datasets, state.fits) is not None


def test_a_named_reader_without_a_record_reads_the_file_on_the_server():
    """``dataset.load`` with only ``reader_name`` + ``filename`` reads, it does not fabricate."""
    from chisurf.core.data import DataCurve
    from chisurf.core.structure import Structure
    from chisurf.server.services.datasets import add_dataset

    _reader("Modelling", "StructureReader")  # registers the experiments
    state = SessionState()
    result = add_dataset(state, reader_name="StructureReader", filename=str(PDB))
    assert result["ok"], result
    members = list(state.datasets[0])
    assert len(members) == 1 and isinstance(members[0], Structure)
    assert not isinstance(members[0], DataCurve)
    assert members[0].n_atoms > 1000


def test_a_cached_structure_needs_its_snapshot():
    from chisurf.server.services.datasets import _prepare_cached_dataset

    with pytest.raises(ValueError, match="snapshot"):
        _prepare_cached_dataset({"kind": "structure", "uid": "s-1", "arrays": {}})
