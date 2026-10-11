"""A scratch MMFDB with two dyes for the Förster radius calculator.

Shared by the before-half capture of the Qt calculator, the emtk dialog test and
the Qt-free unit tests, so all three see the same probes in the same state.
Both dyes carry an emission and an absorption spectrum (each can be donor or
acceptor), a quantum yield and an extinction coefficient; the pair
``CachedDonor``/``CachedAcceptor`` is not created here -- tests that need a
tabulated R0 add it themselves.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

#: name -> (absorption max, emission max, width, QY, epsilon max)
DYES = {
    "Dye488": (495.0, 520.0, 22.0, 0.92, 73000.0),
    "Dye594": (590.0, 617.0, 25.0, 0.66, 92000.0),
}
WAVELENGTHS = np.linspace(400.0, 750.0, 351)


def gaussian(centre: float, width: float) -> np.ndarray:
    """A peak-normalised Gaussian band on :data:`WAVELENGTHS`."""
    return np.exp(-(((WAVELENGTHS - centre) / width) ** 2))


def make_spectra_db(path: Path) -> dict[str, int]:
    """Create the scratch database at *path*; return ``{dye name: probe_id}``."""
    from mmfdb.repository import MFDatabase

    ids: dict[str, int] = {}
    with MFDatabase(str(path)) as db:
        type_id = db.conn.execute(
            "INSERT INTO probe_types (type_name, display_name) VALUES (?, ?)",
            ("test-spectra", "Test spectra"),
        ).lastrowid
        for name, (abs_max, em_max, width, qy, eps) in DYES.items():
            pid = db.add_probe(name, type_id, category="organic_dye")
            db.add_spectrum(pid, "absorption", WAVELENGTHS, gaussian(abs_max, width))
            db.add_spectrum(pid, "emission", WAVELENGTHS, gaussian(em_max, width))
            db.add_optical_property(pid, "qy", str(qy))
            db.add_optical_property(pid, "ext_coeff", str(eps))
            ids[name] = pid
        db.conn.commit()
    return ids


def opener(path: Path):
    """A database factory over *path*, read-only, as the calculator opens MMFDB."""
    from mmfdb.repository import MFDatabase

    return lambda: MFDatabase(str(path), readonly=True)
