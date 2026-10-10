"""A skipped burst stays a sentinel row once the container is exported to a td4.

Pins the fix to the bug documented in ``okf/references/known-issues.md`` and in
``test_container.py``'s module docstring: ``_save_td4_results`` used to build
its row grid from the ``Burst Index`` values the correlator actually produced,
so a burst it skipped was a *missing* row and every later burst's diffusion time
landed one row too early. The container holds only the bursts that produced a
result, keyed by ``Burst Index``; the explicit legacy export puts them back on
the burst table's full grid.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.burst_companion import read_companion


def _rows(burst_folder: str, first_file: str) -> list:
    """Four results out of eight bursts -- gaps at 2 and 4-6."""
    ids = [0, 1, 3, 7]
    means = [0.51, 0.62, 0.48, 0.55]
    peaks = [0.50, 0.60, 0.47, 0.54]
    return [
        {
            "First File": first_file,
            "Burst Folder": burst_folder,
            "Burst Index": bid,
            "pair_name": "green-red",
            "td_mean_ms": mean,
            "td_peak_ms": peak,
        }
        for bid, mean, peak in zip(ids, means, peaks)
    ]


def test_a_skipped_burst_is_a_sentinel_row_not_a_missing_one(tmp_path: Path):
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact
    from chisurf.core.fio.fluorescence.legacy_export import export_legacy
    from chisurf.plugins.burst.burst_fcs_correlator.core.export import write_fcs_results

    source = Path(__file__).resolve().parents[5] / "test/data/tttr/BH/132/BH_SPC132.spc"
    raw = tmp_path / "m000.spc"
    shutil.copyfile(source, raw)
    container = write_burst_artifact(
        raw,
        {"Number of Photons": np.arange(8, dtype=float) + 10},
        name="bursts",
        artifact_kind="burst_table",
        operation_type="burst_selection",
        derived_from=(),
    )
    write_fcs_results(
        _rows(str(tmp_path), str(raw)), {(str(tmp_path), "m000"): 8}, parameters={"n_bins": 3}
    )
    assert not (tmp_path / "td4").exists()

    out = tmp_path / "legacy"
    written = export_legacy(container, out)
    td4 = [p for p in written if p.suffix == ".td4"]
    assert len(td4) == 1 and td4[0].parent.name == "td4"
    columns, body = read_companion(td4[0])

    assert body.shape[0] == 8  # every burst of the measurement
    mean_col = columns.index("td_mean__green-red")
    assert body[0, mean_col] == pytest.approx(0.51)
    assert body[1, mean_col] == pytest.approx(0.62)
    assert body[3, mean_col] == pytest.approx(0.48)
    assert body[7, mean_col] == pytest.approx(0.55)  # row 7, not shifted up to 3
    for skipped in (2, 4, 5, 6):
        assert body[skipped, mean_col] == 0.0
