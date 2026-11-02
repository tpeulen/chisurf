"""The per-frame file questions answer from one stat, and the same as before.

A run picker asks every frame which container a run lives in and whether a file is a container;
walking every path prefix and reading the container's header made those frames 0.1-0.3 s.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from chisurf.core.fio.address import split_address
from chisurf.core.fio.pto import is_measurement

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
)


def test_the_container_is_found_below_folders_with_dots(tmp_path):
    folder = tmp_path / "a.b" / "run.d"
    folder.mkdir(parents=True)
    container = folder / "m.pto"
    container.write_bytes(b"x")
    assert split_address(container / "sliding_window_All 0.15#60") == (
        container,
        "sliding_window_All 0.15#60",
    )
    assert split_address(container) == (container, "")
    assert split_address(folder / "missing.pto" / "run") == (None, None)
    assert split_address(tmp_path / "a.b") == (None, None)


def test_is_measurement_follows_a_rewritten_file(tmp_path):
    from chisurf.core.fio.fluorescence.burst_container import open_measurement

    photons = tmp_path / "m000.spc"
    shutil.copy(DATA, photons)
    with open_measurement(photons, tmp_path / "analysis", raw_data="sidecar"):
        pass
    container = tmp_path / "analysis" / "m000.pto"
    assert is_measurement(container) and is_measurement(container)  # the second from the memo
    container.write_bytes(b"not a container any more")
    stamp = container.stat().st_mtime_ns + 5_000_000_000
    os.utime(container, ns=(stamp, stamp))
    assert not is_measurement(container)
    assert not is_measurement(tmp_path / "nothing.pto")
