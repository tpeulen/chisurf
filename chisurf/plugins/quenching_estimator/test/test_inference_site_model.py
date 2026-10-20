"""The site model reproduces the MalE prototype's ``Site`` bit for bit, then re-pins.

``male_prototype.json`` (``site_lifetimes``) holds ``Site.lifetime`` for every measured row at
each stage's printed parameter set, computed on the prototype's cached tables. The shipped
table (1OMP/72/L 20.12) covers the Atto655 rows of site 72 apo; the full set needs the
prototype cache (``~/dev/quest/prototype/cache``), checked by sha256, and is slow.

The prototype read the contacts between two tested contact offsets linearly; the analysis
declares the cubic B-spline (``delta_interpolation: bspline``, smooth at the offsets), so the
reproduction tests declare ``linear`` (``PROTOTYPE``). On today's geometry (re-pinned site
tables, see ``test_inference_site_table.py``) with the declared settings the same parameter
sets give the ``REPIN`` numbers. They do not fit as well: the prototype's contact
offset delta absorbed the old frame's registration error, so WP4 refits on the corrected
geometry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import site_model as sm
from chisurf.plugins.quenching_estimator.core.inference import site_table as st

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "baselines" / "male_prototype.json"
SHIPPED = HERE / "data" / "male_site_1omp72_L20.12.npz"
PROTOTYPE_CACHE = Path.home() / "dev" / "quest" / "prototype" / "cache"

#: The prototype's site model: the declared settings with its linear delta interpolation.
PROTOTYPE = {**st.settings(), "delta_interpolation": "linear", "rate_model": "contact_shell"}
#: Today's contact-shell model (the B-spline delta): the stored parameter sets need delta.
SHELL = {**st.settings(), "rate_model": "contact_shell"}

#: Today's geometry, the printed stage parameters, the declared bspline delta interpolation:
#: Site.lifetime of the APO 72 / L 20.12 rows (linear, before 2026-10-20 evening: 3.46629,
#: 3.59844, 2.20740).
REPIN_APO72 = {
    ("Atto655 in D2O", "D2O"): (3.384481773743211, 0.0031199602638887214, 0.61680883579832),
    ("Atto655 in D2O and H2O", "D2O"): (3.589296153828212, 0.0013942334897742992,
                                        0.6508147752891014),
    ("Atto655 in D2O and H2O", "H2O"): (2.2035139334554157, 0.0013984184220964258,
                                        0.6508146451392677),
}
#: Per stage (rms, median |dev|, mean dark fraction) on today's geometry; the prototype's (old
#: tables) and today's with linear delta in comments. The printed parameters are not today's
#: optimum (the refit's are): these pin the arithmetic, not a fit quality.
REPIN_STAGES = {
    "AF488 in H2O": (0.7827923008896187, 0.44064703454729415, 0.1361911012219956),
    # prototype 0.616 0.047 0.129; linear 0.649 0.165 0.139
    "Cy3B in H2O": (0.703919732137106, 0.3331729968044752, 0.004480574608173316),
    # prototype 0.023 0.010 0.004; linear 0.255 0.205 0.005
    "Atto655 in D2O": (0.9284980191106449, 0.24774321809363142, 0.003969583008921313),
    # prototype 0.633 0.061 0.003; linear 0.853 0.242 0.004
    "Atto655 in D2O and H2O": (0.8044352427766295, 0.22248587428158317, 0.003704652289038114),
    # prototype 0.523 0.094 0.002; linear 0.791 0.225 0.004
}
#: Stage C, site 72 apo, Atto655 D2O: exposure over the visible time / reachable positions.
REPIN_EXPOSURE_72 = (0.6508147752891011, 0.9643838733269777, 0.0013942334897742992)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def shipped():
    return sm.Site(SHIPPED, PROTOTYPE)


def _rows(golden, state="APO", site=72, linker=20.12):
    for stage, v in golden["site_lifetimes"].items():
        if stage == "note":
            continue
        for row in v["rows"]:
            if (row["state"], row["site"], row["linker_length"]) == (state, site, linker):
                yield stage, v["theta"], row


def test_the_shipped_table_gives_the_golden_rows_exactly(golden, shipped):
    rows = list(_rows(golden))
    assert len(rows) == 3
    for _, theta, row in rows:
        out = shipped.lifetime(theta, row["tau0"], row["water"])
        assert out == (row["lifetime"], row["dark_fraction"], row["visible_exposure"])


def test_unique_rows_and_the_time_weighted_exposure(golden, shipped):
    ref = golden["time_weighted_exposure_stage_c"]["72"]
    assert len(shipped.count) == ref["unique_rows"]
    assert shipped.n_positions == ref["positions"]
    theta = golden["site_lifetimes"]["Atto655 in D2O and H2O"]["theta"]
    e = shipped.exposure_profile(theta, golden["TAU0"]["Atto655 D2O"])
    assert e["visible"] == ref["visible_time_weighted_e"]
    assert e["reachable"] == ref["reachable_count_weighted_e"]
    assert e["dark_fraction"] == ref["dark_fraction"]
    assert abs(e["weight"].sum() - 1.0) < 1e-12


def test_model_limits(shipped):
    theta = {
        **{f"ln_s_{g}": 0.0 for g in shipped.groups},
        "ln_scale": np.log(1e-12), "delta": 0.0, "lam": 0.0, "ln_static": np.log(1e-12),
        "delta_static": 0.0, "kq": [3.5, 2.0, 1.67, 1.0, 2.0],
    }
    # no stickiness: every position by its count; no quenching: the free dye
    assert np.allclose(shipped.weights(theta), shipped.count / shipped.count.sum())
    tau, dark, _ = shipped.lifetime(theta, 4.0)
    assert abs(tau - 4.0) < 1e-6 and dark < 1e-6
    # water quenches in proportion to exposure; shielding lengthens where buried
    assert shipped.lifetime(theta, 4.0, water=0.3)[0] < tau
    assert shipped.lifetime({**theta, "dtau_shield": 1.0}, 4.0)[0] > tau
    # stickier aromatic neighbourhood -> more quenching (aromatics are quenchers)
    quenched = {**theta, "ln_scale": 0.0}
    sticky = {**quenched, "ln_s_aromatic": np.log(0.1)}
    assert shipped.lifetime(sticky, 4.0)[0] < shipped.lifetime(quenched, 4.0)[0]


def test_todays_geometry_is_pinned(golden, tmp_path):
    lib = sm.SiteLibrary(cache_dir=tmp_path, settings_=SHELL)
    site = lib.site("APO", 72, 20.12)
    assert lib.site("APO", 72, 20.12) is site
    for stage, theta, row in _rows(golden):
        out = site.lifetime(theta, row["tau0"], row["water"])
        assert np.allclose(out, REPIN_APO72[(stage, row["solvent"])], rtol=0, atol=1e-12)
    theta = golden["site_lifetimes"]["Atto655 in D2O and H2O"]["theta"]
    e = site.exposure_profile(theta, golden["TAU0"]["Atto655 D2O"])
    assert np.allclose((e["visible"], e["reachable"], e["dark_fraction"]), REPIN_EXPOSURE_72,
                       rtol=0, atol=1e-12)
    # points and predict: one Site per (state, site, linker), water per row
    rows = [dict(dye="Atto655", state="APO", site=72)] * 2
    points = lib.points(rows, water=[0.0, golden["KQW_FREE"]])
    pred = sm.predict(points, theta, golden["TAU0"]["Atto655 D2O"])
    assert pred.shape == (2,) and pred[1] < pred[0]


def test_declared_tables_carry_resolvable_terms():
    table = sm.predictions_table([dict(
        dye="Atto655", solvent="D2O", state="APO", site=72, linker_length=20.12, water=0.0,
        tau0=3.69, lifetime=3.47, dark_fraction=0.003, visible_exposure=0.62)])
    assert table["site"][0] == 72 and table.dtype.names[-1] == "visible_exposure"
    assert sm.exposure_table([dict(site=72, state="APO", reachable=0.96, visible=0.65,
                                   dark_fraction=0.001)]).size == 1
    with pytest.raises(KeyError):
        sm.predictions_table([dict(dye="x")])
    mmfdb = pytest.importorskip("mmfdb.schema.pdbx_metadata")
    dictionary = mmfdb.MmcifDictionary.load_bundled()
    from chisurf.plugins.quenching_estimator.core.inference import columns

    for name in ("site_predictions", "site_exposure"):
        for entry in columns.columns(name, st.SITE_MODEL):
            assert dictionary.get_item(entry["term"]) is not None, entry["term"]


def _prototype_tables(golden):
    if not PROTOTYPE_CACHE.is_dir():
        pytest.skip(f"{PROTOTYPE_CACHE} is not on this machine")
    out = {}
    for key, entry in golden["site_tables"].items():
        path = PROTOTYPE_CACHE / entry["file"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            pytest.skip(f"prototype cache file {path.name} missing or changed")
        out[key] = path
    return out


@pytest.mark.slow
def test_every_golden_row_on_the_prototype_tables(golden):
    paths = _prototype_tables(golden)
    sites = {}
    for stage, v in golden["site_lifetimes"].items():
        if stage == "note":
            continue
        for row in v["rows"]:
            key = f"{row['state']} {row['site']} {row['linker_length']}"
            if key not in sites:
                sites[key] = sm.Site(paths[key], PROTOTYPE)
            out = sites[key].lifetime(v["theta"], row["tau0"], row["water"])
            assert out == (row["lifetime"], row["dark_fraction"], row["visible_exposure"]), (
                stage, key)


@pytest.mark.slow
def test_every_stage_on_todays_geometry(golden, tmp_path):
    lib = sm.SiteLibrary(cache_dir=tmp_path, settings_=SHELL)
    for stage, v in golden["site_lifetimes"].items():
        if stage == "note":
            continue
        dev, dark = [], []
        for row in v["rows"]:
            out = lib.site(row["state"], row["site"], row["linker_length"]).lifetime(
                v["theta"], row["tau0"], row["water"])
            dev.append(out[0] - row["tauX"])
            dark.append(out[1])
        dev = np.asarray(dev)
        got = (np.sqrt((dev**2).mean()), np.median(np.abs(dev)), np.mean(dark))
        assert np.allclose(got, REPIN_STAGES[stage], rtol=1e-9, atol=0), stage


def test_unique_rows_equals_numpy_unique(shipped):
    table = shipped.table
    n = np.asarray(table.neighbours).astype(float)
    features = np.concatenate([n, np.asarray(table.contacts).astype(np.float32).reshape(len(n), -1),
                               np.asarray(table.exposure, float)[:, None]], 1)
    _, first, count = np.unique(features, axis=0, return_index=True, return_counts=True)
    got_first, got_count = sm.unique_rows(features)
    assert np.array_equal(got_first, first) and np.array_equal(got_count, count)
    # ties, negative zero and an all-equal block
    x = np.array([[0.0, 1.0], [-0.0, 1.0], [0.0, 0.5], [2.0, 0.0], [0.0, 1.0]])
    _, first, count = np.unique(x, axis=0, return_index=True, return_counts=True)
    got = sm.unique_rows(x)
    assert np.array_equal(got[0], first) and np.array_equal(got[1], count)


def test_the_declared_delta_interpolation_is_smooth(golden, shipped):
    """bspline: no kink at the offsets (linear has them), contacts >= 0 and growing with delta."""
    smooth = sm.Site(SHIPPED, SHELL)
    assert smooth.delta_interpolation == "bspline" and shipped.delta_interpolation == "linear"
    theta = golden["site_lifetimes"]["Atto655 in D2O"]["theta"]
    tau0 = golden["TAU0"]["Atto655 D2O"]
    h = 2e-3

    def slopes(site, delta):
        """Second-order one-sided slopes left and right of *delta*."""
        f = {d: site.lifetime({**theta, "delta": delta + d * h}, tau0)[0]
             for d in (-2, -1, 0, 1, 2)}
        return ((3 * f[0] - 4 * f[-1] + f[-2]) / (2 * h),
                (-3 * f[0] + 4 * f[1] - f[2]) / (2 * h))

    for node in (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0):
        left, right = slopes(smooth, node)
        assert abs(left - right) < 1e-2 * max(abs(left), abs(right), 1e-3), (node, left, right)
    left, right = slopes(shipped, -1.0)
    assert abs(right) > 10 * abs(left), (left, right)  # the prototype's kink
    # midway between offsets the two agree closely; at an offset the spline is the 1-4-1 mean
    kq = np.ones(5)
    c = [smooth._contacts(d, 1.0, kq) for d in (-1.0, 0.0, 1.0)]
    lin = [shipped._contacts(d, 1.0, kq) for d in (-1.0, 0.0, 1.0)]
    assert np.allclose(c[1], (lin[0] + 4 * lin[1] + lin[2]) / 6, rtol=1e-5, atol=1e-6)
    grid = np.linspace(-4.0, 5.0, 91)
    total = np.array([smooth._contacts(d, 1.0, kq).astype(float).sum() for d in grid])
    assert np.all(np.diff(total) >= -1e-4 * total.max()) and total.min() >= 0.0
    with pytest.raises(ValueError):
        sm.Site(SHIPPED, {**SHELL, "delta_interpolation": "spline"})


@pytest.fixture(scope="module")
def apo72_v2(tmp_path_factory):
    """Today's APO 72 / L 20.12 table with its quencher distances."""
    return st.site_table(st.male_structure("APO"), 72, 20.12,
                         cache_dir=tmp_path_factory.mktemp("site_tables"))


