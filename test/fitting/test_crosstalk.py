"""Tests for the general spectral-crosstalk / mixing core and 3-cube rFRET."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.crosstalk import (
    apply_mixing,
    correct_three_cube,
    invert_mixing,
    matrix_from_payload,
    three_cube_fret_efficiency,
)


def _payload(rows, columns, values):
    return {"rows": list(rows), "columns": list(columns), "values": values}


def test_matrix_from_payload_default_order():
    """The matrix reproduces the payload values in payload order."""
    p = _payload(["D", "A"], ["green", "red"], [[0.9, 0.1], [0.05, 0.95]])
    m, rows, cols = matrix_from_payload(p)
    assert rows == ["D", "A"] and cols == ["green", "red"]
    assert np.allclose(m, [[0.9, 0.1], [0.05, 0.95]])


def test_matrix_from_payload_reorder_and_subset():
    """Requesting a label subset/order selects and reorders; missing -> zero."""
    p = _payload(["D", "A"], ["green", "red"], [[0.9, 0.1], [0.05, 0.95]])
    m, rows, cols = matrix_from_payload(p, rows=["A", "D", "X"], columns=["red", "green"])
    assert rows == ["A", "D", "X"] and cols == ["red", "green"]
    assert np.allclose(m[0], [0.95, 0.05])  # A row, red/green
    assert np.allclose(m[1], [0.1, 0.9])    # D row
    assert np.allclose(m[2], [0.0, 0.0])    # missing X -> zeros


def test_mixing_round_trip():
    """invert_mixing recovers the sources produced by apply_mixing."""
    m = np.array([[0.9, 0.1], [0.2, 0.8]])  # 2 sources x 2 detectors, invertible
    sources = np.array([3.0, 5.0])
    measured = apply_mixing(m, sources)
    assert np.allclose(measured, m.T @ sources)
    recovered = invert_mixing(m, measured)
    assert np.allclose(recovered, sources, atol=1e-9)


def test_mixing_round_trip_image_stack():
    """Mixing/unmixing broadcasts over trailing (pixel) axes."""
    m = np.array([[0.85, 0.15], [0.1, 0.9]])
    rng = np.random.default_rng(0)
    sources = rng.uniform(0.1, 1.0, size=(2, 8, 8))
    measured = apply_mixing(m, sources)
    recovered = invert_mixing(m, measured)
    assert recovered.shape == sources.shape
    assert np.allclose(recovered, sources, atol=1e-9)


def test_invert_nonneg_runs_and_is_nonnegative():
    """The nnls path returns a non-negative solution."""
    m = np.array([[0.9, 0.1], [0.2, 0.8]])
    measured = np.array([1.0, -0.2])  # would give a negative unconstrained source
    rec = invert_mixing(m, measured, nonneg=True)
    assert np.all(rec >= 0.0)


@pytest.mark.parametrize("E", [0.1, 0.4, 0.75])
def test_three_cube_recovers_known_efficiency(E):
    """3-cube correction recovers a known E from synthesized IDD/IDA/IAA."""
    d, a, G = 0.12, 0.08, 1.3  # donor leak, direct excitation, gamma
    idd = 1.0 - E
    iaa = 1.0
    fc_true = G * E
    ida = fc_true + d * idd + a * iaa  # forward mix of the FRET channel
    out = correct_three_cube(idd, ida, iaa, donor_leak=d, direct_excitation=a, gamma=G)
    assert np.isclose(out["fc"], fc_true, atol=1e-9)
    assert np.isclose(out["efficiency"], E, atol=1e-9)


def test_three_cube_broadcasts_over_pixels():
    """The correction works element-wise on image arrays."""
    E = np.linspace(0.05, 0.9, 16).reshape(4, 4)
    d, a, G = 0.1, 0.05, 1.0
    idd = 1.0 - E
    iaa = np.ones_like(E)
    ida = G * E + d * idd + a * iaa
    out = correct_three_cube(idd, ida, iaa, donor_leak=d, direct_excitation=a, gamma=G)
    assert out["efficiency"].shape == E.shape
    assert np.allclose(out["efficiency"], E, atol=1e-9)


def test_nusiance_decorator_applies_crosstalk():
    """The (fixed) nusiance decorator runs and applies the crosstalk correction.

    Previously it used the Python-2 ``func_globals`` attribute and raised
    AttributeError at call time.
    """
    from chisurf.core.fluorescence import fret

    # Fg = Sg - Bg = 100; Fr = Sr - Br - Fg*crosstalk = 100 - 10 = 90.
    r = fret.fg_fr(100.0, 100.0, crosstalk=0.1, Bg=0.0, Br=0.0)
    assert np.isclose(r, 100.0 / 90.0)


def test_efficiency_zero_denominator_safe():
    """Zero donor + zero sensitized emission yields 0, not nan."""
    e = three_cube_fret_efficiency(np.array([0.0, 1.0]), np.array([0.0, 1.0]), gamma=1.0)
    assert np.all(np.isfinite(e))
    assert e[0] == 0.0
