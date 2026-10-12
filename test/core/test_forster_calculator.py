"""The Förster radius calculator's model, without a toolkit and without MMFDB.

A fake database (``sqlite3`` in memory, the four tables the calculator reads)
stands in for MMFDB; one test runs the same model against a real scratch
``MFDatabase`` so the SQL is checked against the real schema too.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra
from chisurf.core.fluorescence.fret.forster_calculator import (
    GRID_POINTS,
    ForsterCalculatorModel,
    overlap_curves,
)

WL = np.linspace(400.0, 750.0, 351)


def _band(centre: float, width: float = 25.0, wl: np.ndarray = WL) -> np.ndarray:
    return np.exp(-(((wl - centre) / width) ** 2))


class FakeDB:
    """The slice of ``MFDatabase`` the calculator uses, over an in-memory SQLite."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE probes (probe_id INTEGER PRIMARY KEY, chromophore_name TEXT,
                                 deleted_at TEXT);
            CREATE TABLE spectra (probe_id INTEGER, spectrum_type TEXT, wavelengths BLOB,
                                  intensity_values BLOB, deleted_at TEXT);
            CREATE TABLE optical_properties (probe_id INTEGER, property_name TEXT,
                                             property_value TEXT, deleted_at TEXT);
            CREATE TABLE flr_fret_forster_radius (donor_probe_id INTEGER,
                                                  acceptor_probe_id INTEGER,
                                                  forster_radius REAL);
            """
        )
        self.opened = 0
        self.closed = 0

    def add(self, name, spectra=(), props=()):
        pid = self.conn.execute(
            "INSERT INTO probes (chromophore_name) VALUES (?)", (name,)
        ).lastrowid
        for kind, wl, values in spectra:
            self.conn.execute(
                "INSERT INTO spectra VALUES (?, ?, ?, ?, NULL)",
                (pid, kind, np.asarray(wl, float).tobytes(), np.asarray(values, float).tobytes()),
            )
        for key, value in props:
            self.conn.execute(
                "INSERT INTO optical_properties VALUES (?, ?, ?, NULL)", (pid, key, value)
            )
        return pid

    def get_optical_properties(self, probe_id):
        rows = self.conn.execute(
            "SELECT property_name, property_value FROM optical_properties "
            "WHERE probe_id = ? AND deleted_at IS NULL",
            (probe_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def opener(self):
        def open_db():
            self.opened += 1
            return self

        return open_db

    def close(self):
        self.closed += 1


@pytest.fixture
def db():
    fake = FakeDB()
    fake.ids = {
        "Donor": fake.add(
            "Donor",
            [("emission", WL, _band(520.0)), ("absorption", WL, _band(495.0))],
            [("qy", "0.8"), ("ext_coeff", "not a number")],
        ),
        "Acceptor": fake.add(
            "Acceptor",
            [("absorption", WL, _band(590.0)), ("emission", WL, _band(617.0))],
            [("molar_extinction", "92000"), ("quantum yield", "-1")],
        ),
        "Excitation only": fake.add("Excitation only", [("excitation", WL, _band(500.0))]),
    }
    return fake


def _expected(qy=0.8, emax=92000.0, n=1.33, donor=520.0, acceptor=590.0):
    grid = np.linspace(400.0, 750.0, GRID_POINTS)
    absorption = _band(acceptor)
    return forster_radius_from_spectra(
        grid,
        np.interp(grid, WL, _band(donor)),
        np.interp(grid, WL, absorption / absorption.max() * emax),
        donor_quantum_yield=qy,
        kappa2=2.0 / 3.0,
        refractive_index=n,
    )


def test_options_list_probes_by_the_spectrum_their_role_needs(db):
    model = ForsterCalculatorModel(open_database=db.opener())
    assert model.available
    assert model.donor_options() == [
        ("", ""),
        (db.ids["Acceptor"], "Acceptor"),
        (db.ids["Donor"], "Donor"),
    ]
    assert model.acceptor_options() == [
        ("", ""),
        (db.ids["Acceptor"], "Acceptor"),
        (db.ids["Donor"], "Donor"),
    ]
    assert db.opened == db.closed == 1


def test_choosing_the_pair_fills_properties_and_computes_r0(db):
    model = ForsterCalculatorModel(open_database=db.opener())
    model.set_donor(db.ids["Donor"])
    assert model.donor_qy == 0.8
    assert model.r0 is None and not model.enabled("apply")
    model.set_acceptor(db.ids["Acceptor"])
    assert model.acceptor_emax == 92000.0
    r0, overlap = _expected()
    np.testing.assert_allclose(model.r0, r0, rtol=1e-12)
    np.testing.assert_allclose(model.overlap, overlap, rtol=1e-12)
    assert not model.cached and model.enabled("apply")
    assert model.status.startswith(f"R₀ = {r0:.1f} Å")
    assert model.detail.startswith("J = ")
    assert model.curves["wavelengths"].shape == (GRID_POINTS,)
    assert "Donor: emission · 351 pts · 400–750 nm" in model.spectra_text()

    model.donor_qy = 0.5
    model.refractive_index = 1.4
    model.changed()
    np.testing.assert_allclose(model.r0, _expected(qy=0.5, n=1.4)[0], rtol=1e-12)

    # A property the probe does not store (or stores unusably) keeps the typed value.
    model.donor_qy = 0.3
    model.set_donor(db.ids["Acceptor"])
    assert model.donor_qy == 0.3
    model.set_donor("")
    assert model.donor is None and model.r0 is None and model.status == ""


def test_tabulated_r0_wins_over_the_spectra(db):
    db.conn.execute(
        "INSERT INTO flr_fret_forster_radius VALUES (?, ?, ?)",
        (db.ids["Donor"], db.ids["Acceptor"], 52.5),
    )
    model = ForsterCalculatorModel(open_database=db.opener())
    model.set_donor(db.ids["Donor"])
    model.set_acceptor(db.ids["Acceptor"])
    assert model.r0 == 52.5 and model.cached and model.overlap is None
    assert "(cached)" in model.status


def test_spectra_without_a_shared_range_give_zero():
    fake = FakeDB()
    blue = np.linspace(400.0, 500.0, 101)
    red = np.linspace(600.0, 700.0, 101)
    donor = fake.add("Blue", [("emission", blue, _band(450.0, wl=blue))])
    acceptor = fake.add("Red", [("absorption", red, _band(650.0, wl=red))])
    model = ForsterCalculatorModel(open_database=fake.opener())
    model.set_donor(donor)
    model.set_acceptor(acceptor)
    assert model.r0 == 0.0 and "no spectral overlap" in model.status
    assert (
        overlap_curves(
            {"wavelengths": blue, "intensity": blue}, {"wavelengths": red, "intensity": red}, 1.0
        )
        is None
    )


def test_unavailable_database_explains_itself():
    def missing():
        raise RuntimeError("MMFDB is unavailable; spectra selection requires MMFDB.")

    model = ForsterCalculatorModel(open_database=missing)
    assert not model.available
    assert "unavailable" in model.status and model.detail == model.status
    assert not model.enabled("donor") and not model.enabled("apply")
    assert model.donor_options() == [("", "")]
    assert model.compute() is None and "unavailable" in model.status

    def broken():
        raise OSError("disk")

    assert ForsterCalculatorModel(open_database=broken).status == "Could not open MMFDB database."


def test_real_mmfdb_schema(tmp_path):
    pytest.importorskip("mmfdb.repository")
    from test.native_emtk.forster_spectra_fixture import (
        DYES,
        WAVELENGTHS,
        gaussian,
        make_spectra_db,
        opener,
    )

    ids = make_spectra_db(tmp_path / "spectra.sqlite")
    model = ForsterCalculatorModel(open_database=opener(tmp_path / "spectra.sqlite"))
    model.set_donor(ids["Dye488"])
    model.set_acceptor(ids["Dye594"])
    assert model.donor_qy == DYES["Dye488"][3]
    assert model.acceptor_emax == DYES["Dye594"][4]
    grid = np.linspace(WAVELENGTHS[0], WAVELENGTHS[-1], GRID_POINTS)
    absorption = gaussian(DYES["Dye594"][0], DYES["Dye594"][2])
    expected, _ = forster_radius_from_spectra(
        grid,
        np.interp(grid, WAVELENGTHS, gaussian(DYES["Dye488"][1], DYES["Dye488"][2])),
        np.interp(grid, WAVELENGTHS, absorption / absorption.max() * DYES["Dye594"][4]),
        donor_quantum_yield=DYES["Dye488"][3],
        kappa2=2.0 / 3.0,
        refractive_index=1.33,
    )
    np.testing.assert_allclose(model.r0, expected, rtol=1e-12)
