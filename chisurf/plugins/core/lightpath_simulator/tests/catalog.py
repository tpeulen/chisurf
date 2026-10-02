"""A small hermetic MMFDB spectra catalogue for the light-path tests and evidence scripts.

The spectra are generated here (Gaussian bands, a sigmoid long-pass, flat quantum efficiency): they stand in for the
curated catalogue so that the default optical path finds its Atto 488 / Atto 647N / 561LP / BP components by name. They
are test data, never shown as measured spectra.
"""

from __future__ import annotations

import numpy as np

WAVELENGTHS = np.arange(350.0, 801.0, 5.0)


def _band(centre: float, sigma: float) -> np.ndarray:
    return np.exp(-0.5 * ((WAVELENGTHS - centre) / sigma) ** 2)


def build_catalogue(db_path) -> dict[str, int]:
    """Create the catalogue at *db_path*; returns ``{name: probe_id}``."""
    from mmfdb.repository import MFDatabase

    ids: dict[str, int] = {}
    with MFDatabase(str(db_path)) as db:
        type_id = db.conn.execute(
            "INSERT INTO probe_types (type_name, display_name) VALUES (?, ?)", ("test", "Test probes")
        ).lastrowid

        def dye(name, ab, em, qy, ec):
            pid = db.add_probe(name, type_id, category="organic_dye")
            db.add_optical_property(pid, "qy", str(qy))
            db.add_optical_property(pid, "ext_coeff", str(ec))
            db.add_spectrum(pid, "absorption", WAVELENGTHS, _band(ab, 18.0))
            db.add_spectrum(pid, "emission", WAVELENGTHS, _band(em, 22.0))
            ids[name] = pid

        def transmission(name, curve, category):
            pid = db.add_probe(name, type_id, category=category)
            db.add_spectrum(pid, "transmission", WAVELENGTHS, curve)
            ids[name] = pid

        dye("Atto 488", 500.0, 520.0, 0.8, 90000)
        dye("Atto 647N", 645.0, 668.0, 0.65, 150000)
        transmission("561LP dichroic", 1.0 / (1.0 + np.exp(-(WAVELENGTHS - 561.0) / 4.0)), "dichroic")
        transmission("BP 500/50 filter", ((WAVELENGTHS > 475) & (WAVELENGTHS < 525)).astype(float) * 0.92, "filter")
        transmission("BP 650/60 filter", ((WAVELENGTHS > 620) & (WAVELENGTHS < 680)).astype(float) * 0.92, "filter")
        for name in ("APD (flat QE)", "PMT (flat QE)"):
            pid = db.add_probe(name, type_id, category="detector")
            db.add_spectrum(pid, "quantum_efficiency", WAVELENGTHS, np.full_like(WAVELENGTHS, 0.6))
            ids[name] = pid
    return ids
