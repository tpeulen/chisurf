"""The site model reproduces the MalE prototype's ``Site`` bit for bit, then re-pins.

``male_prototype.json`` (``site_lifetimes``) holds ``Site.lifetime`` for every measured row at
each stage's printed parameter set, computed on the prototype's cached tables. The shipped
table (1OMP/72/L 20.12) covers the Atto655 rows of site 72 apo; the full set needs the
prototype cache (``~/dev/quest/prototype/cache``), checked by sha256, and is slow.

On today's geometry (re-pinned site tables, see ``test_inference_site_table.py``) the same
parameter sets give the ``REPIN`` numbers. They do not fit as well: the prototype's contact
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

#: Today's geometry, the printed stage parameters: Site.lifetime of the APO 72 / L 20.12 rows.
REPIN_APO72 = {
    ("Atto655 in D2O", "D2O"): (3.4662850703046475, 0.0031269960272761743, 0.6167809867565738),
    ("Atto655 in D2O and H2O", "D2O"): (3.5984393482767447, 0.0008451658268918694,
                                        0.6507923773506309),
    ("Atto655 in D2O and H2O", "H2O"): (2.2074019448508952, 0.0008492901567700439,
                                        0.6507922461273774),
}
#: Per stage (rms, median |dev|, mean dark fraction) on today's geometry (prototype in comments).
REPIN_STAGES = {
    "AF488 in H2O": (0.6488894007297438, 0.1652777261820506, 0.13885874367591164),  # 0.616 0.047 0.129
    "Cy3B in H2O": (0.2554589983335347, 0.20507447501502352, 0.004889275396244485),  # 0.023 0.010 0.004
    "Atto655 in D2O": (0.8529156147295666, 0.2424830892708194, 0.00438323359882204),  # 0.633 0.061 0.003
    "Atto655 in D2O and H2O": (0.7914413213348841, 0.22474130621324662,
                               0.003965678432727453),  # 0.523 0.094 0.002
}
#: Stage C, site 72 apo, Atto655 D2O: exposure over the visible time / reachable positions.
REPIN_EXPOSURE_72 = (0.650792377350631, 0.9643838733269777, 0.0008451658268918694)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def shipped():
    return sm.Site(SHIPPED)


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
    lib = sm.SiteLibrary(cache_dir=tmp_path)
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
                sites[key] = sm.Site(paths[key])
            out = sites[key].lifetime(v["theta"], row["tau0"], row["water"])
            assert out == (row["lifetime"], row["dark_fraction"], row["visible_exposure"]), (
                stage, key)


@pytest.mark.slow
def test_every_stage_on_todays_geometry(golden, tmp_path):
    lib = sm.SiteLibrary(cache_dir=tmp_path)
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
