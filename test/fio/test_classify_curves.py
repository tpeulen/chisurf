"""A dropped curve finds its experiment from the file (chisurf.core.fio.classify.curve_reader).

The one drop takes curves too: with no file type chosen in Read data, the file's own content says
whether it is a decay (TCSPC) or a correlation (FCS), and how to read it. The probe reads a bounded
head and tail of the file and never raises.
"""

from __future__ import annotations

import pathlib

import numpy as np

from chisurf.core.fio.classify import classify, curve_reader

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_a_stacked_vv_vh_decay_with_its_footer_is_a_tcspc_curve_read_as_it_says(tmp_path):
    counts = np.r_[np.zeros(10), np.arange(40, 0, -1), np.zeros(10), np.arange(20, 0, -1)]
    path = tmp_path / "demo.txt"
    path.write_text(
        "\n".join(f"{c:.6f}" for c in counts) + "\n# #l1: 0.0\n# #l2: 0.0\n# #dt: 0.008\n"
    )
    assert classify(path) == "curve"
    assert curve_reader(path) == (
        "TCSPC", "TXT/CSV", {"skiprows": 0, "x_on": False, "is_vv_vh": True, "dt": 0.008}
    )


def test_a_two_column_decay_with_a_header_line_is_tcspc(tmp_path):
    path = tmp_path / "irf.dat"
    path.write_text("time\tcounts\n" + "\n".join(f"{i * 0.05}\t{max(0, 50 - i)}" for i in range(64)))
    assert curve_reader(path) == ("TCSPC", "TXT/CSV", {"skiprows": 1, "x_on": True, "is_vv_vh": False})


def test_lag_times_spread_over_decades_are_a_correlation(tmp_path):
    tau = np.concatenate([np.arange(1, 9) * 1e-6 * 2.0**k for k in range(12)])
    path = tmp_path / "g.csv"
    path.write_text("\n".join(f"{t:.6e},{1 + 1 / (1 + t / 1e-4):.6f}" for t in np.unique(tau)))
    assert curve_reader(path) == ("FCS", "FCS-CSV", {})


def test_a_correlator_extension_names_its_reader_and_nothing_says_none(tmp_path):
    assert curve_reader(tmp_path / "x.asc")[:2] == ("FCS", "ALV-Correlator")
    empty = tmp_path / "notes.txt"
    empty.write_text("a few words\n")
    assert curve_reader(empty) is None
    assert curve_reader(tmp_path / "missing.txt") is None  # never raises


def test_the_repository_samples():
    tcspc = REPO / "test/data/tcspc/decay_fit/Prompt.txt"
    fcs = REPO / "test/data/fcs/CSV/fcs-csv.csv"
    if tcspc.is_file():
        assert curve_reader(tcspc)[0] == "TCSPC"
    if fcs.is_file():
        assert curve_reader(fcs)[0] == "FCS"
