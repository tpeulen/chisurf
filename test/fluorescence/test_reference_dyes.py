"""Tests for the MMFDB-backed reference-dye lookup used by the FCS tools."""

from __future__ import annotations

import math

import pytest

import chisurf.core.fluorescence.dyes as dyes


@pytest.fixture
def fresh_database(tmp_path, monkeypatch):
    """Point MMFDB at an empty database and clear the process-level cache."""
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "dyes.db"))
    monkeypatch.setattr(dyes, "_CACHE", None)
    monkeypatch.setattr(dyes, "_ALIASES", None)
    yield
    monkeypatch.setattr(dyes, "_CACHE", None)
    monkeypatch.setattr(dyes, "_ALIASES", None)


def test_reference_dyes_are_read_from_mmfdb(fresh_database):
    """A fresh database is seeded and every species is a real MMFDB probe."""
    table = dyes.reference_dyes()
    assert table, "no reference species available"
    assert "Rhodamine 6G" in table
    entry = table["Rhodamine 6G"]
    assert entry["d25_um2_s"] == 414.0
    assert entry["unit"] == "um^2/s"
    assert entry["probe_id"] is not None
    assert entry["sources"][0]["citation"].startswith("Kapusta")


def test_diffusion_is_stored_as_a_probe_property(fresh_database):
    """Diffusion lives on the probe next to the other dye properties."""
    from mmfdb.models import DIFFUSION_PROPERTY_NAME
    from mmfdb.repository import MFDatabase
    from mmfdb.store.database_resolver import resolve_database_path

    probe_id = dyes.reference_dyes()["Cy5"]["probe_id"]
    with MFDatabase(str(resolve_database_path())) as db:
        row = db.conn.execute(
            "SELECT property_value, unit FROM optical_properties "
            "WHERE probe_id = ? AND property_name = ?",
            (probe_id, DIFFUSION_PROPERTY_NAME),
        ).fetchone()
    assert row is not None
    assert float(row["property_value"]) == 360.0


def test_lookup_accepts_legacy_names(fresh_database):
    """Names used before the table moved into MMFDB still resolve."""
    assert dyes.get_dye("Rhodamine 6G (Rh6G)")["name"] == "Rhodamine 6G"
    assert dyes.diffusion_coefficient_25C("Rh6G") == 414.0
    assert dyes.diffusion_coefficient_25C("Alexa 647") == 330.0
    assert dyes.get_dye("not a dye") is None
    assert math.isnan(dyes.diffusion_coefficient_25C("not a dye"))


def test_dye_names_are_sorted(fresh_database):
    names = dyes.dye_names()
    assert names == sorted(names)
    assert len(names) == len(dyes.reference_dyes())


def test_calculator_core_reexports_the_mmfdb_lookup(fresh_database):
    """The FCS calculator core keeps no private dye table."""
    from chisurf.plugins.fcs.fcs_calculator.core import algorithms

    assert not hasattr(algorithms, "DYE_DATA")
    assert algorithms.dye_diffusion_25C("Rhodamine 110") == 470.0
    assert algorithms.get_dye("Rhodamine 110")["probe_id"] is not None


def test_calculator_cli_can_take_d_from_a_dye(fresh_database, capsys):
    """``--dye`` resolves through MMFDB and scales D to the given conditions."""
    import json

    from chisurf.plugins.fcs.fcs_calculator.cli.main import main

    assert main(["--dye", "Rhodamine 6G", "--temp-C", "25.0", "--water-eta"]) == 0
    result = json.loads(capsys.readouterr().out)
    # At the reference temperature the value is D_25 up to the small mismatch
    # between the water-viscosity model and the tabulated eta(25 °C).
    assert result["D_um2_s"] == pytest.approx(414.0, rel=1e-3)
