"""The tree must run on NumPy 1 and NumPy 2 alike.

NumPy 2 removed a batch of aliases (``np.trapz``, ``np.bool8``, ``np.NaN``, …).
Each removal raises ``AttributeError`` at the call site — often inside a
``try``/``except`` that turns it into a silent wrong answer rather than a crash.
Three call sites in this tree were dead under NumPy 2 before the shim existed:
the Foerster overlap integral, a fractal-dimension transfer efficiency and the
light-path spectral propagation. These tests pin that the shim is applied on import and that those
three paths actually compute.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf  # noqa: F401  (importing the package is what applies the shim)
from chisurf.core.runtime.compat import NUMPY_ALIASES, applied_shims, apply_numpy_compat


def test_both_spellings_exist_after_importing_chisurf():
    """Old and new spelling are both available, whichever NumPy is installed."""
    for old, new in NUMPY_ALIASES.items():
        assert hasattr(np, old), f"np.{old} missing — the compat shim did not run"
        assert hasattr(np, new), f"np.{new} missing — the compat shim did not run"


def test_restored_aliases_are_the_same_object():
    """A restored alias *is* its replacement — a rename, never a reimplementation.

    Only the names this process had to restore are checked: NumPy may still ship
    its own (possibly deprecated) alias, and that one is left alone.
    """
    assert applied_shims, "nothing was restored — is this really a NumPy 2 build?"
    for restored, source in applied_shims.items():
        restored_value, source_value = getattr(np, restored), getattr(np, source)
        if isinstance(restored_value, float):     # NaN/Inf constants
            assert np.isnan(restored_value) == np.isnan(source_value)
            assert np.isinf(restored_value) == np.isinf(source_value)
        else:
            assert restored_value is source_value, f"np.{restored} is not np.{source}"


def test_applying_twice_changes_nothing():
    """The shim is idempotent, so import order cannot matter."""
    before = {name: getattr(np, name) for name in NUMPY_ALIASES}
    assert apply_numpy_compat() == {}             # nothing left to restore
    assert all(getattr(np, name) is value for name, value in before.items()
               if not isinstance(value, float))


def test_trapz_still_integrates():
    """The restored name is a working function, not a placeholder."""
    x = np.linspace(0.0, 1.0, 101)
    assert float(np.trapz(x, x)) == pytest.approx(0.5, abs=1e-4)
    assert float(np.trapezoid(x, x)) == pytest.approx(0.5, abs=1e-4)


# ---------------------------------------------------------------------------
# the call sites that were dead
# ---------------------------------------------------------------------------


def test_forster_overlap_integral_runs():
    """R0 from spectra — an AttributeError here made every dye lookup fail."""
    from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra

    wl = np.arange(400.0, 801.0, 1.0)
    donor = np.exp(-0.5 * ((wl - 570.0) / 20.0) ** 2)
    acceptor = np.exp(-0.5 * ((wl - 645.0) / 20.0) ** 2) * 150000.0
    r0, overlap = forster_radius_from_spectra(wl, donor, acceptor, donor_quantum_yield=0.8)
    assert overlap > 0 and 20.0 < r0 < 150.0


def test_dimensionality_transfer_efficiency_runs():
    """Fractal-dimension FRET transfer efficiency — the second dead call site.

    Was the phasor transform until that module was deleted (the photon library's
    ``DecayPhasor`` computes the same coordinates, and to the definition rather
    than to a trapezoid); this is the surviving ``np.trapz`` in the same package.
    """
    from chisurf.core.fluorescence.fret.acceptor_density import transfer_efficiency

    values = [transfer_efficiency(1.0, d) for d in (3, 2, 1)]
    assert all(np.isfinite(v) and 0.0 < v < 1.0 for v in values)
    # more directions to approach from -> more efficient transfer at C = C0
    assert values[0] > values[1] > values[2]


def test_lightpath_spectral_propagation_runs():
    """The optical path's overlap integrals — the third dead call site."""
    from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import (
        WAVELENGTHS,
        calculate_r0,
    )

    donor = np.exp(-0.5 * ((WAVELENGTHS - 570.0) / 20.0) ** 2)
    acceptor = np.exp(-0.5 * ((WAVELENGTHS - 645.0) / 20.0) ** 2)
    r0 = calculate_r0(donor, 0.8, acceptor, 150000.0)
    assert np.isfinite(r0) and r0 > 0
