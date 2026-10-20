"""The shipped MalE measurement tables, their reader, and the prototype golden file.

The golden file ``baselines/male_prototype.json`` is produced by executing the MalE prototype
notebook (``baselines/make_male_prototype.py``); these tests pin the data it was produced from.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import measurements as m

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "baselines" / "male_prototype.json"
SITE_FIXTURE = HERE / "data" / "male_site_1omp72_L20.12.npz"


@pytest.fixture(scope="module")
def data():
    """The shipped MalE data set, read once."""
    return m.load_measurements()


@pytest.fixture(scope="module")
def golden():
    """The prototype golden document."""
    return json.loads(GOLDEN.read_text())


def _sha256(path):
    """Hex SHA-256 of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_row_counts(data):
    assert len(data.lifetimes) == 248
    assert len(data.titration_summary) == 17
    assert len(data.titration_points) == 297
    assert data.folder == m.EXAMPLE_FOLDER


def test_six_af488_rows_are_corrected_95_to_186(data):
    got = [(c.dye, c.condition, c.d2o_percent, int(c.variant), c.site) for c in data.corrections]
    assert got == [
        ("AF488", "APO", 0.0, 95, 186),
        ("AF488", "APO", 90.0, 95, 186),
        ("AF488", "APO", 54.0, 95, 186),
        ("AF488", "HOLO", 0.0, 95, 186),
        ("AF488", "HOLO", 87.84, 95, 186),
        ("AF488", "HOLO", 52.65, 95, 186),
    ]
    rows = [c.row for c in data.corrections]
    assert np.all(data.lifetimes["site"][rows] == 186)
    assert np.all(data.lifetimes["variant"][rows] == 95)
    assert all("MalE186AF488" in c.data_path for c in data.corrections)


def test_uncorrected_rows_keep_their_variant(data):
    lt = data.lifetimes
    corrected = np.zeros(len(lt), bool)
    corrected[[c.row for c in data.corrections]] = True
    same = (lt["site"] == lt["variant"]) | (np.isnan(lt["site"]) & np.isnan(lt["variant"]))
    assert np.all(same[~corrected])


def test_measured_sites_and_dyes(data):
    lt = data.lifetimes
    labelled = np.isin(lt["condition"], ["APO", "HOLO"])
    assert set(np.unique(lt["dye"])) == {"AF488", "Cy3B", "Atto655"}
    assert set(lt["site"][labelled].astype(int)) == {72, 92, 95, 186, 211, 219, 233, 309, 322}
    assert np.all(np.isfinite(lt["tau_x"]))


def test_titration_summary_columns(data):
    ts = data.titration_summary
    af488_trp = ts[(ts["dye"] == "AF488") & (ts["quencher"] == "Trp")][0]
    assert af488_trp["n_dates"] == 3
    assert af488_trp["ksv_per_M"] == pytest.approx(14.427279634236234, abs=0)
    assert set(np.unique(ts["dye"])) == {"AF488", "Cy3B", "Atto655"}


def test_reader_agrees_with_golden(data, golden):
    counts = golden["measurements"]
    assert counts["lifetime_rows"] == len(data.lifetimes)
    assert counts["titration_results"] == len(data.titration_summary)
    assert counts["titration_points"] == len(data.titration_points)
    assert [c["row"] for c in counts["corrections"]] == [c.row for c in data.corrections]


def test_provenance_checksums_match_the_shipped_files():
    provenance = json.loads((m.EXAMPLE_FOLDER / "provenance.json").read_text())
    for name, entry in provenance["files"].items():
        assert _sha256(m.EXAMPLE_FOLDER / name) == entry["sha256"], name
    for name, entry in provenance["structures"].items():
        assert _sha256(m.EXAMPLE_FOLDER / name) == entry["sha256"], name
    assert (m.EXAMPLE_FOLDER / "1OMP.cif").read_text().startswith("data_1OMP")
    assert (m.EXAMPLE_FOLDER / "1ANF.cif").read_text().startswith("data_1ANF")


def test_site_fixture_is_the_prototype_table(golden):
    assert _sha256(SITE_FIXTURE) == golden["site_fixture"]["sha256"]
    assert golden["site_tables"]["APO 72 20.12"]["sha256"] == golden["site_fixture"]["sha256"]
    with np.load(SITE_FIXTURE) as table:
        n = table["neighbours"].shape[0]
        assert table["neighbours"].dtype == np.int8 and table["neighbours"].shape == (n, 20)
        assert table["contacts"].dtype == np.float16 and table["contacts"].shape == (n, 5, 10, 2)
        assert table["exposure"].dtype == np.float32 and table["exposure"].shape == (n,)


def test_golden_covers_the_recorded_quantities(golden):
    for key in (
        "per_day",
        "K_POSTERIOR",
        "hyper",
        "water",
        "scatter",
        "data",
        "coverage",
        "TAU0",
        "KQW_FREE",
        "KQ_TABLE",
        "KQ_TABLE_SD",
        "stretched_linker_AF488",
        "site_lifetimes",
        "naive_h2o_test",
        "water_access",
        "time_weighted_exposure_stage_c",
        "printed",
    ):
        assert key in golden, key
    assert len(golden["data"]) == 64
    assert len(golden["K_POSTERIOR"]) == 17
    assert golden["KQW_FREE"] == pytest.approx(0.271, abs=5e-4)
    stages = {k: v for k, v in golden["site_lifetimes"].items() if k != "note"}
    assert {k: len(v["rows"]) for k, v in stages.items()} == {
        "AF488 in H2O": 18,
        "Cy3B in H2O": 10,
        "Atto655 in D2O": 18,
        "Atto655 in D2O and H2O": 36,
    }
    # The Site model at the printed (rounded) estimates reproduces the stored run's printed summaries.
    assert stages["AF488 in H2O"]["rms"] == pytest.approx(0.62, abs=0.005)
    assert stages["AF488 in H2O"]["median_abs_dev"] == pytest.approx(0.047, abs=0.0005)
    assert stages["Atto655 in D2O and H2O"]["median_abs_dev"] == pytest.approx(0.094, abs=0.0005)


def test_read_table_handles_empty_cells_and_missing_columns(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(
        "Date,D2O %,Variant,Dye,Condition,tauX,Data path name\n"
        "20260101,,,AF488,dye,4.1,x\\MalE72AF488_a\n"
        ",,,,,,\n"
    )
    lifetimes, corrections = m.read_lifetimes(path)
    assert len(lifetimes) == 1
    assert np.isnan(lifetimes["d2o_percent"][0])
    assert lifetimes["site"][0] == 72  # an empty variant is filled from the file name
    assert len(corrections) == 1
    with pytest.raises(KeyError, match="is missing"):
        m.read_titration_points(path)


def test_reader_needs_no_pandas_or_scipy():
    tree = ast.parse(Path(m.__file__).read_text())
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported |= {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imported & {"pandas", "scipy", "openpyxl", "Bio"}
