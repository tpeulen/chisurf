"""The zero separator rows of a ``.bur`` table are not bursts.

A Seidel ``.bur`` interleaves an all-zero row after every burst. Its ``First
File``/``Last File`` both read ``0``, so it passed the same-file test of
``read_bur_bursts`` and every table resolved to an extra one-photon "burst" at
photon 0 -- the ``(0, 1)`` that led every PDA read of the bundled sm-DNA folder
(guide 11's ``reader.resolve_inputs(["burstwise_All 0.1000#15"])``).
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

FOLDER = pathlib.Path(__file__).resolve().parents[2] / (
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15"
)


def test_a_zero_row_naming_file_0_is_dropped(tmp_path):
    from chisurf.core.experiments.pda2c.inputs import read_bur_bursts

    path = tmp_path / "m000.bur"
    path.write_text(
        "First Photon\tLast Photon\tNumber of Photons\tFirst File\tLast File\n"
        "0\t0\t0\t0\t0\n"
        "10\t19\t10\tm000.spc\tm000.spc\n"
        "0\t0\t0\t0\t0\n"
    )
    names, starts, stops = read_bur_bursts(path)
    assert names.tolist() == ["m000.spc"]
    np.testing.assert_array_equal(starts, [10])
    np.testing.assert_array_equal(stops, [20])


def test_the_bundled_burst_folder_resolves_no_photon_zero_burst():
    from chisurf.core.experiments.pda2c.inputs import read_bur_bursts, resolve_bur_files

    bur = FOLDER / "bi4_bur" / "m000.bur"
    if not bur.is_file():
        pytest.skip("sm-DNA fixture not present")
    names, starts, stops = read_bur_bursts(bur)
    assert (names == "m000.spc").all()
    assert (stops - starts > 1).all()
    _, slices = resolve_bur_files([str(bur)])
    (intervals,) = slices.values()
    assert intervals[0] == (int(starts[0]), int(stops[0]))
