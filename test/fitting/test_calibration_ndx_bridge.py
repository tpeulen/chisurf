"""Tests for mapping/pushing a calibration into ndxplorer constants."""

from __future__ import annotations

import collections.abc

import pytest

from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters,
    calibration_to_ndx_constants,
)
from chisurf.plugins.ndxplorer.calibration_bridge import push_calibration_to_ndx


def _calib():
    c = CalibrationParameters()
    c.gamma, c.alpha, c.delta = 1.6, 0.08, 0.05
    c.bg_dd, c.bg_da, c.bg_aa = 1.0, 0.5, 0.6
    c.phi_a, c.phi_d = 0.4, 0.8
    c.r0 = 55.0
    return c


def test_mapping_matches_ndx_constant_names():
    """The mapping uses ndx's constant names and the effective-gamma inversion."""
    m = calibration_to_ndx_constants(_calib())
    # ndx effective gamma = (PhiA/PhiD)/(gG/gR) must equal calib gamma
    assert m["gG/gR"] == pytest.approx((0.4 / 0.8) / 1.6)
    assert m["alpha"] == pytest.approx(0.08)
    assert m["beta"] == pytest.approx(0.05)      # ndx 'beta' == direct excitation (delta)
    assert m["Bg"] == pytest.approx(1.0) and m["Br"] == pytest.approx(0.5)
    assert m["forster_radius"] == pytest.approx(55.0)
    # round-trip: ndx's effective gamma equals the calibration gamma
    assert (m["PhiA"] / m["PhiD"]) / m["gG/gR"] == pytest.approx(1.6)


class _StubDataSource:
    def __init__(self):
        self.last = None

    def compute_columns(self, constants, equations=None):
        self.last = dict(constants)


class _StubNdx:
    def __init__(self):
        self.constants = {"gG/gR": 0.6, "alpha": 0.015, "beta": 0.005, "tauD0": 4.0}
        self.equations = []
        self.data_source = _StubDataSource()
        self.updated = 0

    def update_plots(self):
        self.updated += 1


def test_push_updates_constants_and_recomputes():
    """Pushing merges the mapping into ndx.constants and recomputes."""
    ndx = _StubNdx()
    mapping = push_calibration_to_ndx(ndx, _calib())
    # merged (existing unrelated keys preserved, mapped keys overwritten)
    assert ndx.constants["tauD0"] == 4.0
    assert ndx.constants["alpha"] == pytest.approx(0.08)
    assert ndx.constants["gG/gR"] == pytest.approx((0.4 / 0.8) / 1.6)
    # recompute happened with the merged constants; plots refreshed
    assert ndx.data_source.last["alpha"] == pytest.approx(0.08)
    assert ndx.updated == 1
    assert mapping["alpha"] == pytest.approx(0.08)


def test_push_without_recompute():
    """recompute=False updates constants but does not recompute/refresh."""
    ndx = _StubNdx()
    push_calibration_to_ndx(ndx, _calib(), recompute=False)
    assert ndx.constants["alpha"] == pytest.approx(0.08)
    assert ndx.data_source.last is None
    assert ndx.updated == 0


class _DataSourceWithData:
    def __init__(self, df):
        self.data = df
        self.computed = 0

    def compute_columns(self, constants=None, equations=None):
        self.computed += 1


class _NdxWithData:
    def __init__(self, df):
        self.constants = {}
        self.equations = []
        self.data_source = _DataSourceWithData(df)
        self.updated = 0

    def update_plots(self):
        self.updated += 1


def _burst_df():
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(0)
    n = 300
    return pd.DataFrame({
        "Number of Photons (green)": rng.integers(20, 400, n),
        "Number of Photons (red)": rng.integers(20, 400, n),
        "Green Count Rate (KHz)": rng.uniform(10, 80, n),
        "Red Count Rate (KHz)": rng.uniform(10, 80, n),
    })


