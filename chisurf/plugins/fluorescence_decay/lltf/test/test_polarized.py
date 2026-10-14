"""LLTF's joint VV/VH fit: known lifetimes, rotations, r0 and calibration come back.

Decays are Poisson samples of ChiSurf's own forward model
(:func:`chisurf.core.fluorescence.decay.synthetic_aniso_decay`) with the plugin's
example IRF (6100 channels of 8 ps), 2e6 photons over both channels.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.plugins.fluorescence_decay.lltf.core import polarized as P
from chisurf.plugins.fluorescence_decay.lltf.core.cli import cli
from chisurf.plugins.fluorescence_decay.lltf.core.settings import merged_settings

EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / "example"
IRF = np.loadtxt(EXAMPLE / "IRF_D0.dat")[:, 1]
DT = 0.008


def _fit(lifetimes, amplitudes, rotations, g, l1, l2, seed, n, m, r_inf=False, fit_g=None):
    data = P.simulate_vv_vh(IRF, DT, lifetimes, amplitudes, rotations, g, l1, l2, 2e6, seed)
    pd = P.PolarizedDecay(
        data.time, data.vv, data.vh, IRF, IRF, g if fit_g is None else fit_g, l1, l2
    )
    settings = merged_settings()
    pd.setup(settings)
    return pd.fit(n, m, r_inf, settings=settings)


# ── recovery ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_two_lifetimes_one_rotation_are_recovered(seed):
    """The demo: 1 + 4 ns (0.3, 0.7), rho 1.5 ns, r0 0.35, G 1.2."""
    r = _fit([1.0, 4.0], [0.3, 0.7], [(0.35, 1.5)], 1.2, 0.0, 0.0, seed, 2, 1)
    (x_long, tau_long), (x_short, tau_short) = [
        (c["amplitude"], c["lifetime"]) for c in r["lifetimes"]
    ]
    assert tau_long == pytest.approx(4.0, abs=0.05)
    assert tau_short == pytest.approx(1.0, abs=0.06)
    assert x_short == pytest.approx(0.3, abs=0.02)
    assert r["rotations"][0]["rho"] == pytest.approx(1.5, abs=0.06)
    assert r["r0"] == pytest.approx(0.35, abs=0.01)
    assert r["reduced_chi_square"] < 1.08
    assert r["reduced_chi_square_vv"] < 1.1 and r["reduced_chi_square_vh"] < 1.1
    assert r["converged"]


def test_a_noise_free_pair_returns_its_truth_exactly():
    """Simulator and fitter are one forward model: the expected counts give r0 = 0.3500.

    Over 30 Poisson seeds r0 averages 0.3503 +- 0.0004 (sd 0.0020); seeds 1-5 happen
    to sit at 0.3518-0.3535.
    """
    from chisurf.core.fluorescence.decay import synthetic_aniso_decay

    vv, vh = synthetic_aniso_decay(
        IRF.size,
        [1.0, 4.0],
        amplitudes=[0.3, 0.7],
        anisotropy_spectrum=[0.35, 1.5],
        g_factor=1.2,
        bin_width=DT,
        irf=IRF,
        normalize=True,
    )
    pd = P.PolarizedDecay(np.arange(IRF.size) * DT, vv * 2e6, vh * 2e6, IRF, IRF, 1.2)
    settings = merged_settings()
    pd.setup(settings)
    r = pd.fit(2, 1, settings=settings)
    assert r["r0"] == pytest.approx(0.35, abs=2e-4)
    assert r["rotations"][0]["rho"] == pytest.approx(1.5, abs=2e-3)
    assert [c["lifetime"] for c in r["lifetimes"]] == pytest.approx([4.0, 1.0], abs=3e-3)


@pytest.mark.parametrize("seed", [1, 2])
def test_schaffer_mixing_and_g_are_applied(seed):
    """G = 0.8, l1 = 0.05, l2 = 0.08: rho 2.0 ns and r0 0.30 come back."""
    r = _fit([4.0], [1.0], [(0.30, 2.0)], 0.8, 0.05, 0.08, seed, 1, 1)
    assert r["lifetimes"][0]["lifetime"] == pytest.approx(4.0, abs=0.02)
    assert r["rotations"][0]["rho"] == pytest.approx(2.0, abs=0.06)
    assert r["r0"] == pytest.approx(0.30, abs=0.01)
    assert r["reduced_chi_square"] < 1.08


def test_a_wrong_g_shows_in_the_fit():
    """Fitting G = 1.2 data with G = 1.0: chi2r 1.40 and rho 2.6 ns instead of 1.5."""
    r = _fit([1.0, 4.0], [0.3, 0.7], [(0.35, 1.5)], 1.2, 0.0, 0.0, 1, 2, 1, fit_g=1.0)
    assert r["reduced_chi_square"] > 1.2
    assert abs(r["rotations"][0]["rho"] - 1.5) > 0.5


def test_two_rotations_are_resolved():
    """0.15 at 0.3 ns and 0.20 at 5 ns."""
    r = _fit([4.0], [1.0], [(0.15, 0.3), (0.20, 5.0)], 1.0, 0.0, 0.0, 1, 1, 2)
    fast, slow = r["rotations"]
    assert fast["rho"] == pytest.approx(0.3, abs=0.08)
    assert slow["rho"] == pytest.approx(5.0, abs=0.4)
    assert fast["b"] == pytest.approx(0.15, abs=0.025)
    assert slow["b"] == pytest.approx(0.20, abs=0.02)


def test_residual_anisotropy():
    """r(t) = 0.25 exp(-t/1.5) + 0.10."""
    r = _fit([4.0], [1.0], [(0.25, 1.5), (0.10, 1e9)], 1.0, 0.0, 0.0, 1, 1, 1, r_inf=True)
    assert r["fit_r_infinity"]
    assert r["r_infinity"] == pytest.approx(0.10, abs=0.01)
    assert r["rotations"][0]["rho"] == pytest.approx(1.5, abs=0.1)
    assert r["r0"] == pytest.approx(0.35, abs=0.01)


def test_the_scan_picks_two_lifetimes(tmp_path):
    decay, irf = P.write_demo(tmp_path)
    r = P.fit_polarized(
        decay,
        irf,
        config={"lifetime_fit_parameter": {"find_optimal": True, "maximum_number_of_lifetimes": 3}},
    )
    assert r["n_lifetimes"] == 2
    assert r["optimal_fitting"]["n_lifetimes_tried"] == [1, 2, 3]
    assert r["optimal_fitting"]["probabilities"][1] > 0.68


# ── calibration and input ─────────────────────────────────────────────────────
def test_calibration_given_over_data_over_settings():
    data = P.PolarizedData(np.arange(3.0), np.ones(3), np.ones(3), {"g_factor": 1.3})
    settings = {"g_factor": 1.0, "l1": 0.01, "l2": 0.02}
    cal = P.calibration(data, settings, {"g_factor": None, "l1": 0.05, "l2": None})
    assert (cal["g_factor"], cal["g_factor_source"]) == (1.3, "data")
    assert (cal["l1"], cal["l1_source"]) == (0.05, "given")
    assert (cal["l2"], cal["l2_source"]) == (0.02, "settings")


def test_every_input_form_reads_the_same_pair(tmp_path):
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fio.vv_vh import write_vv_vh

    pair = P.simulate_vv_vh(IRF, DT, [4.0], None, [(0.3, 2.0)], 1.2, 0.01, 0.02, 1e5, 3)
    write_vv_vh(
        tmp_path / "stacked.txt",
        vv=pair.vv,
        vh=pair.vh,
        g_factor=1.2,
        metadata={"l1": 0.01, "l2": 0.02, "dt": DT},
    )
    np.savetxt(tmp_path / "three.txt", np.column_stack([pair.time, pair.vv, pair.vh]))
    np.savetxt(tmp_path / "vv.txt", np.column_stack([pair.time, pair.vv]))
    np.savetxt(tmp_path / "vh.txt", np.column_stack([pair.time, pair.vh]))
    group = DataCurveGroup([DataCurve(x=pair.time, y=pair.vv), DataCurve(x=pair.time, y=pair.vh)])
    group.meta_data = {"g_factor": 1.2, "l1": 0.01, "l2": 0.02}
    forms = {
        "stacked": P.read_polarized(tmp_path / "stacked.txt"),
        "three": P.read_polarized(tmp_path / "three.txt"),
        "two": P.read_polarized(tmp_path / "vv.txt", tmp_path / "vh.txt"),
        "group": P.from_data_group(group),
    }
    for name, got in forms.items():
        assert np.allclose(got.vv, pair.vv) and np.allclose(got.vh, pair.vh), name
        assert np.allclose(got.time, pair.time), name
    assert forms["stacked"].calibration == {"g_factor": 1.2, "l1": 0.01, "l2": 0.02}
    assert forms["group"].calibration == {"g_factor": 1.2, "l1": 0.01, "l2": 0.02}
    assert forms["three"].calibration == {}
    with pytest.raises(ValueError, match="VH"):
        P.read_polarized(tmp_path / "vv.txt")


def test_the_irf_keeps_its_tail_but_drops_a_noise_pedestal():
    """A zero-baseline IRF keeps its tail; one on a Poisson baseline loses the clipped noise."""
    kept = P.PolarizedDecay._clean_irf(IRF)
    raw = np.clip(IRF - np.median(IRF), 0, None)
    inside = np.nonzero(kept)[0]
    assert kept.sum() == pytest.approx(1.0)
    # 3.6 ns of response kept, 99.88 % of its area (a 1e-3-of-peak cut kept 0.75 ns, 99.75 %)
    assert raw[inside.min() : inside.max() + 1].sum() / raw.sum() > 0.998
    rng = np.random.default_rng(0)
    x = np.arange(800) * 0.05
    noisy = rng.poisson(20000 * np.exp(-0.5 * ((x - 2.0) / 0.12) ** 2) + 4.0).astype(float)
    clean = P.PolarizedDecay._clean_irf(noisy)
    assert np.all(clean[x > 4.0] == 0.0)  # no pedestal beyond the response


# ── surfaces ──────────────────────────────────────────────────────────────────
def test_cli_round_trip(tmp_path):
    runner = CliRunner()
    out = runner.invoke(cli, ["demo-vvvh", str(tmp_path)])
    assert out.exit_code == 0, out.output
    decay = tmp_path / "lltf_vv_vh_demo.txt"
    result_file = tmp_path / "fit.json"
    out = runner.invoke(
        cli,
        [
            "fit-vvvh",
            str(decay),
            str(EXAMPLE / "IRF_D0.dat"),
            "-n",
            "2",
            "-sp",
            str(tmp_path),
            "-o",
            str(result_file),
        ],
    )
    assert out.exit_code == 0, out.output
    assert "Rotation 1:" in out.output and "g: 1.2 (data)" in out.output
    r = json.loads(result_file.read_text())
    assert r["mode"] == "vv_vh" and r["n_lifetimes"] == 2
    assert r["rotations"][0]["rho"] == pytest.approx(P.DEMO["rho"], abs=0.06)
    assert r["r0"] == pytest.approx(P.DEMO["r0"], abs=0.01)
    assert (tmp_path / "lltf_vv_vh_demo_vvvh_fit.png").is_file()
    # an explicit G wins over the file's and is reported as given
    out = runner.invoke(
        cli,
        [
            "fit-vvvh",
            str(decay),
            str(EXAMPLE / "IRF_D0.dat"),
            "-n",
            "2",
            "-g",
            "1.25",
            "-sp",
            str(tmp_path),
            "-o",
            str(result_file),
        ],
    )
    r = json.loads(result_file.read_text())
    assert r["g_factor"] == 1.25 and r["calibration_source"]["g_factor"] == "given"


def test_agrees_with_chisurfs_own_anisotropy_fit(tmp_path, monkeypatch):
    """The tr_anisotropy demo (tau 4 ns, rho 2 ns, r0 0.38, separate VV/VH IRFs on a 4-count baseline).

    Measured: LLTF 3.999 / 1.997 / 0.3804 (chi2r 0.98), ChiSurf's linked global fit
    3.997 / 2.007 / 0.381 (chi2r 0.98).
    """
    import chisurf
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.demo import DEMO, make_demo, paths
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel

    make_demo(tmp_path)
    p = paths(tmp_path)
    ours = P.fit_polarized(
        p["data_vv"],
        p["irf_vv"],
        vh_decay=p["data_vh"],
        irf_vh=p["irf_vh"],
        config={"lifetime_fit_parameter": {"number_of_lifetimes": 1}},
    )
    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])
    model = NativeAnisotropyModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.load_data()
    vv, _vh, global_fit = model.create_fits()
    global_fit.run()
    theirs = {q.canonical_id: q.value for q in vv.model.parameters_all}
    assert ours["lifetimes"][0]["lifetime"] == pytest.approx(theirs["lifetime.tau.0"], abs=0.03)
    assert ours["rotations"][0]["rho"] == pytest.approx(theirs["rotation.time.0"], abs=0.05)
    assert ours["r0"] == pytest.approx(theirs["anisotropy.r0"], abs=0.005)
    assert ours["reduced_chi_square"] < 1.1 and global_fit.chi2r < 1.1
    assert ours["lifetimes"][0]["lifetime"] == pytest.approx(DEMO["tau_ns"], abs=0.03)
