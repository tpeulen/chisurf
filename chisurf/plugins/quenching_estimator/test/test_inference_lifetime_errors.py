"""Lifetime statistics reproduce the MalE prototype (chapter 2) from the shipped data.

Water quenching per site, pooled/leave-one-out/robust scatter, per-site errors with the prior
points, leave-one-out coverage, free-dye tau0 and kq_w,free, and the measured water access. The
port is bit for bit on the platform that wrote the golden file; RTOL only absorbs a different
LAPACK in ``numpy.polyfit`` elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import (
    columns,
    lifetime_errors,
    measurements,
)

GOLDEN = Path(__file__).resolve().parent / "baselines" / "male_prototype.json"
RTOL = 1e-12


@pytest.fixture(scope="module")
def golden():
    """The prototype golden document."""
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def result():
    """Chapter 2 on the shipped data."""
    data = measurements.load_measurements()
    return lifetime_errors.analyse_lifetimes(data.lifetimes, data.titration_summary)


def test_water_quenching_per_site(result, golden):
    ref = golden["water"]
    water = result.water
    assert [(str(r["dye"]), str(r["state"]), int(r["site"])) for r in water] == [
        (r["dye"], r["state"], r["site"]) for r in ref
    ]
    np.testing.assert_allclose(water["kq_w"], [r["kq_w"] for r in ref], rtol=RTOL, atol=0)
    summary = lifetime_errors.water_quenching_summary(water)
    for dye, stats in golden["water_summary"].items():
        for key, value in stats.items():
            assert summary[dye][key] == pytest.approx(value, rel=RTOL), (dye, key)
    # printed: AF488 0.012/-0.040/0.077, Atto655 0.158/0.028/0.280, Cy3B 0.024/0.011/0.029
    assert round(summary["Atto655"]["median"], 3) == 0.158


def test_measurement_scatter_and_coverage(result, golden):
    for dye, ref in golden["scatter"].items():
        row = result.scatter[result.scatter["dye"] == dye][0]
        assert row["series"] == ref["series"] and row["points"] == ref["points"]
        for key in ("regression", "leave_one_out", "typical"):
            assert row[key] == pytest.approx(ref[key], rel=RTOL), (dye, key)
        assert row["coverage"] == golden["coverage"][dye]
    assert result.coverage == golden["coverage"]
    # printed: AF488 4.78/4.74/0.91 %, coverage 57 / 69 / 61 %
    assert round(100 * result.scatter["regression"][0], 2) == 4.78
    assert {d: round(100 * v) for d, v in result.coverage.items()} == {
        "AF488": 57,
        "Atto655": 69,
        "Cy3B": 61,
    }


def test_site_lifetimes_with_errors(result, golden):
    ref = golden["data"]
    data = result.data
    assert len(data) == 64
    assert [(str(r["dye"]), str(r["solvent"]), str(r["state"]), int(r["site"])) for r in data] == [
        (r["dye"], r["solvent"], r["state"], r["site"]) for r in ref
    ]
    assert data["n"].tolist() == [r["n"] for r in ref]
    for field, key in (
        ("tau_x", "tauX"),
        ("sigma_meas", "sigma_meas"),
        ("point_error_pct", "point_error_pct"),
        ("water_slope", "water_slope"),
        ("water_slope_err", "water_slope_err"),
    ):
        np.testing.assert_allclose(
            data[field], [r[key] for r in ref], rtol=RTOL, atol=0, err_msg=field
        )
    # the plan's spot value: AF488 H2O APO 72
    assert data["tau_x"][0] == pytest.approx(3.0882338779942993, rel=RTOL)
    assert data["sigma_meas"][0] == pytest.approx(0.023607500932585287, rel=RTOL)
    for key, value in golden["median_sigma_meas"].items():
        assert result.median_sigma()[key] == pytest.approx(value, rel=RTOL), key


def test_free_dye_and_water_reference(result, golden):
    for key, value in golden["TAU0"].items():
        assert result.tau0[tuple(key.split())] == pytest.approx(value, rel=RTOL), key
    assert result.kqw_free == pytest.approx(golden["KQW_FREE"], rel=RTOL)
    table = lifetime_errors.free_dye_table(result.tau0)
    assert len(table) == 4


def test_measured_water_access(result, golden):
    ref = golden["water_access"]["rows"]
    access = result.access
    assert [(int(r["site"]), str(r["state"])) for r in access] == [
        (r["site"], r["state"]) for r in ref
    ]
    np.testing.assert_allclose(access["measured"], [r["measured"] for r in ref], rtol=RTOL, atol=0)
    np.testing.assert_allclose(
        access["measured_err"], [r["measured_err"] for r in ref], rtol=RTOL, atol=0
    )
    printed = [
        0.498,
        0.102,
        0.644,
        0.830,
        0.593,
        0.474,
        0.549,
        0.709,
        1.034,
        0.493,
        0.578,
        0.536,
        0.799,
        0.542,
        0.487,
        0.589,
        0.647,
        0.974,
    ]
    assert np.round(access["measured"], 3).tolist() == printed


def test_tables_follow_the_declaration(result):
    for table, name in (
        (result.water, "water_quenching"),
        (result.scatter, "measurement_scatter"),
        (result.data, "site_lifetimes"),
        (result.access, "water_access"),
        (lifetime_errors.free_dye_table(result.tau0), "free_dye_lifetimes"),
    ):
        assert table.dtype.names == tuple(c["column"] for c in columns.columns(name)), name