def test_inject_stable_unmixed_columns_no_hardcoded_names():
    """Caller supplies emission + channel columns + labels; no hardcoded names."""
    import numpy as np

    from chisurf.plugins.ndxplorer.calibration_bridge import push_unmixed_columns_to_ndx

    df = _burst_df()
    ndx = _NdxWithData(df)
    emission = np.array([[1.0, 0.08], [0.0, 1.4]])  # donor/acceptor x green/red
    injected = push_unmixed_columns_to_ndx(
        ndx,
        emission=emission,
        channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
        source_labels=["donor", "acceptor"],
        rate_columns=["Green Count Rate (KHz)", "Red Count Rate (KHz)"],
    )
    assert "Number of Photons (donor, unmix)" in df.columns
    assert "Number of Photons (acceptor, unmix)" in df.columns
    assert "donor Count Rate unmix (KHz)" in df.columns
    # non-negative continuous unmix
    assert np.all(df["Number of Photons (donor, unmix)"] >= 0)
    assert ndx.data_source.computed == 1 and ndx.updated == 1
    assert injected  # non-empty


def test_inject_shuffle_preserves_total_counts_and_is_integer():
    import numpy as np

    from chisurf.plugins.ndxplorer.calibration_bridge import push_unmixed_columns_to_ndx

    df = _burst_df()
    ndx = _NdxWithData(df)
    emission = np.array([[1.0, 0.08], [0.0, 1.4]])
    push_unmixed_columns_to_ndx(
        ndx,
        emission=emission,
        channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
        source_labels=["donor", "acceptor"],
        unmix="shuffle",
        seed=1,
    )
    donor = df["Number of Photons (donor, shuffle)"].to_numpy()
    acceptor = df["Number of Photons (acceptor, shuffle)"].to_numpy()
    raw_total = (df["Number of Photons (green)"] + df["Number of Photons (red)"]).to_numpy()
    # integer + exact photon-count preservation per burst
    assert np.array_equal(donor + acceptor, raw_total)
    assert np.allclose(donor, np.rint(donor))


def test_inject_returns_empty_when_columns_absent():
    import numpy as np
    import pandas as pd

    from chisurf.plugins.ndxplorer.calibration_bridge import push_unmixed_columns_to_ndx

    ndx = _NdxWithData(pd.DataFrame({"something else": [1, 2, 3]}))
    out = push_unmixed_columns_to_ndx(
        ndx,
        emission=np.array([[1.0, 0.08], [0.0, 1.4]]),
        channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
        source_labels=["donor", "acceptor"],
    )
    assert out == {}


# ---------------------------------------------------------------------------
# optimizing the constants against the data the window has loaded
# ---------------------------------------------------------------------------


GAMMA, ALPHA, BETA, DELTA = 0.65, 0.08, 1.4, 0.06
TAU_D0 = 4.0


def _simulated_burst_columns(seed: int = 2):
    """ndXplorer-named burst columns with known correction factors."""
    import numpy as np

    from chisurf.core.fluorescence.fret.lines import static_fret_line

    line = static_fret_line(TAU_D0, r0=52.0, sigma=6.0)
    rng = np.random.default_rng(seed)
    dd, da, aa, tau = [], [], [], []
    for efficiency, n in ((0.3, 900), (0.75, 900)):
        photons = rng.poisson(400, n).astype(float)
        dd.append(rng.poisson((1 - efficiency) * photons))
        aa.append(rng.poisson(BETA * GAMMA * photons))
        da.append(rng.poisson(GAMMA * efficiency * photons
                              + ALPHA * (1 - efficiency) * photons
                              + DELTA * BETA * GAMMA * photons))
        tau.append(rng.normal(float(line.lifetime_at(efficiency)), 0.12, n))
    photons = rng.poisson(400, 300).astype(float)          # donor-only
    dd.append(rng.poisson(photons))
    da.append(rng.poisson(ALPHA * photons))
    aa.append(rng.poisson(2.0, 300))
    tau.append(rng.normal(TAU_D0, 0.12, 300))
    photons = rng.poisson(400, 300).astype(float)          # acceptor-only
    dd.append(rng.poisson(2.0, 300))
    aa.append(rng.poisson(BETA * GAMMA * photons))
    da.append(rng.poisson(DELTA * BETA * GAMMA * photons))
    tau.append(np.full(300, np.nan))
    return {
        "Green Count Rate (KHz)": np.concatenate(dd).astype(float),
        "Red Count Rate (KHz)": np.concatenate(da).astype(float),
        "S delayed yellow (kHz)": np.concatenate(aa).astype(float),
        "Tau (green)": np.concatenate(tau),
    }


