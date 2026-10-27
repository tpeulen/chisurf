"""A table of named columns drops in as a table row; a headed curve stays a curve."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from chisurf.core.fio.classify import classify

ROOT = Path(__file__).resolve().parents[2]


def test_a_burst_and_a_result_table_are_tables():
    bur = next((ROOT / "chisurf/plugins/burst/burstwise_import/tests/data").rglob("*.bur"))
    assert classify(bur) == "table"
    quest = ROOT / "chisurf/plugins/quenching_estimator/examples/male/tcspc_fit_results.csv"
    assert classify(quest) == "table"


def test_a_curve_with_a_header_stays_a_curve(tmp_path):
    curve = tmp_path / "decay.csv"
    curve.write_text("time,counts,error\n" + "".join(f"{i},{100 - i},1\n" for i in range(50)))
    assert classify(curve) == "curve"
    bare = tmp_path / "decay.txt"
    bare.write_text("".join(f"{i} {100 - i} 1 2 3 4\n" for i in range(50)))
    assert classify(bare) == "curve"  # numbers in the first line: data


def test_an_npz_of_columns_is_a_table_a_lut_stays_a_setup(tmp_path):
    columns = tmp_path / "bursts.npz"
    np.savez(columns, **{name: np.arange(10.0) for name in "abcdef"})
    assert classify(columns) == "table"
    lut = tmp_path / "lut.npz"
    np.savez(lut, lut=np.arange(10.0), shifts=np.zeros(3))
    assert classify(lut) == "setup"


def test_a_trajectory_is_a_trajectory(tmp_path):
    for suffix in (".dcd", ".xtc", ".trr", ".nc"):
        path = tmp_path / f"run{suffix}"
        path.write_bytes(b"\0" * 16)
        assert classify(path) == "trajectory"
