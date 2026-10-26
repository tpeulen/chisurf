"""What a drop does with burst data: a legacy burstwise folder is a kind of its own, and a
measurement container's burst runs include the ones a fusion or a BID import wrote.

A burst run written by an operation other than the search (an imported BID selection, a fused
search) was invisible to the workspace: the container listed only the search's runs, so after a
project reopen the import's run was simply gone from the Datasets view.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.classify import classify, container_entries, is_burst_folder

SPC = (
    Path(__file__).resolve().parents[2]
    / "chisurf"
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)


def test_a_legacy_burstwise_folder_is_a_burst_folder(tmp_path: Path):
    folder = tmp_path / "sliding_window_All 0.1500#60"
    (folder / "bi4_bur").mkdir(parents=True)
    (folder / "bi4_bur" / "m000.bur").write_text("First Photon\tLast Photon\n0\t0\n")
    assert is_burst_folder(folder)
    assert classify(folder) == "burst_folder"


def test_a_folder_without_burst_tables_is_not(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "notes.txt").write_text("nothing")
    assert not is_burst_folder(tmp_path / "data")
    assert classify(tmp_path / "data") != "burst_folder"
    assert not is_burst_folder(tmp_path / "data" / "notes.txt")


@pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")
def test_an_imported_bid_selection_is_a_burst_run_of_its_container(tmp_path: Path):
    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

    (tmp_path / SPC.name).write_bytes(SPC.read_bytes())
    bid = tmp_path / "m000.bid"
    np.savetxt(bid, np.array([[100, 180], [900, 1010], [5000, 5120]]), fmt="%d")
    convert_bid_file(bid, output_types={"pto"})

    entries = container_entries(tmp_path / "m000.pto")
    kinds = [kind for kind, _address in entries]
    assert kinds.count("photons") >= 1
    runs = [address for kind, address in entries if kind == "bursts"]
    # The import's table is the container's top-level burst table: the container itself.
    assert runs == [str(tmp_path / "m000.pto")]
