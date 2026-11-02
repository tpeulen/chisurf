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


def test_a_container_made_ahead_is_the_one_the_search_writes_into(tmp_path):
    """The pipeline makes the container while the file waits in Data Selection; a writer asking
    meanwhile waits for it instead of making a second one."""
    import threading

    from chisurf.core.fio.fluorescence.burst_container import ensure_container, open_measurement

    photons = tmp_path / "m000.spc"
    shutil.copy(DATA, photons)
    out = tmp_path / "analysis"
    made = {}
    ahead = threading.Thread(
        target=lambda: made.setdefault("path", ensure_container(photons, out, raw_data="sidecar"))
    )
    ahead.start()
    with open_measurement(photons, out, raw_data="sidecar"):
        pass
    ahead.join()
    assert made["path"] == out / "m000.pto" and is_measurement(made["path"])
    assert sorted(p.name for p in out.iterdir()) == ["m000.pto"]
    stamp = made["path"].stat().st_mtime_ns
    assert ensure_container(photons, out, raw_data="sidecar") == made["path"]
    assert made["path"].stat().st_mtime_ns == stamp  # an existing container is left alone
