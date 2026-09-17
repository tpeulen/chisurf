"""Integration contracts for experiment-reader provenance."""

from __future__ import annotations

from pathlib import Path

import pytest
from mmfdb.repository import MFDatabase

import chisurf.core.data
from chisurf.core.experiments.core.reader import ExperimentReader
from chisurf.core.experiments.deer.reader import DeerReader
from chisurf.core.experiments.globalfit.reader import GlobalFitSetup
from chisurf.core.experiments.ics import ICSReader
from chisurf.core.experiments.modelling.reader import StructureReader


class _Reader(ExperimentReader):
    """Minimal reader that can fail before producing decoded data."""

    def __init__(self, *, fail: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.fail = fail
        self.experiment = None

    def autofitrange(self, data, **kwargs):
        return 0, len(data)

    def read(self, filename=None, **kwargs):
        if self.fail:
            raise ValueError("decode failed")
        return chisurf.core.data.DataCurve(
            name="decoded",
            x=[0.0, 1.0],
            y=[1.0, 2.0],
        )


def _row_count(db: MFDatabase, table: str) -> int:
    return int(db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_failed_decode_performs_no_mmfdb_writes(tmp_path: Path) -> None:
    """Source registration must not happen until decoding has succeeded."""
    source = tmp_path / "source.dat"
    source.write_bytes(b"raw")
    db = MFDatabase(tmp_path / "reader.db")
    try:
        reader = _Reader(db=db, fail=True)
        with pytest.raises(ValueError, match="decode failed"):
            reader.get_data(filename=str(source))

        assert _row_count(db, "mmfdb_artifact") == 0
        assert _row_count(db, "mmfdb_operation") == 0
    finally:
        db.close()


def test_provenance_failure_rolls_back_the_whole_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed final operation link must not leave source/derived rows behind."""
    source = tmp_path / "source.dat"
    source.write_bytes(b"raw")
    db = MFDatabase(tmp_path / "reader.db")
    try:

        def fail_operation(**kwargs):
            raise RuntimeError("operation rejected")

        monkeypatch.setattr(db, "record_operation_with_artifacts", fail_operation)
        reader = _Reader(db=db)
        group = reader.get_data(filename=str(source))

        assert len(group) == 1
        assert _row_count(db, "mmfdb_artifact") == 0
        assert _row_count(db, "mmfdb_operation") == 0
        assert _row_count(db, "mmfdb_object") == 0
        assert "mmfdb" not in group[0].meta_data
    finally:
        db.close()


def test_uncovered_experiment_families_declare_stable_provenance_contracts() -> None:
    """Every reader family must state vocabulary-backed operation/artifact kinds."""
    assert (DeerReader.operation_type, DeerReader.artifact_kind_derived) == (
        "analysis",
        "analysis_result",
    )
    assert (ICSReader.operation_type, ICSReader.artifact_kind_derived) == (
        "image_analysis",
        "analysis_result",
    )
    assert (StructureReader.operation_type, StructureReader.artifact_kind_derived) == (
        "import",
        "processed_data",
    )
    assert GlobalFitSetup.operation_type == "global_fit"


def test_successful_decode_records_one_linked_operation(tmp_path: Path) -> None:
    """One reader call produces one operation joining its source and decoded data."""
    source = tmp_path / "source.csv"
    source.write_text("x,y\n0,1\n", encoding="utf-8")
    db = MFDatabase(tmp_path / "reader.db")
    try:
        group = _Reader(db=db).get_data(filename=str(source))

        assert _row_count(db, "mmfdb_artifact") == 2
        assert _row_count(db, "mmfdb_operation") == 1
        assert _row_count(db, "mmfdb_operation_artifact") == 2
        operation_id = group[0].meta_data["mmfdb"]["operation_id"]
        operation = db.get_operation(operation_id)
        assert operation["status"] == "succeeded"
    finally:
        db.close()


def test_globalfit_placeholder_does_not_archive_by_default() -> None:
    """Creating a UI placeholder is not a scientific global-fit operation."""
    assert GlobalFitSetup().record_provenance is False