class _LoadedNdx(_StubNdx):
    """A stub window that has burst data loaded, as after opening a file."""

    def __init__(self):
        super().__init__()
        self.constants.update({"PhiA": 0.32, "PhiD": 0.8, "forster_radius": 52.0,
                               "Bg": 0.0, "Br": 0.0, "By": 0.0, "r": 1.0})
        self.data_source.data = _simulated_burst_columns()


def test_optimize_recovers_the_factors_from_the_loaded_data():
    """The constants ndx applies are optimized against the bursts it has open."""
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    ndx = _LoadedNdx()
    before_gg_gr = ndx.constants["gG/gR"]
    result = optimize_calibration_from_ndx(ndx, n_bootstrap=0)

    assert result["ok"], result.get("error")
    assert result["factors"]["gamma"] == pytest.approx(GAMMA, rel=0.05)
    assert result["factors"]["alpha"] == pytest.approx(ALPHA, abs=0.006)
    assert result["factors"]["delta"] == pytest.approx(DELTA, abs=0.006)
    assert result["factors"]["beta"] == pytest.approx(BETA, rel=0.05)
    # written into the window with ndx's own naming, and recomputed
    assert ndx.constants["gG/gR"] != before_gg_gr
    assert (ndx.constants["PhiA"] / ndx.constants["PhiD"]) / ndx.constants["gG/gR"] == \
        pytest.approx(result["factors"]["gamma"])
    assert ndx.constants["beta"] == pytest.approx(result["factors"]["delta"])
    assert ndx.constants["r"] == pytest.approx(1.0 / result["factors"]["beta"])
    assert ndx.updated == 1
    assert result["before"]["gG/gR"] == pytest.approx(before_gg_gr)
    # the columns were recognised by their ndx names
    assert result["columns"]["i_dd"] == "Green Count Rate (KHz)"
    assert result["columns"]["tau_f"] == "Tau (green)"


def test_optimize_starts_from_the_windows_own_settings():
    """Settings the data cannot improve are taken from the window, not defaults."""
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    ndx = _LoadedNdx()
    ndx.constants.update({"forster_radius": 60.0, "PhiA": 0.5, "PhiD": 0.9, "Bg": 1.5})
    result = optimize_calibration_from_ndx(ndx, n_bootstrap=0)
    assert result["ok"]
    assert ndx.constants["forster_radius"] == pytest.approx(60.0)
    assert ndx.constants["PhiA"] == pytest.approx(0.5)
    assert ndx.constants["Bg"] == pytest.approx(1.5)


def test_optimize_injects_accurate_columns():
    """Accurate per-burst columns are added; ndx's own columns stay untouched.

    ndx's native efficiency equation has no direct-excitation term, so pushing
    the constants alone cannot make its ``FRET efficiency`` column accurate.
    """
    import numpy as np

    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    ndx = _LoadedNdx()
    original = set(ndx.data_source.data)
    result = optimize_calibration_from_ndx(ndx, n_bootstrap=0)

    assert "FRET efficiency (accurate)" in result["injected"]
    assert "Stoichiometry (accurate)" in result["injected"]
    assert "Off static FRET line" in result["injected"]
    assert original <= set(ndx.data_source.data)          # nothing overwritten
    fret = ndx.data_source.data["Population"] >= 0
    e = ndx.data_source.data["FRET efficiency (accurate)"][fret]
    assert 0.2 < float(np.mean(e)) < 0.8
    # the two simulated populations come back at their true efficiencies
    populations = sorted(p["E"] for p in result["populations"])
    assert populations[0] == pytest.approx(0.3, abs=0.02)
    assert populations[1] == pytest.approx(0.75, abs=0.02)


