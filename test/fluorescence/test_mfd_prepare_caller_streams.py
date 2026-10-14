"""Caller ``streams=`` are matched to the detector columns by name, never by position.

A partial list used to crash with ``IndexError: index 2 is out of bounds`` in the
count-agreement loop, and a complete list in another order than the columns would
have checked (and fitted) each detector against another detector's photons.
"""

from pathlib import Path

import pytest

from chisurf.core.fluorescence.mfd.prepare import prepare_burst_folder

FOLDER = (
    Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15"
)

GREEN = {"name": "green", "channels": [0, 8]}
RED = {"name": "red", "channels": [1, 9]}
YELLOW = {"name": "yellow", "channels": [1, 9], "micro_time_ranges": [[2048, 4094]]}


def test_a_partial_definition_names_the_missing_detector():
    with pytest.raises(ValueError, match="no definition for 'yellow'"):
        prepare_burst_folder(FOLDER, streams=[GREEN, RED])


def test_an_unknown_detector_is_refused():
    blue = {"name": "blue", "channels": [2]}
    with pytest.raises(ValueError, match="no detector named 'blue'"):
        prepare_burst_folder(FOLDER, streams=[GREEN, RED, YELLOW, blue])


def test_a_reordered_definition_is_aligned_by_name():
    prep = prepare_burst_folder(FOLDER, streams=[YELLOW, RED, GREEN])
    assert prep.channels == ("green", "red", "yellow")
    assert [s.name for s in prep.streams] == ["green", "red", "yellow"]
    assert prep.summary["stream_origin"] == "caller"
    assert prep.summary["count_agreement"] == {"green": 1.0, "red": 1.0, "yellow": 1.0}
