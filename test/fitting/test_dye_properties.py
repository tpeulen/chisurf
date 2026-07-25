"""Dye properties and spectra from MMFDB feeding the calibration.

The quantum yields and the Förster radius are properties of the *dyes*, not of
the measurement, so selecting a donor and an acceptor should be enough to fill
them in. These tests pin that chain — spectra and curated properties in, R0 and
quantum yields out — and, just as importantly, that a gap in the catalogue is
reported rather than papered over with a default.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fret.dyes import (
    DyeProperties,
    apply_to_calibration,
    dye_properties,
    fret_pair,
    list_dyes,
)


class _StubDatabase:
    """A small stand-in for MMFDB with two dyes and one gap."""

    #: probe_id -> (name, category, {property: value})
    PROBES = {
        1: ("StubDonor", "organic_dye", {"qy": 0.8, "ext_coeff": 80000.0, "lifetime": 3.6}),
        2: ("StubAcceptor", "organic_dye", {"qy": 0.62, "ext_coeff": 150000.0}),
        3: ("StubNoProperties", "organic_dye", {}),
    }

    def __init__(self):
        grid = np.arange(400.0, 801.0, 1.0)
        self._spectra = {
            (1, "emission"): (grid, np.exp(-0.5 * ((grid - 570.0) / 20.0) ** 2)),
            (1, "absorption"): (grid, np.exp(-0.5 * ((grid - 550.0) / 18.0) ** 2)),
            (2, "emission"): (grid, np.exp(-0.5 * ((grid - 665.0) / 22.0) ** 2)),
            (2, "absorption"): (grid, np.exp(-0.5 * ((grid - 645.0) / 20.0) ** 2)),
            (3, "emission"): (grid, np.exp(-0.5 * ((grid - 500.0) / 20.0) ** 2)),
        }

    def get_probes(self):
        """Return every probe row."""
        return [{"probe_id": pid, "chromophore_name": name, "category": category}
                for pid, (name, category, _) in self.PROBES.items()]

    def get_probe(self, probe_id):
        """Return one probe row."""
        entry = self.PROBES.get(int(probe_id))
        if entry is None:
            return None
        return {"probe_id": int(probe_id), "chromophore_name": entry[0], "category": entry[1]}

    def get_optical_properties(self, probe_id):
        """Return the curated optical properties of a probe."""
        _, _, properties = self.PROBES[int(probe_id)]
        return [{"property_name": k, "property_value": v} for k, v in properties.items()]

    def get_spectrum_record(self, probe_id, spectrum_type):
        """Return one stored spectrum."""
        entry = self._spectra.get((int(probe_id), spectrum_type))
        if entry is None:
            return None
        return {"wavelengths": entry[0], "intensity_values": entry[1]}

    def lookup_forster_radius(self, donor_name, acceptor_name):
        """No stored pair values in the stub."""
        return None


@pytest.fixture()
def database():
    """Return a stub database with two usable dyes and one without properties."""
    return _StubDatabase()


def test_dye_properties_are_read(database):
    """Curated properties and spectra availability come back per dye."""
    donor = dye_properties("StubDonor", db=database)
    assert isinstance(donor, DyeProperties)
    assert donor.quantum_yield == pytest.approx(0.8)
    assert donor.extinction_coefficient == pytest.approx(80000.0)
    assert donor.lifetime == pytest.approx(3.6)
    assert donor.has_emission and donor.has_absorption
    assert donor.usable_as_donor and donor.usable_as_acceptor

    bare = dye_properties("StubNoProperties", db=database)
    assert bare.quantum_yield is None
    assert not bare.usable_as_donor          # no quantum yield
    assert not bare.usable_as_acceptor       # no absorption spectrum


def test_only_usable_dyes_are_listed(database):
    """The picker offers dyes the database can actually describe."""
    names = [d.name for d in list_dyes(db=database)]
    assert names == ["StubAcceptor", "StubDonor"]
    assert "StubNoProperties" in [d.name for d in list_dyes(db=database, usable_only=False)]


def test_forster_radius_is_computed_from_the_spectra(database):
    """R0 follows from the overlap of the stored spectra, not from a table."""
    pair = fret_pair("StubDonor", "StubAcceptor", db=database)
    assert pair is not None
    assert pair.provenance["forster_radius"] == "mmfdb:spectra"
    assert pair.overlap_integral > 0
    assert 30.0 < pair.forster_radius < 100.0

    # R0 scales as (kappa2)^(1/6) and n^(-2/3) — the two assumptions it rests on
    tighter = fret_pair("StubDonor", "StubAcceptor", db=database, kappa2=4.0)
    assert tighter.forster_radius == pytest.approx(
        pair.forster_radius * (4.0 / (2.0 / 3.0)) ** (1 / 6), rel=1e-6
    )
    denser = fret_pair("StubDonor", "StubAcceptor", db=database, refractive_index=1.40)
    assert denser.forster_radius == pytest.approx(
        pair.forster_radius * (1.40 / 1.33) ** (-2 / 3), rel=1e-6
    )


def test_a_gap_in_the_catalogue_is_reported(database):
    """An acceptor without properties yields no R0 — and says so."""
    pair = fret_pair("StubDonor", "StubNoProperties", db=database)
    assert pair is not None
    assert pair.forster_radius is None
    assert pair.provenance["forster_radius"] == "missing"
    assert pair.provenance["quantum_yield_acceptor"] == "missing"
    assert "missing" in pair.summary()


def test_the_pair_fills_a_calibration(database):
    """Selecting the dyes sets the quantities that are properties of the dyes."""
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    calibration = CalibrationParameters()
    calibration.r0 = 1.0
    pair = fret_pair("StubDonor", "StubAcceptor", db=database)
    calibration, applied = apply_to_calibration(pair, calibration)

    assert calibration.phi_d == pytest.approx(0.8)
    assert calibration.phi_a == pytest.approx(0.62)
    assert calibration.r0 == pytest.approx(pair.forster_radius)
    assert set(applied) == {"PhiD", "PhiA", "R0"}


def test_a_gap_never_overwrites_a_set_value(database):
    """What the database cannot answer is left alone, not defaulted."""
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    calibration = CalibrationParameters()
    calibration.r0, calibration.phi_a = 55.0, 0.35
    pair = fret_pair("StubDonor", "StubNoProperties", db=database)
    calibration, applied = apply_to_calibration(pair, calibration)

    assert calibration.r0 == pytest.approx(55.0)      # kept
    assert calibration.phi_a == pytest.approx(0.35)   # kept
    assert applied == {"PhiD": "mmfdb:property"}      # only what was known


def test_absorption_falls_back_to_the_excitation_curve():
    """A catalogue entry with only an excitation curve still gives an R0.

    Most catalogue spectra are curated as *excitation* rather than absorption;
    for a dye the two have the same shape, and refusing them would rule out most
    of the database.
    """
    database = _StubDatabase()
    grid = np.arange(400.0, 801.0, 1.0)
    database._spectra.pop((2, "absorption"))
    database._spectra[(2, "excitation")] = (grid, np.exp(-0.5 * ((grid - 645.0) / 20.0) ** 2))

    pair = fret_pair("StubDonor", "StubAcceptor", db=database)
    assert pair.forster_radius is not None
    assert pair.provenance["forster_radius"] == "mmfdb:spectra"


# ---------------------------------------------------------------------------
# against the real database, when there is one
# ---------------------------------------------------------------------------


def test_real_database_pair_reproduces_the_literature():
    """A curated pair computed from real spectra lands on the known R0.

    EGFP → mCherry is ~52 Å and ATTO 550 → ATTO 643 ~65 Å in the literature;
    computing them from the database's own spectra is the end-to-end check that
    the properties, the spectra and the overlap integral fit together.
    """
    pytest.importorskip("mmfdb")
    expectations = {("EGFP", "mCherry"): (48.0, 57.0),
                    ("ATTO 550", "ATTO 643"): (60.0, 70.0)}
    checked = 0
    for (donor, acceptor), (low, high) in expectations.items():
        pair = fret_pair(donor, acceptor)
        if pair is None or pair.forster_radius is None:
            continue
        assert low < pair.forster_radius < high, f"{donor}->{acceptor}"
        assert pair.provenance["forster_radius"] == "mmfdb:spectra"
        checked += 1
    if checked == 0:
        pytest.skip("no curated pair with spectra available in this database")


def test_real_repository_round_trip(tmp_path):
    """The chain runs on the actual MMFDB code, not only on the stub.

    Two dyes with their spectra and properties are written through MMFDB's own
    API and read back through it, so the accessors, the property spellings and
    the spectrum storage are exercised as they are in a real database — the stub
    above could agree with itself while disagreeing with MMFDB.
    """
    pytest.importorskip("mmfdb")
    from mmfdb.repository import MFDatabase

    grid = np.arange(400.0, 801.0, 1.0)
    database = MFDatabase(str(tmp_path / "dyes.db"))
    try:
        database.add_probe(1, name="RepoDonor", category="organic_dye")
        database.add_probe(2, name="RepoAcceptor", category="organic_dye")
        database.add_optical_property(1, "qy", 0.8)
        database.add_optical_property(1, "ext_coeff", 80000.0)
        database.add_optical_property(1, "lifetime", 3.6)
        database.add_optical_property(2, "qy", 0.62)
        database.add_optical_property(2, "ext_coeff", 150000.0)
        database.add_spectrum(1, "emission", grid,
                              np.exp(-0.5 * ((grid - 570.0) / 20.0) ** 2))
        database.add_spectrum(2, "absorption", grid,
                              np.exp(-0.5 * ((grid - 645.0) / 20.0) ** 2))

        donor = dye_properties("RepoDonor", db=database)
        assert donor is not None and donor.quantum_yield == pytest.approx(0.8)
        assert donor.lifetime == pytest.approx(3.6)

        pair = fret_pair("RepoDonor", "RepoAcceptor", db=database)
        assert pair is not None
        assert pair.provenance["forster_radius"] == "mmfdb:spectra"
        assert 30.0 < pair.forster_radius < 120.0
        assert pair.provenance["donor_lifetime"] == "mmfdb:property"

        names = [d.name for d in list_dyes(db=database)]
        assert {"RepoDonor", "RepoAcceptor"} <= set(names)
    finally:
        database.close()
