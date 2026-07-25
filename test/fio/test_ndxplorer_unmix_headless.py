"""End-to-end **headless** test of the ndxplorer calibration / un-mixing bridge.

Unlike ``test/fitting/test_calibration_ndx_bridge.py`` (which drives a stub ndx),
this exercises ndxplorer's **real** ``DataSource`` evaluation engine and the real
MFD equation/constant files, so it verifies that

* pushing calibration constants actually changes ndx's derived FRET columns, and
* the stable-/shuffle-unmixed columns injected by the bridge are real dataframe
  columns that ndx's own equation engine can compute over.

ndxplorer is an optional in-tree submodule; the test puts it on the path (as the
plugin does at load time) and skips when it is unavailable. It needs no display —
``DataSource.compute_columns`` is pure pandas — but we force the offscreen Qt
platform defensively because importing the ndx core pulls pyqtgraph.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_NDX_MODULE = pathlib.Path(__file__).resolve().parents[2] / "modules" / "ndxplorer"
if _NDX_MODULE.is_dir() and str(_NDX_MODULE) not in sys.path:
    sys.path.insert(0, str(_NDX_MODULE))

pytest.importorskip("ndxplorer.core.data_source", reason="ndxplorer submodule not available")

from ndxplorer.core.data_source import DataSource, _load_equations_file  # noqa: E402

from chisurf.core.fluorescence.fret.calibration import CalibrationParameters  # noqa: E402
from chisurf.plugins.ndxplorer.calibration_bridge import (  # noqa: E402
    push_calibration_to_ndx,
    push_unmixed_columns_to_ndx,
)

_SETTINGS = _NDX_MODULE / "ndxplorer" / "settings"


def _real_equations_and_constants():
    equations = _load_equations_file(str(_SETTINGS / "mfd.equations.yaml"))
    constants = json.load(open(_SETTINGS / "mfd.constants.json"))
    return equations, constants


def _burst_df(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "Green Count Rate (KHz)": rng.uniform(20, 90, n),
        "Red Count Rate (KHz)": rng.uniform(20, 90, n),
        "Number of Photons (green)": rng.integers(30, 400, n),
        "Number of Photons (red)": rng.integers(30, 400, n),
    })


class _RealNdx:
    """Minimal ndx-window shim over the real DataSource + real equations."""

    def __init__(self, df, constants, equations):
        self.data_source = DataSource(data=df)
        self.constants = dict(constants)
        self.equations = equations
        self.updated = 0

    def update_plots(self):
        self.updated += 1


def _calib(gamma):
    c = CalibrationParameters()
    c.gamma, c.alpha, c.delta = gamma, 0.08, 0.05
    c.phi_a, c.phi_d = 0.4, 0.8
    c.r0 = 55.0
    return c


def test_pushed_calibration_changes_real_derived_fret():
    """The real ndx engine recomputes FRET efficiency from the pushed constants."""
    equations, constants = _real_equations_and_constants()

    ndx_lo = _RealNdx(_burst_df(), constants, equations)
    push_calibration_to_ndx(ndx_lo, _calib(gamma=1.2))
    e_lo = float(np.nanmean(ndx_lo.data_source.data["FRET efficiency"]))

    ndx_hi = _RealNdx(_burst_df(), constants, equations)
    push_calibration_to_ndx(ndx_hi, _calib(gamma=2.5))
    e_hi = float(np.nanmean(ndx_hi.data_source.data["FRET efficiency"]))

    # the derived column exists and genuinely depends on the pushed gamma
    assert np.isfinite(e_lo) and np.isfinite(e_hi)
    assert abs(e_lo - e_hi) > 1e-3
    assert ndx_lo.updated == 1


def test_injected_stable_columns_are_computable_by_real_engine():
    """Unmixed columns are real dataframe columns ndx equations can use."""
    equations, constants = _real_equations_and_constants()
    ndx = _RealNdx(_burst_df(), constants, equations)
    emission = np.array([[1.0, 0.08], [0.0, 1.6]])

    push_unmixed_columns_to_ndx(
        ndx,
        emission=emission,
        channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
        source_labels=["donor", "acceptor"],
        rate_columns=["Green Count Rate (KHz)", "Red Count Rate (KHz)"],
        recompute=False,
    )
    df = ndx.data_source.data
    assert "Number of Photons (donor, unmix)" in df.columns
    assert (df["Number of Photons (donor, unmix)"] >= 0).all()

    # add an equation over the injected columns and let the REAL engine compute it
    extra = [{"Proximity ratio (unmix)":
              "'Number of Photons (acceptor, unmix)' / "
              "('Number of Photons (donor, unmix)' + 'Number of Photons (acceptor, unmix)')"}]
    ndx.data_source.compute_columns(constants=ndx.constants, equations=extra)
    pr = ndx.data_source.data["Proximity ratio (unmix)"].to_numpy()
    assert np.all((pr >= -1e-9) & (pr <= 1 + 1e-9))


def test_injected_shuffle_columns_are_integer_and_count_preserving():
    """The shuffle path lands integer, count-preserving columns in the real engine."""
    equations, constants = _real_equations_and_constants()
    df = _burst_df()
    ndx = _RealNdx(df, constants, equations)
    emission = np.array([[1.0, 0.08], [0.0, 1.6]])

    push_unmixed_columns_to_ndx(
        ndx,
        emission=emission,
        channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
        source_labels=["donor", "acceptor"],
        unmix="shuffle", seed=3,
        recompute=False,
    )
    out = ndx.data_source.data
    donor = out["Number of Photons (donor, shuffle)"].to_numpy()
    acceptor = out["Number of Photons (acceptor, shuffle)"].to_numpy()
    raw = (out["Number of Photons (green)"] + out["Number of Photons (red)"]).to_numpy()
    assert np.array_equal(donor + acceptor, raw)        # exact photon-count preservation
    assert np.array_equal(donor, np.rint(donor))         # integer


# ---------------------------------------------------------------------------
# optimizing the constants against the loaded measurement (real engine)
# ---------------------------------------------------------------------------


def _alex_burst_df(seed=3):
    """Build simulated ALEX bursts with known factors, in ndx's column names."""
    from chisurf.core.fluorescence.fret.lines import static_fret_line

    gamma, alpha, beta, delta = 0.65, 0.08, 1.4, 0.06
    line = static_fret_line(4.0, r0=52.0, sigma=6.0)
    rng = np.random.default_rng(seed)
    dd, da, aa, tau = [], [], [], []
    for efficiency, n in ((0.3, 900), (0.75, 900)):
        photons = rng.poisson(400, n).astype(float)
        dd.append(rng.poisson((1 - efficiency) * photons))
        aa.append(rng.poisson(beta * gamma * photons))
        da.append(rng.poisson(gamma * efficiency * photons
                              + alpha * (1 - efficiency) * photons
                              + delta * beta * gamma * photons))
        tau.append(rng.normal(float(line.lifetime_at(efficiency)), 0.12, n))
    photons = rng.poisson(400, 300).astype(float)
    dd.append(rng.poisson(photons))
    da.append(rng.poisson(alpha * photons))
    aa.append(rng.poisson(2.0, 300))
    tau.append(rng.normal(4.0, 0.12, 300))
    photons = rng.poisson(400, 300).astype(float)
    dd.append(rng.poisson(2.0, 300))
    aa.append(rng.poisson(beta * gamma * photons))
    da.append(rng.poisson(delta * beta * gamma * photons))
    tau.append(np.full(300, np.nan))
    return pd.DataFrame({
        "Green Count Rate (KHz)": np.concatenate(dd).astype(float),
        "Red Count Rate (KHz)": np.concatenate(da).astype(float),
        "S delayed yellow (kHz)": np.concatenate(aa).astype(float),
        "Tau (green)": np.concatenate(tau),
    }), {"gamma": gamma, "alpha": alpha, "beta": beta, "delta": delta}


