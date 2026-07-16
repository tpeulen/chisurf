"""Tests for mapping/pushing a calibration into ndxplorer constants."""

from __future__ import annotations

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