def _direct_kernel(table, theta, settings_):
    """Rates and the lifetime straight from the sparse histogram, voxel by voxel (no merging)."""
    d = table.distances
    lo, hi = d.edges()
    length, h = float(np.exp(theta["ln_decay_length"])), d.step

    def f(offset):
        a = np.where(np.isfinite(lo), lo, -1e9)
        out = np.empty(len(lo))
        for j in range(len(lo)):
            if j == 0 or hi[j] <= offset:
                out[j] = 1.0
            elif a[j] >= offset:
                out[j] = length * (np.exp(-(a[j] - offset) / length)
                                   - np.exp(-(hi[j] - offset) / length)) / h
            else:
                out[j] = ((offset - a[j]) + length * (1 - np.exp(-(hi[j] - offset) / length))) / h
        return out

    q, src, b = d.columns // (2 * d.n_bins), (d.columns // d.n_bins) % 2, d.columns % d.n_bins
    kq = np.asarray(theta["kq"], float)
    mix = np.where(src == 0, 1 - theta["lam"], theta["lam"])
    n = table.n_voxels
    k = np.bincount(d.rows, d.weights * kq[q] * mix * f(0.0)[b], minlength=n)
    ks = np.bincount(d.rows, d.weights * kq[q] * mix * f(theta["delta_static"])[b], minlength=n)
    residues = st.residue_types(settings_)
    idx = {r: i for i, r in enumerate(residues)}
    nb = np.asarray(table.neighbours, float)
    n_group = np.stack([nb[:, [idx[r] for r in rs]].sum(1) for rs in settings_["groups"].values()], 1)
    log_p = -n_group @ np.array([theta[f"ln_s_{g}"] for g in settings_["groups"]])
    p = np.exp(log_p - log_p.max())
    p /= p.sum()
    e = np.clip(np.asarray(table.exposure, float), 0, 1)
    tau0 = 3.69 + theta.get("dtau_shield", 0.0) * (1 - e)
    tau = 1 / (1 / tau0 + np.exp(theta["ln_scale"]) * k)
    seen = 1 / (1 + (settings_["tau_min"] / tau) ** settings_["visibility_power"])
    seen *= np.exp(-np.exp(theta["ln_static"]) * ks)
    return float((p * seen * tau).sum() / (p * seen).sum())


