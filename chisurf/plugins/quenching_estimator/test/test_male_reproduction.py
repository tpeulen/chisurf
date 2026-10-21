"""The MalE analysis end to end (slow): the stored run's optimum, then today's refit.

(a) **Arithmetic, at the stored optimum.** On the prototype's 54 cached site tables
(``~/dev/quest/prototype/cache``, sha256-checked against ``male_prototype.json``; skipped
when absent) every block is settled at the stored run's printed best fit with its printed
model error (the search's inlier rule then gives the stored outlier counts), and the joint fit
is *polished* from the printed parameters and titration slopes (``Analysis.replay``). Laplace,
leave one out, notes, the naive H2O test and the Laplace scale summaries are then compared with
what the notebook printed. Best fits agree to the printed four decimals or within 0.3 % of each
parameter's range (the start is the printed, rounded point; a flat direction can move), every
interval end likewise, outlier sets exactly, LOO |z| within 0.15. "Other regions possible"
needs the 64 searches and is not compared; "not determined" parameters (Stage B delta_static)
are skipped.

Why not the full search: the robust multistart landscape has narrow basins. With IMP.bff's
L-BFGS-B the 64 random starts of the stored seeds find other optima than the stored run's scipy
searches (Cy3B best log posterior 25.0 vs 32.4 reachable at the stored point; Stage B scale 3.3
vs 0.11; AF488 5.8 with 3 outlier lifetimes vs 6.2 with 4); only Stage C's block lands in the
stored basin (s 0.107 vs 0.108, scale 0.11). So the search is not a reproducible quantity across
optimisers, and the stages declare the stored optimum as an extra start
(``settings/analysis/stages.yaml`` ``starts``).

(b) **Refit on today's geometry** (re-pinned site tables: IMP.bff AV + corrected grid frame,
``test_inference_site_table.py``). The stored parameters do not fit these tables, so the
numbers move; ``REFIT`` pins them (the plan concept and ``okf/log.md`` list them beside the
stored run's). Since WP4c the default rate model is the distance-continuous kernel, so the
pins are the full preset's kernel refit (26 146 s / 7 workers, 2026-10-21).

Both are ``slow``: (a) about 4 minutes, (b) about 3.3 hours on 7 worker processes (the serial
MINPACK joint fit of the 41-parameter graph alone is 1.5 h).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import graph_fit as gf
from chisurf.plugins.quenching_estimator.core.inference import site_table as site_table
from chisurf.plugins.quenching_estimator.core.inference import stages as st

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "baselines" / "male_prototype.json"
PROTOTYPE_CACHE = Path.home() / "dev" / "quest" / "prototype" / "cache"

#: stored-run label of each (stage, block) of this port
VIEWS = {
    "AF488 in H2O": ("A", "AF488 in H2O"),
    "Cy3B in H2O": ("A", "Cy3B in H2O"),
    "Atto655 in D2O": ("B", "Atto655 in D2O"),
    "Atto655 in D2O and H2O": ("C", "Atto655 in D2O and H2O"),
}

#: search outlier lifetimes and model errors (cell 33/45 text; the error is given, the count
#: follows from the inlier rule)
SEARCH = {"AF488 in H2O": (4, 0.050), "Cy3B in H2O": (0, 0.050),
          "Atto655 in D2O and H2O": (3, 0.108), "Atto655 in D2O": (2, 0.065)}
#: rms, median |dev| as printed
STATS = {"AF488 in H2O": (0.62, 0.047), "Cy3B in H2O": (0.02, 0.010),
         "Atto655 in D2O and H2O": (0.52, 0.094), "Atto655 in D2O": (0.63, 0.061)}
OUTLIERS = {"AF488 in H2O": [92, 219, 233], "Cy3B in H2O": [],
            "Atto655 in D2O and H2O": [322], "Atto655 in D2O": [211, 219, 322]}
#: Laplace scale summary (median, 16 %, 84 %, factor) as printed (cells 39, 46, 55)
LAPLACE = {"AF488 in H2O": ("6.1", "4.6", "8.1", "1.8"),
           "Atto655 in D2O": ("0.11", "0.08", "0.15", "1.9"),
           "Atto655 in D2O and H2O": ("0.11", "0.08", "0.15", "1.9")}


def _close(mine, printed, spec):
    """Agreement to the printed precision or within 0.3 % of the parameter's range."""
    if round(mine, 4) == printed:
        return True
    f = np.log if spec.log else (lambda x: x)
    if spec.log and (mine <= 0 or printed <= 0):
        return False
    return abs(f(mine) - f(printed)) <= 0.003 * (spec.upper - spec.lower)


