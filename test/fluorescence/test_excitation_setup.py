"""Reading a detector setup, the range dialects and the gate-only check (excitation.setup)."""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.excitation import (
    channel_map,
    format_ranges,
    gates_from_inclusive,
    gates_to_inclusive,
    merge_gates,
    micro_mask,
    polarization_channels,
)

SETUP = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4096]},
    "detectors": {"green": {"chs": [0, 8], "micro_time_ranges": [[0, 4096]]},
                  "red": {"chs": [1, 9]}},
}


def test_channel_map_is_window_by_detector_with_its_gates():
    m = channel_map(SETUP)
    assert set(m) == {"prompt_green", "prompt_red", "delayed_green", "delayed_red"}
    assert m["prompt_green"] == [{"window_range": [0, 2048], "detector_chs": [0, 8],
                                  "micro_time_range": [0, 4096]}]
    assert m["prompt_red"] == []
    assert channel_map(SETUP, ungated_means_all=True)["prompt_red"][0]["micro_time_range"] is None
    per = channel_map({"detectors": SETUP["detectors"]}, per_detector_without_windows=True,
                      ungated_means_all=True)
    assert set(per) == {"green", "red"} and per["red"][0]["window_range"] is None
    assert channel_map({"data": SETUP}) == m


def test_range_dialects_round_trip_and_masks_agree():
    assert gates_to_inclusive([[0, 2048]]) == [(0, 2047)]
    assert gates_from_inclusive([(0, 2047)]) == [[0, 2048]]
    micro = np.arange(10)
    assert micro_mask(micro, [[2, 5]]).nonzero()[0].tolist() == [2, 3, 4]
    assert micro_mask(micro, [(2, 4)], inclusive=True).tolist() == micro_mask(micro, [[2, 5]]).tolist()
    assert micro_mask(micro, None).all()


def test_polarization_merge_and_format():
    assert polarization_channels({"chs": [0, 8]}) == ([0], [8])
    assert polarization_channels({"chs": [3]}) == ([3], [3])
    assert polarization_channels({"ch_p": [1], "ch_s": [2], "chs": [5]}) == ([1], [2])
    out = merge_gates(SETUP["detectors"], {"red": [[0, 3125]], "other": [[1, 2]]})
    assert out["red"]["micro_time_ranges"] == [[0, 3125]] and "other" not in out
    assert format_ranges({"prompt": [50, 1613], "green": [[0, 10], [20, 30]]}) == \
        "prompt 50–1613, green 0–10, 20–30"