def test_the_kernel_equals_a_voxel_by_voxel_sum(golden, apo72_v2):
    """Merged rows, the inner/tail split and the one-pass bincounts change nothing."""
    s = st.settings()
    assert s["rate_model"] == "kernel"
    site = sm.Site(apo72_v2)
    assert site.rate_model == "kernel" and site.n_positions == apo72_v2.n_voxels
    assert len(site.count) < apo72_v2.n_voxels / 2
    theta = dict(golden["site_lifetimes"]["Atto655 in D2O"]["theta"])
    for length, scale, static, delta_s in ((0.3, 1.0, 0.001, 0.0), (1.0, 3.0, 2.0, -1.3),
                                           (1.7, 0.2, 20.0, -3.6), (0.8, 1.0, 5.0, 0.4)):
        th = {**theta, "ln_decay_length": np.log(length), "ln_scale": np.log(scale),
              "ln_static": np.log(static), "delta_static": delta_s}
        assert abs(site.lifetime(th, 3.69)[0] - _direct_kernel(apo72_v2, th, s)) < 1e-10


def test_the_kernel_is_smooth_and_the_prototype_tables_refuse_it(golden, apo72_v2):
    site = sm.Site(apo72_v2)
    theta = {**golden["site_lifetimes"]["Atto655 in D2O"]["theta"], "ln_scale": 0.0}
    lengths = np.linspace(0.1, 2.0, 77)
    tau = np.array([site.lifetime({**theta, "ln_decay_length": np.log(v)}, 3.69)[0]
                    for v in lengths])
    assert np.all(np.diff(tau) < 0)                 # a longer range quenches more
    # no kinks: the curvature itself changes smoothly from one step to the next
    second = np.abs(np.diff(tau, 2))
    assert np.abs(np.diff(tau, 3)).max() < 0.3 * second.max()
    # a short decay is the contact shell at delta 0 up to the voxel snapping of the stamps
    shell = sm.Site(apo72_v2, SHELL)
    short = site.lifetime({**theta, "ln_decay_length": np.log(0.1)}, 3.69)[0]
    assert abs(short - shell.lifetime({**theta, "delta": 0.0}, 3.69)[0]) < 0.05
    with pytest.raises(ValueError, match="contact_shell"):
        sm.Site(SHIPPED)