def printed_mismatches(summary, golden):
    """Every printed number of the stored run the result does not give.

    Parameters
    ----------
    summary : dict
        ``AnalysisResult.to_dict()``.
    golden : dict
        ``male_prototype.json``.

    Returns
    -------
    list of str
    """
    specs = {p.label: p for p in gf.parameter_specs()}
    bad = []
    printed = golden["printed"]
    for label, (stage, block) in VIEWS.items():
        numbers = summary["stages"][stage]["numbers"]["blocks"][block]
        est = numbers["estimates"]
        for row in printed["estimates"][label]:
            mine = est[row["parameter"]]
            note = row["note"].replace("; other regions possible", "").replace(
                "other regions possible", "")
            if note.startswith("not determined") or row["parameter"] == "model_error":
                continue
            if row["note"].startswith("fixed"):
                ok = all(round(mine[k], 4) == row[f] for k, f in
                         (("value", "value"), ("low", "low_68"), ("high", "high_68")))
            else:
                ok = all(_close(mine[k], row[f], specs[row["parameter"]]) for k, f in
                         (("value", "value"), ("low", "low_68"), ("high", "high_68")))
            if not ok:
                bad.append(f"{label} {row['parameter']}: {mine} vs {row}")
            if mine["note"] != note:
                bad.append(f"{label} {row['parameter']} note: {mine['note']!r} vs {note!r}")
        n_out, s = SEARCH[label]
        if numbers["stats"]["n_outlier_lifetimes"] != n_out:
            bad.append(f"{label} search outliers {numbers['stats']['n_outlier_lifetimes']} vs "
                       f"{n_out}")
        rms, med = STATS[label]
        if abs(numbers["stats"]["rms"] - rms) > 0.01 or \
                abs(numbers["stats"]["median_abs_dev"] - med) > 0.002:
            bad.append(f"{label} rms/median {numbers['stats']['rms']:.4f}/"
                       f"{numbers['stats']['median_abs_dev']:.4f} vs {rms}/{med}")
        if numbers["stats"]["outliers"] != OUTLIERS[label]:
            bad.append(f"{label} outliers {numbers['stats']['outliers']} vs {OUTLIERS[label]}")
        worst = {str(s): z for s, z in numbers["worst"]}
        ref = printed["loo"][label]
        if set(worst) != set(ref) or any(abs(worst[k] - ref[k]) > 0.15 for k in ref):
            bad.append(f"{label} LOO {worst} vs {ref}")
        if numbers["worst"][0][0] != int(next(iter(ref))):
            bad.append(f"{label} worst LOO site {numbers['worst'][0][0]} vs {next(iter(ref))}")
        if label in LAPLACE:
            lap = numbers["scale_laplace"]
            got = np.array([lap["median"], lap["low"], lap["high"]])
            want = np.array([float(v) for v in LAPLACE[label][:3]])
            if np.any(np.abs(np.log(got / want)) > 0.05):     # printed to two digits
                bad.append(f"{label} Laplace scale {got} vs {want}")
    slopes = {(r["dye"], r["amino_acid"]): r
              for r in summary["stages"]["A"]["tables"]["titration_slopes"]}
    for row in printed["k_graph"]:
        mine = slopes[(row["dye"], row["amino_acid"])]
        for field, key in (("K_graph", "ksv_graph"), ("low_68", "low_68"), ("high_68", "high_68")):
            if abs(mine[key] - row[field]) > 0.002:
                bad.append(f"K {row['dye']} {row['amino_acid']} {field}: {mine[key]:.5f} vs "
                           f"{row[field]}")
    naive = summary["stages"]["naive_h2o"]["numbers"]
    if (round(naive["median_abs_dev"], 2), naive["sites_above_free_tau0"]) != (0.48, 16):
        bad.append(f"naive {naive['median_abs_dev']:.4f}, {naive['sites_above_free_tau0']}")
    return bad


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