def test_optimize_reports_unusable_data():
    """A window without recognisable channels reports why, without raising."""
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    ndx = _StubNdx()
    ndx.data_source.data = {"foo": [1.0, 2.0], "bar": [3.0, 4.0]}
    result = optimize_calibration_from_ndx(ndx)
    assert not result["ok"] and "i_dd" in result["error"]


# ---------------------------------------------------------------------------
# the push has to reach the parameter table, and must not replace a live mapping
# ---------------------------------------------------------------------------


class _ConstantsMapping(collections.abc.Mapping):
    """Stand-in for ndx's live mapping over the fitting-parameter group.

    It is a ``Mapping`` with an ``update``, deliberately **not** a ``dict``:
    writing through it is what keeps a constant's crosslink to a fit parameter
    alive.
    """

    def __init__(self, values):
        self._values = dict(values)

    def __getitem__(self, key):
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def update(self, other=None, **kwargs):
        self._values.update(other or {})
        self._values.update(kwargs)


class _ParameterEditor:
    """Stand-in for ndx's constants table."""

    def __init__(self, values):
        self.dict = dict(values)

    def apply_values(self, values):
        self.dict.update({str(k): float(v) for k, v in dict(values).items()})


class _TableBackedNdx(_StubNdx):
    """An ndx whose constants are a live mapping fed by a parameter table."""

    def __init__(self):
        super().__init__()
        defaults = {"gG/gR": 0.6, "alpha": 0.015, "beta": 0.005, "tauD0": 4.0}
        self.parameter_control = _ParameterEditor(defaults)
        self.constants = _ConstantsMapping(defaults)

    def settle(self):
        """What ndx's recompute throttle does on any parameter event.

        ``_schedule_parameter_recompute`` resets ``constants`` from the table,
        so anything the push wrote only into ``constants`` is reverted here.
        """
        self.constants = _ConstantsMapping(self.parameter_control.dict)


def test_push_writes_the_parameter_table_so_it_survives_a_recompute():
    """A calibration must still be in force after ndx's throttle fires.

    Writing only ``ndx.constants`` looked correct right up until the event loop
    turned: ndx re-seeds that mapping from the parameter table, so the pushed
    calibration was silently replaced by the table's defaults and every derived
    column went back to the old numbers.
    """
    ndx = _TableBackedNdx()
    mapping = push_calibration_to_ndx(ndx, _calib())

    assert ndx.parameter_control.dict["alpha"] == pytest.approx(mapping["alpha"])
    assert ndx.parameter_control.dict["gG/gR"] == pytest.approx(mapping["gG/gR"])

    ndx.settle()
    assert ndx.constants["alpha"] == pytest.approx(mapping["alpha"])
    assert ndx.constants["gG/gR"] == pytest.approx(mapping["gG/gR"])
    assert ndx.constants["tauD0"] == 4.0     # unrelated constants survive


def test_push_updates_a_live_mapping_in_place_instead_of_replacing_it():
    """A non-dict ``Mapping`` must be written through, not swapped for a dict.

    ndx's ``ConstantsMapping`` is a view over the fitting-parameter group;
    replacing it with a plain dict severs every Global-View crosslink while
    leaving the numbers looking right.
    """
    ndx = _TableBackedNdx()
    before = ndx.constants
    push_calibration_to_ndx(ndx, _calib())

    assert ndx.constants is before, "the live mapping was replaced"
    assert isinstance(ndx.constants, _ConstantsMapping)
