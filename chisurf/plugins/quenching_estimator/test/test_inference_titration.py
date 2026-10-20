"""Titration statistics reproduce the MalE prototype (chapter 1) from the shipped data.

The golden numbers (``baselines/male_prototype.json``) come from executing the prototype
notebook. The port gives them bit for bit on the platform that wrote the golden file; the
relative tolerance RTOL only absorbs a different LAPACK in ``numpy.polyfit`` on another machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import columns, measurements, titration

GOLDEN = Path(__file__).resolve().parent / "baselines" / "male_prototype.json"
RTOL = 1e-12


@pytest.fixture(scope="module")
def golden():
    """The prototype golden document."""
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def result():
    """Per-day slopes and the posterior of the shipped titrations."""
    data = measurements.load_measurements()
    return titration.analyse_titrations(data.titration_points)


def test_per_day_lines(result, golden):
    per_day, _ = result
    ref = golden["per_day"]
    assert len(per_day) == len(ref) == 30
    assert [(str(r["dye"]), str(r["amino_acid"]), int(r["day"])) for r in per_day] == [
        (r["dye"], r["amino_acid"], r["day"]) for r in ref
    ]
    for field, key in (("ksv", "KSV"), ("ksv_sd", "KSV_err"), ("tau0", "tau0")):
        np.testing.assert_allclose(
            per_day[field], [r[key] for r in ref], rtol=RTOL, atol=0, err_msg=field
        )


def test_k_posterior(result, golden):
    _, post = result
    ref = golden["K_POSTERIOR"]
    table = post.table
    assert [(str(r["dye"]), str(r["amino_acid"])) for r in table] == [
        (r["dye"], r["amino_acid"]) for r in ref
    ]
    assert table["days"].tolist() == [r["days"] for r in ref]
    for field, key in (
        ("tau0", "tau0_ns"),
        ("ksv", "K"),
        ("ksv_sd", "K_sd"),
        ("kq", "kq"),
        ("kq_sd", "kq_sd"),
    ):
        np.testing.assert_allclose(
            table[field], [r[key] for r in ref], rtol=RTOL, atol=0, err_msg=field
        )
    # the plan's printed spot checks
    k = post.k_mean()
    assert k[("AF488", "Trp")] == pytest.approx(14.44, abs=0.005)
    assert k[("AF488", "His")] == pytest.approx(6.23562603290228, rel=RTOL)
    assert k[("Atto655", "Tyr")] == pytest.approx(10.40, abs=0.005)
    assert k[("Cy3B", "Trp")] == pytest.approx(11.10, abs=0.005)
    assert k[("Atto655", "Phe")] < 0  # kept as measured; only kQ takes the positive part


def test_day_to_day_hyper_posterior(result, golden):
    _, post = result
    hyper = golden["hyper"]
    np.testing.assert_allclose(post.day_abs, hyper["DAY_ABS"], rtol=RTOL)
    np.testing.assert_allclose(post.day_rel, hyper["DAY_REL"], rtol=RTOL)
    np.testing.assert_allclose(post.abs_marginal, hyper["abs_marginal"], rtol=RTOL, atol=0)
    np.testing.assert_allclose(post.rel_marginal, hyper["rel_marginal"], rtol=RTOL, atol=0)
    for q, v in hyper["abs_quantiles"].items():
        assert post.quantile("abs", float(q)) == pytest.approx(v, rel=RTOL)
    for q, v in hyper["rel_quantiles"].items():
        assert post.quantile("rel", float(q)) == pytest.approx(v, rel=RTOL)
    assert post.edge_mass == pytest.approx(hyper["edge_mass"], rel=RTOL)
    assert post.edge_mass < 0.05
    assert list(np.unravel_index(np.argmax(post.weight), post.weight.shape)) == hyper["argmax"]
    # printed: absolute 0.01 (0.01-0.03) 1/M, relative 2 % (1-3 %)
    assert round(post.quantile("abs", 0.5), 2) == 0.01
    assert round(100 * post.quantile("rel", 0.5)) == 2


def test_tables_follow_the_declaration(result):
    per_day, post = result
    for table, name in ((per_day, "titration_days"), (post.table, "k_posterior")):
        assert table.dtype.names == tuple(c["column"] for c in columns.columns(name))


def test_line_fit_without_degree_of_freedom_has_no_error():
    slope, err = titration.line_fit([0.0, 1.0], [1.0, 3.0])
    assert slope == pytest.approx(2.0)
    assert err == 0.0
