"""Layout test for the legacy td4 writer: one row per burst, not one row per result.

Pins the fix to the bug documented in ``okf/references/known-issues.md`` and in
``test_container.py``'s module docstring: ``_save_td4_results`` used to build
its row grid from ``Burst Index`` values the correlator actually produced, so a
burst it skipped was a *missing* row rather than a sentinel one, and every
later burst's diffusion time landed one row too early -- silently, because the
shape and the column names stayed right and only the attribution was wrong.

``burst_counts`` (the true ``.bur``/``.bst`` grid size, threaded through from
``_run_burstwise_fcs``) is what fixes it: it lets the writer allocate the full
per-measurement grid before filling in the bursts that produced a result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.core.fio.fluorescence.burst_companion import read_companion


def _rows(burst_folder: str, first_file: str) -> list:
    """Four results out of eight bursts -- gaps at 2 and 4-6, as in test_container.py."""
    ids = [0, 1, 3, 7]
    means = [0.51, 0.62, 0.48, 0.55]
    peaks = [0.50, 0.60, 0.47, 0.54]
    return [
        {
            "First File": first_file,
            "Burst Folder": burst_folder,
            "Burst Index": bid,
            "pair_name": "green-red",
            "pair_channel_a": "green",
            "pair_channel_b": "red",
            "td_mean_ms": mean,
            "td_peak_ms": peak,
            "n_bins": 3,
            "n_casc": 20,
            "make_fine": False,
        }
        for bid, mean, peak in zip(ids, means, peaks)
    ]


def test_a_skipped_burst_is_a_sentinel_row_not_a_missing_one(tmp_path: Path, qapp, qtbot, monkeypatch):
    from chisurf.plugins.burst.burst_fcs_correlator.wizard import BurstWiseFCSWizard

    w = BurstWiseFCSWizard()
    qtbot.addWidget(w)
    # The container path is pinned separately in test_container.py; stub it out
    # here so this test is only about the td4 companion's row grid.
    monkeypatch.setattr(w, "_write_container", lambda *a, **k: None)

    burst_folder = str(tmp_path)
    first_file = str(tmp_path / "m000.spc")
    rows = _rows(burst_folder, first_file)
    burst_counts = {(burst_folder, "m000"): 8}

    w._save_td4_results(rows, burst_counts)

    td4_file = tmp_path / "td4" / "m000.td4"
    assert td4_file.exists()
    columns, body = read_companion(td4_file)

    # Every burst of the measurement, not just the 4 that produced a result.
    assert body.shape[0] == 8
    assert "td_mean__green-red" in columns
    mean_col = columns.index("td_mean__green-red")

    # Computed bursts keep their true position -- burst 7 lands on row 7, not
    # shifted up to row 3 the way a "unique Burst Index values" grid would put it.
    assert body[0, mean_col] == pytest.approx(0.51)
    assert body[1, mean_col] == pytest.approx(0.62)
    assert body[3, mean_col] == pytest.approx(0.48)
    assert body[7, mean_col] == pytest.approx(0.55)

    # Skipped bursts are sentinel rows, not missing ones.
    for skipped in (2, 4, 5, 6):
        assert body[skipped, mean_col] == 0.0


def test_without_a_burst_count_it_falls_back_to_the_bursts_computed(tmp_path: Path, qapp, qtbot, monkeypatch):
    """Defensive fallback when ``burst_counts`` lacks the (folder, stem) key.

    Still writes a file rather than crashing, but the grid is only as wide as
    the highest ``Burst Index`` actually computed -- narrower than the true
    ``.bur`` grid, which is why ``_run_burstwise_fcs`` always supplies the real
    count in the ordinary path.
    """
    from chisurf.plugins.burst.burst_fcs_correlator.wizard import BurstWiseFCSWizard

    w = BurstWiseFCSWizard()
    qtbot.addWidget(w)
    monkeypatch.setattr(w, "_write_container", lambda *a, **k: None)

    burst_folder = str(tmp_path)
    first_file = str(tmp_path / "m000.spc")
    rows = _rows(burst_folder, first_file)

    w._save_td4_results(rows, {})

    td4_file = tmp_path / "td4" / "m000.td4"
    columns, body = read_companion(td4_file)
    assert body.shape[0] == 8  # last Burst Index (7) + 1
