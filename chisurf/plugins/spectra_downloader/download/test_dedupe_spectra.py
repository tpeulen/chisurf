"""Headless tests for the spectra quality/dedupe curation utility."""

from __future__ import annotations

import sqlite3

import numpy as np

from chisurf.plugins.spectra_downloader.download import dedupe_spectra as ds


def _make_db() -> sqlite3.Connection:
    """In-memory DB with the minimal probes/spectra/optical_properties schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE probes (
            probe_id INTEGER PRIMARY KEY, chromophore_name TEXT, category TEXT,
            source TEXT, verification_status TEXT, deleted_at TEXT);
        CREATE TABLE spectra (
            id INTEGER PRIMARY KEY, probe_id INTEGER, spectrum_type TEXT,
            wavelengths BLOB, intensity_values BLOB, wavelength_unit TEXT DEFAULT 'nm',
            intensity_unit TEXT DEFAULT 'normalized', details TEXT,
            created_at TEXT, updated_at TEXT, deleted_at TEXT,
            UNIQUE (probe_id, spectrum_type));
        CREATE TABLE optical_properties (
            id INTEGER PRIMARY KEY, probe_id INTEGER, property_name TEXT,
            property_value TEXT, unit TEXT, details TEXT,
            created_at TEXT, updated_at TEXT, deleted_at TEXT,
            UNIQUE (probe_id, property_name));
        """
    )
    return conn


def _blob(a) -> bytes:
    return np.asarray(a, dtype=np.float64).tobytes()


def _add_spectrum(conn, sid, pid, stype, w, y):
    conn.execute(
        "INSERT INTO spectra (id, probe_id, spectrum_type, wavelengths, intensity_values) VALUES (?,?,?,?,?)",
        (sid, pid, stype, _blob(w), _blob(y)),
    )


def test_assess_flags_bad_spectra():
    """Empty, non-monotonic, negative and all-zero curves are flagged; a clean one is not."""
    conn = _make_db()
    conn.execute("INSERT INTO probes (probe_id, chromophore_name) VALUES (1, 'x')")
    _add_spectrum(
        conn, 1, 1, "emission", [400, 410, 420, 430, 440], [0.1, 0.5, 1.0, 0.5, 0.1]
    )  # clean
    _add_spectrum(
        conn, 2, 1, "absorption", [400, 420, 410, 430, 440], [0.1, 0.2, 0.3, 0.2, 0.1]
    )  # non-monotonic
    _add_spectrum(
        conn, 3, 1, "transmission", [400, 410, 420, 430, 440], [-0.01, 0.5, 1.0, 0.5, 0.1]
    )  # negative
    _add_spectrum(conn, 4, 1, "excitation", [], [])  # empty
    conn.commit()

    report = ds.assess_spectra(conn)
    flagged = {sid: reason for sid, _pid, _st, reason in report["issues"]}
    assert report["n"] == 4
    assert 1 not in flagged
    assert "non-monotonic" in flagged[2]
    assert "negative" in flagged[3]
    assert "empty" in flagged[4]


def test_merge_group_unions_spectra_and_soft_deletes_duplicate():
    """Merging pulls the duplicate's missing spectra into the primary and soft-deletes it."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO probes (probe_id, chromophore_name, source) VALUES (1, 'EGFP', 'fpbase')"
    )
    conn.execute(
        "INSERT INTO probes (probe_id, chromophore_name, source) VALUES (2, 'EGFP (long)', 'chroma')"
    )
    _add_spectrum(conn, 1, 1, "absorption", [400, 410], [0.1, 0.9])
    _add_spectrum(conn, 2, 1, "emission", [500, 510], [0.9, 0.1])
    _add_spectrum(conn, 3, 2, "emission", [500, 510], [0.8, 0.2])  # overlaps -> ignored
    _add_spectrum(conn, 4, 2, "excitation", [390, 400], [0.2, 0.8])  # new -> copied
    conn.commit()

    ds._merge_group(conn, primary_id=1, duplicate_ids=[2])
    conn.commit()

    live = {
        r[0]
        for r in conn.execute(
            "SELECT spectrum_type FROM spectra WHERE probe_id=1 AND deleted_at IS NULL"
        )
    }
    assert live == {"absorption", "emission", "excitation"}
    # longest name kept, duplicate soft-deleted.
    assert (
        conn.execute("SELECT chromophore_name FROM probes WHERE probe_id=1").fetchone()[0]
        == "EGFP (long)"
    )
    assert conn.execute("SELECT deleted_at FROM probes WHERE probe_id=2").fetchone()[0] is not None


def test_bayes_classifier_ranks_pairs():
    """The naive-Bayes posterior is high for same-dye pairs and near-zero for distinct dyes."""
    af1 = {"chromophore_name": "Alexa 488", "abs_max": 495, "em_max": 519, "source": "chroma"}
    af2 = {"chromophore_name": "AlexaFluor488", "abs_max": 496, "em_max": 520, "source": "fpbase"}
    cy = {"chromophore_name": "Cy5", "abs_max": 649, "em_max": 670, "source": "a"}
    cyanine = {"chromophore_name": "Cyanine 5", "abs_max": 650, "em_max": 671, "source": "b"}
    egfp = {"chromophore_name": "EGFP", "abs_max": 488, "em_max": 507, "source": "a"}
    mcherry = {"chromophore_name": "mCherry", "abs_max": 587, "em_max": 610, "source": "b"}

    assert ds.duplicate_probability(af1, af2) > 0.9  # AF488 alias, close maxima
    assert ds.duplicate_probability(cy, cyanine) > 0.9  # cyanine spelling, close maxima
    assert ds.duplicate_probability(egfp, mcherry) < 0.05  # different dye, far maxima

    # same normalized name but incompatible maxima -> classifier resists the false merge.
    same_name_far = ds.duplicate_probability(
        {"chromophore_name": "Cy5", "abs_max": 649, "em_max": 670, "source": "a"},
        {"chromophore_name": "Cy5", "abs_max": 550, "em_max": 570, "source": "b"},
    )
    assert same_name_far < ds.duplicate_probability(cy, cyanine)


def test_find_candidates_surfaces_fuzzy_pair_only():
    """A fuzzy near-duplicate is highlighted; an unrelated dye is not."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO probes (probe_id, chromophore_name, category, source) VALUES (1,'Cy5','organic_dye','chroma')"
    )
    conn.execute(
        "INSERT INTO probes (probe_id, chromophore_name, category, source) VALUES (2,'Cyanine 5','organic_dye','photochemcad')"
    )
    conn.execute(
        "INSERT INTO probes (probe_id, chromophore_name, category, source) VALUES (3,'EGFP','protein','fpbase')"
    )
    for pid, amax, emax in ((1, 649, 670), (2, 650, 671), (3, 488, 507)):
        conn.execute(
            "INSERT INTO optical_properties (probe_id, property_name, property_value) VALUES (?, 'abs_max', ?)",
            (pid, amax),
        )
        conn.execute(
            "INSERT INTO optical_properties (probe_id, property_name, property_value) VALUES (?, 'em_max', ?)",
            (pid, emax),
        )
    conn.commit()

    cands = ds.find_duplicate_candidates(conn, min_prob=0.5)
    pairs = {(c["a"], c["b"]) for c in cands}
    assert (1, 2) in pairs  # Cy5 ~ Cyanine 5 surfaces
    assert not any(3 in (c["a"], c["b"]) for c in cands)  # EGFP never paired
