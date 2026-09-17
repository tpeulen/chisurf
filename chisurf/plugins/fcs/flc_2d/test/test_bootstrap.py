"""Per-molecule 2D-FDC and the molecule bootstrap, against the original and against truth.

``test/data/flc_2d/matlab_bootstrap.npz`` was recorded 2026-09-17 by running the
original ``TK_MyMain_Create2DFDC_cor_SeparateData_BootStrap_v02.m`` in Octave on three
simulated molecules (ticks as seconds, ``tStep = 1``; its random draw replaced by a
given permutation, nothing else changed) for three draws -- both factors 1; group
factor 2; photon factor 0.5 -- plus ``TK_Create1DFDC_01`` and ``TK_Create2DFDC_04`` at
``dT = ddT/2`` on a stream with 427 repeated macro ticks. Every matrix matched bin for
bin. The same run is what exposed the one-bin offset of the linear matrix in
``core.create_2d_fdc_numba_int``.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.fcs.flc_2d import api
from chisurf.plugins.fcs.flc_2d.bootstrap import (
    _axes,
    _pairs,
    bootstrap_order,
    separate_data_2d_fdc,
)
from chisurf.plugins.fcs.flc_2d.fit.helpers import create_1d_fdc

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "flc_2d"
    / "matlab_bootstrap.npz"
)
MATLAB_NAMES = {
    "fdc_1d_lin": "Mat_1DFDC_lin",
    "fdc_1d_log": "Mat_1DFDC_log",
    "short_lin": "Mat_2DFDC_Short_lin",
    "short_log": "Mat_2DFDC_Short_log",
    "short_cor_lin": "Mat_2DFDC_Short_cor_lin",
    "short_cor_log": "Mat_2DFDC_Short_cor_log",
    "lin": "Mat_2DFDC_lin",
    "log": "Mat_2DFDC_log",
    "cor_lin": "Mat_2DFDC_cor_lin",
    "cor_log": "Mat_2DFDC_cor_log",
}


@pytest.fixture(scope="module")
def recorded():
    assert _FIXTURE.is_file(), f"committed fixture is missing: {_FIXTURE}"
    with np.load(_FIXTURE) as z:
        return {k: z[k] for k in z.files}


@pytest.fixture(scope="module")
def separate(recorded):
    r = recorded
    molecules = [
        (r[f"macro_{j}"].astype(np.int64), r[f"micro_{j}"].astype(np.int64)) for j in range(3)
    ]
    return separate_data_2d_fdc(
        molecules,
        r["dT_ticks"],
        int(r["ddT_ticks"]),
        tMin=int(r["tMin"]),
        tMax=int(r["tMax"]),
        t_start=int(r["t_start"]),
        t_end=int(r["t_end"]),
        lint_bin_factor=int(r["lint_bin_factor"]),
        logt_imax=int(r["logt_imax"]),
    )


@pytest.mark.parametrize("case", [1, 2, 3])
def test_the_driver_matches_the_matlab(recorded, separate, case):
    r = recorded
    order, photons = bootstrap_order(
        separate.photon_counts,
        photon_factor=float(r[f"case{case}_P"]),
        group_factor=int(r[f"case{case}_G"]),
        permutation=r[f"case{case}_perm"] - 1,
    )
    np.testing.assert_array_equal(order + 1, r[f"case{case}_IIII_Random"][: order.size])
    assert photons == int(r[f"case{case}_TotalPhotonNum"])
    np.testing.assert_array_equal(
        separate.measurement_times[order], r[f"case{case}_MeasurementTime_s"]
    )
    got = separate.total(order)
    src = 1 if case == 2 else case  # case 2 draws the same molecules as case 1
    for key, name in MATLAB_NAMES.items():
        want = r[f"case{src}_{name}"].astype(float)
        if want.ndim == 3:
            want = np.moveaxis(want, -1, 0)
        np.testing.assert_array_equal(got[key], want, err_msg=f"case {case}: {key}")


def test_same_tick_photons_pair_forward_only_as_in_the_matlab(recorded):
    """Zero lag and dT = ddT/2 on 427 repeated macro ticks."""
    macro = recorded["dup_macro"].astype(np.int64)
    micro = recorded["dup_micro"].astype(np.int64)
    _, lin, _, log = create_1d_fdc(
        macro, micro, tMin_ticks=100, tMax_ticks=400, lint_bin_factor=20, logt_imax=12
    )
    np.testing.assert_array_equal(lin, recorded["dup_1d_lin"])
    np.testing.assert_array_equal(log, recorded["dup_1d_log"])
    axes = _axes(100, 400, 20, 12)
    mat_lin, mat_log = _pairs(
        macro, micro, 4, 8, 0, int(macro[-1]), 100, 400, axes, True, 1, forward_only=True
    )
    keep = slice(1, axes[0] // axes[1])
    np.testing.assert_array_equal(mat_lin[keep, keep], recorded["dup_short_lin"])
    np.testing.assert_array_equal(mat_log, recorded["dup_short_log"])


def test_both_factors_one_is_the_plain_sum(separate):
    bs = api.bootstrap_2d_fdc(separate, 5, group_factor=1, photon_factor=1.0, seed=0)
    total = separate.total()
    for key, reps in bs.replicates.items():
        assert np.all(bs.std[key] == 0)
        np.testing.assert_array_equal(bs.mean[key], total[key])


def test_a_group_factor_draws_molecules_up_to_that_many_times():
    counts = np.array([100, 300, 200, 400])
    rng = np.random.default_rng(3)
    for _ in range(50):
        order, total = bootstrap_order(counts, group_factor=2, rng=rng)
        assert np.bincount(order, minlength=4).max() <= 2
        assert total >= counts.sum() and total - counts[order[-1]] < counts.sum()


def _molecules(K, n, seed0):
    from chisurf.plugins.fcs.flc_2d.simulate import simulate_photon_stream

    out = []
    for j in range(n):
        s = simulate_photon_stream(
            np.asarray(K, float), (1.0, 3.0), (1e4, 1e4), total_time_s=0.5, seed=seed0 + j
        )
        out.append((s.macro_times, s.micro_times))
    return out


def _exchange_contrast(cor_lin, early):
    """Same-species minus twice the cross-species correlated pairs, at the first lag."""
    c = cor_lin[0]
    e, late = np.flatnonzero(early), np.flatnonzero(~early)
    return c[np.ix_(e, e)].sum() + c[np.ix_(late, late)].sum() - 2 * c[np.ix_(e, late)].sum()


@pytest.mark.parametrize(
    ("K", "exchanging"),
    [([[0, 30], [10, 0]], True), ([[0, 1e-3], [1e-3, 0]], False)],
)
def test_the_bootstrap_error_separates_exchange_from_noise(K, exchanging):
    """The error bar is what decides whether a cross-peak pattern is real.

    Twelve 0.5 s molecules (tau 1 / 3 ns). At a 1 ms lag against the 100 ms
    background, molecules exchanging at 40 s^-1 keep more same-species than
    cross-species pairs; frozen molecules keep neither. Measured 2026-09-17:
    contrast / bootstrap std 8.9 exchanging, 0.07 frozen. Calibration, measured
    once on 16 independent 12-molecule data sets: spread 5570, median bootstrap
    std 4930 (group factor 2).
    """
    sep = api.separate_data_2d_fdc(
        _molecules(K, 12, 100),
        [1000, 100_000],
        1000,
        tMin=0,
        tMax=3000,
        lint_bin_factor=100,
        logt_imax=20,
    )
    bs = api.bootstrap_2d_fdc(sep, 200, seed=1, keys=("cor_lin",))
    early = sep.lin_t < 500  # before 2 ns
    value = _exchange_contrast(sep.total()["cor_lin"], early)
    spread = np.std([_exchange_contrast(r, early) for r in bs.replicates["cor_lin"]], ddof=1)
    z = value / spread
    if exchanging:
        assert z > 5, z
    else:
        assert abs(z) < 2, z


def test_the_cli_writes_the_summed_matrices_and_their_errors(recorded, tmp_path, monkeypatch):
    """``flc-2d bootstrap`` takes one TTTR file per molecule."""
    from click.testing import CliRunner

    from chisurf.plugins.fcs.flc_2d.cli.main import cli

    files = []
    for j in range(3):
        f = tmp_path / f"molecule{j}.ptu"
        f.write_bytes(b"")
        files.append(str(f))

    def fake_load(path, routing_channels=None):
        j = int(path[-5])
        return api.TttrData(
            recorded[f"macro_{j}"].astype(np.int64),
            recorded[f"micro_{j}"].astype(np.int64),
            np.zeros(1),
            1e-6,
            0.004,
            3127,
        )

    monkeypatch.setattr(api, "load_tttr", fake_load)
    out = tmp_path / "boot.npz"
    result = CliRunner().invoke(
        cli,
        [
            "bootstrap",
            *files,
            "--dt",
            "200",
            "--dt",
            "5000",
            "--ddt",
            "100",
            "--tmin",
            "100",
            "--tmax",
            "3000",
            "--lin-factor",
            "50",
            "--log-bins",
            "24",
            "--replicates",
            "20",
            "--seed",
            "4",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    with np.load(out) as z:
        assert z["total_cor_log"].shape == (2, 24, 24)
        assert z["std_cor_log"].shape == (2, 24, 24) and z["std_cor_log"].max() > 0