def test_optimize_from_loaded_data_drives_the_real_engine():
    """Calibrating the loaded bursts changes what ndx's own equations compute.

    The end of the workflow the bridge exists for: ndx has data open, the
    constants are optimized against exactly that data, and ndx's derived FRET
    columns follow.
    """
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    equations, constants = _real_equations_and_constants()
    df, truth = _alex_burst_df()
    ndx = _RealNdx(df, constants, equations)
    ndx.data_source.compute_columns(constants=ndx.constants, equations=equations)
    before = float(np.nanmean(ndx.data_source.data["FRET efficiency"]))

    result = optimize_calibration_from_ndx(ndx, n_bootstrap=0)
    assert result["ok"], result.get("error")
    for factor, expected in truth.items():
        assert result["factors"][factor] == pytest.approx(expected, rel=0.06, abs=0.006)

    after = float(np.nanmean(ndx.data_source.data["FRET efficiency"]))
    assert np.isfinite(after) and abs(after - before) > 1e-3
    assert ndx.updated == 1


def test_injected_accurate_columns_are_computable_by_real_engine():
    """The accurate columns are real dataframe columns ndx can compute over."""
    from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

    equations, constants = _real_equations_and_constants()
    df, _ = _alex_burst_df()
    ndx = _RealNdx(df, constants, equations)
    optimize_calibration_from_ndx(ndx, n_bootstrap=0)

    data = ndx.data_source.data
    assert "FRET efficiency (accurate)" in data.columns
    assert "R_DA (accurate)" in data.columns

    extra = [{"1-E (accurate)": "1.0 - 'FRET efficiency (accurate)'"}]
    ndx.data_source.compute_columns(constants=ndx.constants, equations=extra)
    values = ndx.data_source.data["1-E (accurate)"].to_numpy()
    assert np.isfinite(values).any()
