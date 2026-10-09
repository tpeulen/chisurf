"""Logical burst identity must survive the legacy physical zero interleave."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.core.datastore import numeric_column
from chisurf.core.fio.fluorescence.burst import read_bur_with_companions
from chisurf.core.fio.fluorescence.burst_companion import write_companion
from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
from chisurf.core.fluorescence.burst.table import read_burst_table

DATA = (
    Path(__file__).resolve().parents[2] / "chisurf/plugins/burst/burst_selection/tests/data/"
    "bh_spc132_sm_dna"
)
REAL_BUR = DATA / "burst_analysis_handoff/bi4_bur/m000.bur"


def _write_legacy(path, names, rows):
    """Write the documented physical grid without using the reader under test."""
    path.parent.mkdir(parents=True, exist_ok=True)
    zero = "\t".join(["0"] * len(names))
    lines = ["\t".join(names), zero]
    for row in rows:
        lines.extend(["\t".join(map(str, row)), zero])
    path.write_text("\n".join(lines) + "\n")
    return path


def test_real_bur_has_152_logical_rows_and_exact_numeric_headers():
    """The actual measured file has 305 physical rows, not 305 bursts."""
    lines = REAL_BUR.read_text().splitlines()
    names = lines[0].split("\t")
    raw = [row.split("\t") for row in lines[1:]]
    assert len(raw) == 305
    expected_names = [n for n in names if n and n not in ("First File", "Last File")]
    columns = read_burst_table(REAL_BUR)
    assert list(columns) == expected_names
    assert {len(values) for values in columns.values()} == {152}
    for name in expected_names:
        expected = np.array([float(row[names.index(name)] or "nan") for row in raw[1::2]])
        np.testing.assert_array_equal(columns[name], expected)
        assert columns[name].dtype == np.dtype(float)
    mapping = tttrlib.guess_burst_columns(list(columns))
    nonfinite = ~np.isfinite(
        np.column_stack([columns[mapping[k]] for k in ("i_dd", "i_da", "i_aa")])
    ).all(axis=1)
    assert int(nonfinite.sum()) == 42


def test_real_calibration_matches_independent_logical_rows_without_padding():
    """Calibration sees real observations, so fitted classes/factors may change."""
    from chisurf.plugins.burst.accurate_fret.core import calibrate

    columns = read_burst_table(REAL_BUR)
    mapping = tttrlib.guess_burst_columns(list(columns))
    lines = REAL_BUR.read_text().splitlines()
    names = lines[0].split("\t")
    logical = [row.split("\t") for row in lines[2::2]]
    independent_channels = [
        np.array([float(row[names.index(mapping[role])] or "nan") for row in logical])
        for role in ("i_dd", "i_da", "i_aa")
    ]
    expected = calibrate(*independent_channels, n_bootstrap=0, use_priors=False)
    result = calibrate(
        *(columns[mapping[k]] for k in ("i_dd", "i_da", "i_aa")), n_bootstrap=0, use_priors=False
    )
    assert len(result.labels) == 152
    np.testing.assert_array_equal(result.labels, expected.labels)
    assert result.factors == pytest.approx(expected.factors)
    # Removing padding also changes the fitted factors: 154-153 is not the
    # correct final acceptor-only population after re-estimation.
    assert int(np.sum(result.calibration.split.acceptor_only)) == 0
    assert int(np.sum(result.calibration.split.fret)) == 93


def test_companions_align_before_deinterleave_and_keep_zero_nan_bursts(tmp_path):
    """A zero observation and a nonfinite observation retain their positions."""
    bur = _write_legacy(
        tmp_path / "bi4_bur/m000.bur",
        ["First Photon", "Green Count Rate (KHz)", "Tau (green)", ""],
        [[0, 0, np.nan, 0], [12, 5, np.nan, 0], [20, np.nan, np.nan, 0]],
    )
    write_companion(
        tmp_path, "xx4", "m000", ["Analysis score", "Skipped result"], [[7, 0], [8, 0], [9, 0]]
    )
    columns = read_burst_table(bur)
    np.testing.assert_array_equal(columns["First Photon"], [0, 12, 20])
    np.testing.assert_array_equal(columns["Analysis score"], [7, 8, 9])
    np.testing.assert_array_equal(columns["Skipped result"], [0, 0, 0])
    np.testing.assert_array_equal(columns["Green Count Rate (KHz)"], [0, 5, np.nan])
    np.testing.assert_array_equal(columns["Tau (green)"], [np.nan] * 3)
    assert "" not in columns


def test_ordinary_noninterleaved_bur_keeps_all_rows(tmp_path):
    """A genuine zero-valued row is retained in an already logical table."""
    path = tmp_path / "logical.bur"
    path.write_text("First Photon\tCount Rate (KHz)\n1\t3\n0\t0\n4\t5\n")
    columns = read_burst_table(path)
    np.testing.assert_array_equal(columns["First Photon"], [1, 0, 4])


@pytest.mark.parametrize("delimiter,suffix", [(",", ".csv"), ("\t", ".tsv"), (";", ".txt")])
def test_generic_delimited_zero_and_nonfinite_rows_are_unchanged(tmp_path, delimiter, suffix):
    """Only BUR physical layout changes; generic tables preserve their rows."""
    path = tmp_path / ("generic" + suffix)
    path.write_text(
        delimiter.join(["i_dd", "i_da", "name"])
        + "\n"
        + "\n".join(
            delimiter.join(row) for row in [("0", "0", "a"), ("1", "nan", "b"), ("0", "0", "c")]
        )
        + "\n"
    )
    columns = read_burst_table(path)
    assert list(columns) == ["i_dd", "i_da"]
    np.testing.assert_array_equal(columns["i_dd"], [0, 1, 0])
    np.testing.assert_array_equal(columns["i_da"], [0, np.nan, 0])


def test_npz_and_json_contracts_are_unchanged(tmp_path):
    """NPZ accepts numeric arrays; JSON is still outside this reader's contract."""
    path = tmp_path / "table.npz"
    np.savez(path, i_dd=np.array([0, 2, np.nan]), i_da=np.array([[0, 3, 4]]))
    columns = read_burst_table(path)
    np.testing.assert_array_equal(columns["i_dd"], [0, 2, np.nan])
    np.testing.assert_array_equal(columns["i_da"], [0, 3, 4])
    path = tmp_path / "table.json"
    path.write_text(json.dumps({"i_dd": [1, 2], "i_da": [3, 4]}))
    with pytest.raises(ValueError, match="no numeric columns"):
        read_burst_table(path)


def test_actual_pto_burst_run_values_remain_unchanged(tmp_path):
    """Container dispatch continues to read its declared burst artifact."""
    from chisurf.core.fio.pto import Measurement

    table = deinterleave_bursts(read_bur_with_companions(REAL_BUR))
    with Measurement.create(DATA / "m000.spc", out_dir=tmp_path) as measurement:
        measurement.put_table(
            "measured/bursts",
            table,
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
        )
        path = measurement.path
    columns = read_burst_table(str(path) + "/measured")
    for name in ("First Photon", "Duration (ms)", "Green Count Rate (KHz)"):
        np.testing.assert_array_equal(columns[name], numeric_column(table, name))
    assert len(columns["First Photon"]) == 152


def test_core_bur_read_is_qt_free_in_a_fresh_process():
    """The shared format path does not import graphical libraries or plugins."""
    script = (
        "import sys; from chisurf.core.fluorescence.burst.table import read_burst_table; "
        "data=read_burst_table(sys.argv[1]); "
        "assert not any(m.split('.')[0] in "
        "{'qtpy','PyQt5','PyQt6','PySide2','PySide6','emtk'} for m in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script, str(REAL_BUR)], check=True, capture_output=True)
