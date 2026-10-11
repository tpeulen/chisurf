"""E and S are count ratios: a table's window streams are read as counts, never as rates.

A stream's rate is its photons over *its own* first-to-last span, so two streams'
rates have different denominators (and one photon has no span at all: NaN). Taken
as if they were counts they gave E and S that no histogram looks wrong for -- on
the bundled sm-DNA folder 923 of 2980 bursts dropped out of the gates (S NaN) and
the donor-only peak was truncated. The tables the writers produce now carry
``S <window> <detector> (photons) | r0-r1`` beside each rate (the bundled folder
was brought to that layout from its own photons: every rate column reproduces to
1e-6), and the browser reads those.
"""

from __future__ import annotations

import pathlib

import numpy as np

from chisurf.core.datastore import column_names, numeric_column
from chisurf.plugins.burst.burst_browser.view_model import BurstBrowserViewModel

BUNDLED = (
    pathlib.Path(__file__).resolve().parents[2]
    / "burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/bi4_bur"
)


def test_the_bundled_sm_dna_folder_keeps_every_burst_with_count_ratio_es():
    model = BurstBrowserViewModel()
    model.load_folder(BUNDLED)
    assert model.status_text() == "Bursts: 2980 / 2980 selected"
    names = column_names(model.table)
    dd = np.maximum(numeric_column(model.table, "S prompt green (photons) | 0-2048"), 0)
    da = np.maximum(numeric_column(model.table, "S prompt red (photons) | 0-2048"), 0)
    aa = np.maximum(numeric_column(model.table, "S delayed yellow (photons) | 2048-4095"), 0)
    assert "S prompt yellow (photons) | 0-2048" in names
    e = numeric_column(model.table, "E")
    s = numeric_column(model.table, "S")
    assert not np.isnan(e).any() and not np.isnan(s).any()
    np.testing.assert_allclose(e, da / (dd + da))
    np.testing.assert_allclose(s, (dd + da) / (dd + da + aa))
    assert (e >= 0).all() and (e <= 1).all() and (s >= 0).all() and (s <= 1).all()


def test_counts_are_preferred_over_rates_when_both_are_present(tmp_path):
    folder = tmp_path / "bi4_bur"
    folder.mkdir()
    header = [
        "First Photon", "Last Photon", "Duration (ms)", "Number of Photons",
        "Number of Photons (green)", "Number of Photons (red)",
        "S prompt green (kHz) | 0-2048", "S prompt green (photons) | 0-2048",
        "S prompt red (kHz) | 0-2048", "S prompt red (photons) | 0-2048",
    ]
    # one photon in the red stream: its rate is NaN, its count is 1
    rows = [[0, 9, 1.0, 10, 9, 1, 9.0, 9, float("nan"), 1]]
    lines = ["\t".join(header) + "\t"]
    zero = "\t".join("0" for _ in header) + "\t"
    for row in rows:
        lines += [zero, "\t".join(str(v) for v in row) + "\t"]
    lines.append(zero)
    (folder / "m000.bur").write_text("\n".join(lines) + "\n")
    model = BurstBrowserViewModel()
    model.load_folder(folder)
    assert model.status_text() == "Bursts: 1 / 1 selected"
    np.testing.assert_allclose(numeric_column(model.table, "E"), [0.1])