def _prototype_library(golden):
    if not PROTOTYPE_CACHE.is_dir():
        pytest.skip(f"{PROTOTYPE_CACHE} is not on this machine")
    files = {}
    for key, entry in golden["site_tables"].items():
        path = PROTOTYPE_CACHE / entry["file"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            pytest.skip(f"prototype cache file {path.name} missing or changed")
        state, site, linker = key.split()
        files[(state, int(site), float(linker))] = path
    # the prototype's contact-shell rate model, its contacts read linearly between offsets
    return st.TableFiles(files, {**site_table.settings(), "delta_interpolation": "linear",
                                 "rate_model": "contact_shell"})


def prototype_fit_overrides(golden):
    """The declared parameters with the stored run's bounds (``about.bounds`` of the golden).

    Interval ends, notes and the Laplace clip are relative to a parameter's range, so the
    stored optimum is compared within the stored run's ranges, not today's wider ones.
    """
    bounds = golden["about"]["bounds"]
    params = []
    for p in gf.settings()["parameters"]:
        log = p["scale"] == "log"
        name = f"ln_{p['name']}" if log else p["name"]
        if name not in bounds["lower"]:      # not a parameter of the prototype (decay_length)
            params.append(p)
            continue
        lo, hi = bounds["lower"][name], bounds["upper"][name]
        params.append({**p, "lower": float(np.exp(lo) if log else lo),
                       "upper": float(np.exp(hi) if log else hi)})
    return {"parameters": params}


@pytest.mark.slow
def test_the_stored_optimum_on_its_own_tables(golden):
    data = st.load_analysis_data(library=_prototype_library(golden))
    a = st.Analysis(data, profile=False, fit_overrides=prototype_fit_overrides(golden))
    slopes = {(r["dye"], r["amino_acid"]): r["K_graph"] for r in golden["printed"]["k_graph"]}
    for name in ("joint", "heavy_water"):
        values = {}
        for block in a.declaration["graphs"][name]["blocks"]:
            label = block["label"]
            v = dict(golden["site_lifetimes"][label]["theta"])
            v["model_error"] = [r["value"] for r in golden["printed"]["estimates"][label]
                                if r["parameter"] == "model_error"][0]
            values[label] = v
        a.replay(name, values, slopes)
    summary = a.run("all").to_dict()
    s = summary["graphs"]["joint"]["structure"]
    assert (s["variables"], s["likelihoods"], s["priors"], s["treewidth"]) == (48, 20, 3, 18)
    assert summary["graphs"]["joint"]["n_parameters"] == 41
    assert summary["graphs"]["heavy_water"]["n_parameters"] == 19
    assert printed_mismatches(summary, golden) == []


#: today's geometry, full preset, widened bounds and the B-spline delta (64 random starts + the
#: declared stored-run start): per block quench scale (best, 68 % low, high), model error, outlier
#: sites, worst LOO site — the full preset on the distance-continuous kernel (the default
#: ``rate_model: kernel`` since WP4c). Cy3B and AF488 have interior κ optima (AF488's Laplace
#: point sits in the short-reach basin κ 0.019 / ℓ 0.25; an equal-posterior long-reach basin at
#: κ 0.028 / ℓ 2.0 exists — see the plan concept, item 1e); Atto655 D₂O trades κ for ℓ and γ
#: (ℓ on its 2.0 bound, γ 33); Stage C's κ is at its lower bound with ℓ at 0.1.
#: Contact-shell refit before the kernel (a86b8b45a): AF488 0.015 / δ 4.5, Cy3B 0.086 / δ 1.2,
#: Atto655 B 75 / δ 0.9, Stage C 27 / δ −1.1. Before the widening (scale <= 10, delta -3..2,
#: linear delta): AF488 10.0, Cy3B 0.058, Atto655 B 10.0, C 10.0.
REFIT = {
    "AF488 in H2O": (0.018993707780214936, 0.015774486412262954, 0.02286990053506561,
                     0.12313972015868524, [211, 233], 233),
    "Cy3B in H2O": (0.20156847014563464, 0.11729262282158863, 0.34639730257079204, 0.05,
                    [], 233),
    "Atto655 in D2O": (0.2719287067917118, 0.015717317204356557, 4.704697412158641,
                       0.23431961034596274, [], 322),
    "Atto655 in D2O and H2O": (0.026359098603066483, 0.010000000000000005, 0.09919865546784587,
                               0.15165744019337826, [92, 233, 322], 322),
}


@pytest.mark.slow
def test_the_refit_on_todays_geometry(golden):
    result = st.Analysis(profile=False).run("all")
    for label, (stage, block) in VIEWS.items():
        numbers = result.to_dict()["stages"][stage]["numbers"]["blocks"][block]
        scale = numbers["estimates"]["scale"]
        got = (scale["value"], scale["low"], scale["high"], numbers["model_error"],
               numbers["stats"]["outliers"], numbers["worst"][0][0])
        ref = REFIT[label]
        assert np.allclose(got[:4], ref[:4], rtol=1e-3), (label, got, ref)
        assert got[4:] == ref[4:], (label, got, ref)
