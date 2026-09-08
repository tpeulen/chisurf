"""Which factors a calibration may write, and that holding one really holds it.

Applying everything is right exactly once — the first time, on a measurement
carrying its own donor-only and acceptor-only populations. After that it is
usually wrong in one way: γ from a measurement's own populations is only as good
as those populations, and someone who determined γ on a reference sample wants
α and δ fitted *around* it rather than replaced.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx
from chisurf.plugins.ndxplorer.calibration_options import CalibrationOptions


def _window(**constants):
    """An ndX stand-in holding three-species burst data."""
    rng = np.random.default_rng(0)
    n = 3000
    kind = rng.choice([0, 1, 2], n, p=[0.25, 0.15, 0.60])
    E = np.where(kind == 2, rng.normal(0.55, 0.08, n), np.where(kind == 0, 0.02, 0.0))
    S = np.where(kind == 0, 0.95, np.where(kind == 1, 0.08, 0.55))
    size = rng.gamma(4.0, 60.0, n)

    class _DataSource:
        def __init__(self):
            self.data = {
                "Number of Photons (green)": np.clip(size * (1 - E) * S, 1, None),
                "Number of Photons (red)": np.clip(size * E * S, 1, None),
                "Number of Photons (yellow)": np.clip(size * (1 - S), 1, None),
            }

    class _Ndx:
        def __init__(self):
            self.data_source = _DataSource()
            self.constants = {
                "gG/gR": 1.0, "alpha": 0.0, "beta": 0.0, "r": 1.0,
                "Bg": 0.0, "Br": 0.0, "By": 0.0, "PhiA": 1.0, "PhiD": 1.0,
                "forster_radius": 52.0, "tauD0": 4.0, **constants,
            }

    return _Ndx()


def _run(ndx, **kwargs):
    return optimize_calibration_from_ndx(
        ndx, n_bootstrap=0, inject_columns=False, recompute=False, **kwargs)


def test_by_default_every_factor_is_written():
    result = _run(_window())
    assert result["ok"]
    assert set(result["applied_factors"]) == {"alpha", "beta", "gamma", "delta", "r0"}
    assert result["held"] == {}


def test_a_held_factor_keeps_the_window_value():
    """The point of the option, and the thing that is easy to get wrong.

    ``auto_calibrate`` refines the calibration *in place*, so a factor to be kept
    has to be remembered before the call — reading it back afterwards returns the
    refined value, and 'held fixed' would silently mean 'applied'.
    """
    ndx = _window(forster_radius=61.0)
    result = _run(ndx, factors=["alpha", "delta"])
    assert set(result["applied_factors"]) == {"alpha", "delta"}
    assert set(result["held"]) == {"beta", "gamma", "r0"}
    assert result["held"]["r0"] == pytest.approx(61.0), "the window's R0 was overwritten"


def test_what_a_held_factor_would_have_been_is_still_reported():
    """Holding one is a decision; the number it was held against justifies it."""
    result = _run(_window(), factors=["alpha"])
    assert "gamma" in result["determined"]
    assert np.isfinite(result["determined"]["gamma"])


def test_holding_everything_changes_nothing():
    ndx = _window()
    before = dict(ndx.constants)
    result = _run(ndx, factors=[])
    assert result["ok"]
    assert result["applied_factors"] == []
    for key, value in before.items():
        assert ndx.constants[key] == pytest.approx(value), key


def test_the_options_map_onto_the_bridge():
    options = CalibrationOptions(donor_lifetime=3.2)
    options.fit_gamma = False
    options.fit_r0 = True
    kwargs = options.as_kwargs()
    assert kwargs["factors"] == ["alpha", "delta", "beta", "r0"]
    assert kwargs["donor_lifetime"] == pytest.approx(3.2)
    # Every key must be one the bridge accepts.
    import inspect

    accepted = set(inspect.signature(optimize_calibration_from_ndx).parameters)
    assert set(kwargs) <= accepted, set(kwargs) - accepted


# ── backgrounds: an input, not a factor ──────────────────────────────────────

def test_a_missing_stored_background_falls_back_to_the_constants():
    """Asking for the measured background must not throw the typed one away.

    A container that never had a background step has nothing to subtract. Zeroing
    the window's own numbers *and* subtracting nothing in their place is strictly
    worse than the setting it replaced.
    """
    ndx = _window(Bg=2.0, Br=3.0, By=4.0)
    result = _run(ndx, background="measurement")
    assert result["ok"]
    assert result["background_per_burst"] == [], "this fixture has no container"
    # The typed values survived into the calibration.
    assert ndx.constants["Bg"] == pytest.approx(2.0)


def test_none_really_means_zero():
    ndx = _window(Bg=2.0, Br=3.0, By=4.0)
    result = _run(ndx, background="none")
    assert result["ok"]
    assert result["background"] == "none"


def test_a_rate_becomes_counts_through_the_burst_duration(tmp_path, monkeypatch):
    """kHz x ms = counts, and the scaling is per burst.

    A 4 ms burst carries four times the background of a 1 ms one; subtracting
    one number from both is wrong in opposite directions.
    """
    from chisurf.plugins.ndxplorer import calibration_bridge as bridge

    durations = np.array([1.0, 2.0, 4.0])
    table = {"Duration (ms)": durations}

    class _Column:
        def __init__(self, name, values=None, strings=None):
            self._name, self._values, self._strings = name, values, strings

        def name(self):
            return self._name

        def numpy(self):
            return np.asarray(self._values, dtype=float)

        def string_at(self, row):
            return self._strings[row]

    class _Store:
        def __init__(self):
            self._cols = [
                _Column("Detector", strings=["green", "red", "yellow"]),
                _Column("Rate", values=[0.5, 1.0, 2.0]),
            ]

        def n_columns(self):
            return len(self._cols)

        def n_rows(self):
            return 3

        def column(self, i):
            return self._cols[i]

    class _Obj:
        name = "background"
        uid = 1

    class _Measurement:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def artifacts(self):
            return [_Obj()]

        def get_store(self, _uid):
            return _Store()

    import chisurf.core.fio.pto as pto

    monkeypatch.setattr(pto.Measurement, "open",
                        staticmethod(lambda *_a, **_k: _Measurement()))

    class _DS:
        provenance = {"container_path": str(tmp_path / "m.pto")}

    class _Ndx:
        data_source = _DS()

    out = bridge.measured_background(_Ndx(), table)
    np.testing.assert_allclose(out["i_dd"], 0.5 * durations)   # green
    np.testing.assert_allclose(out["i_da"], 1.0 * durations)   # red
    np.testing.assert_allclose(out["i_aa"], 2.0 * durations)   # yellow
