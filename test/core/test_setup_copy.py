"""A detector setup is copied without its micro-time previews, and signed by their fingerprint.

The burst workflow copies its setup dozens of times (every hand-off, every hosted editor, every
``get_settings``); the two per-channel micro-time previews are ~1.3 MB of JSON of the setup's
~1.4 MB, and deep-copying them was most of a copy (0.1-0.5 s each, ~20 s of the UI thread over
one pipeline run). They are display data, replaced whole and never edited in place, so copies
share them.
"""

import copy
import json

import numpy as np

from chisurf.core.setup_channel_definition import (
    PREVIEW_KEYS,
    ChannelDefinition,
    copy_setup,
    setup_signature,
    with_detector_names,
)


def _setup(n_channels=4, n_bins=256):
    rng = np.random.default_rng(1)
    preview = {
        "file_path": "/data/m.ptu",
        "channels": {str(c): rng.random(n_bins).tolist() for c in range(n_channels)},
    }
    return {
        "setup_name": "S",
        "detectors": {"G|G": {"chs": [0, 1], "micro_time_ranges": [[0, 100]], "g_factor": 1.0}},
        "windows": {"prompt": [0, 100]},
        "tttr_reading": {"file_type": "auto", "macro_time_resolution": 1e-8,
                         "micro_time_resolution": 1e-11, "micro_time_binning": 1},
        "channel_luts": {"0": [0.1, 0.2]},
        "optical_config": {"detectors": [{"name": "G|G"}]},
        PREVIEW_KEYS[0]: preview,
        PREVIEW_KEYS[1]: copy.deepcopy(preview),
    }


def test_copy_equals_deepcopy_and_shares_only_the_previews():
    data = _setup()
    copied = copy_setup(data)
    assert copied == copy.deepcopy(data)
    for key in PREVIEW_KEYS:
        assert copied[key] is data[key]
    for key in set(data) - set(PREVIEW_KEYS):
        if isinstance(data[key], (dict, list)):
            assert copied[key] is not data[key]
    copied["detectors"]["G|G"]["chs"].append(9)
    assert data["detectors"]["G|G"]["chs"] == [0, 1]


def test_get_settings_and_detector_names_are_private_copies():
    data = _setup()
    renamed, _changed = with_detector_names(data)
    assert renamed == copy.deepcopy(data)
    model = ChannelDefinition(data)
    settings = model.get_settings()
    settings["detectors"]["G|G"]["g_factor"] = 2.0
    settings["windows"]["prompt"][1] = 7
    again = model.get_settings()
    assert again["detectors"]["G|G"]["g_factor"] == 1.0
    assert again["windows"]["prompt"] == [0, 100]
    assert again[PREVIEW_KEYS[0]] == data[PREVIEW_KEYS[0]]


def test_signature_tells_revisions_apart():
    data = _setup()
    same = copy.deepcopy(data)
    assert setup_signature(data) == setup_signature(same)
    edited = copy.deepcopy(data)
    edited["detectors"]["G|G"]["g_factor"] = 1.1
    assert setup_signature(edited) != setup_signature(data)
    reread = copy.deepcopy(data)
    reread[PREVIEW_KEYS[0]]["channels"]["0"][3] += 5.0
    assert setup_signature(reread) != setup_signature(data)
    moved = copy.deepcopy(data)  # counts moved between bins (a LUT): same total, other preview
    counts = moved[PREVIEW_KEYS[0]]["channels"]["1"]
    counts[0], counts[1] = counts[1], counts[0]
    assert setup_signature(moved) != setup_signature(data)
    other_file = copy.deepcopy(data)
    other_file[PREVIEW_KEYS[1]]["file_path"] = "/data/n.ptu"
    assert setup_signature(other_file) != setup_signature(data)
    # arrays (LUTs) enter by value, and a setup without previews signs as plain JSON
    with_array = {"channel_luts": {"0": np.arange(3.0)}}
    assert json.loads(setup_signature(with_array)) == {"channel_luts": {"0": [0.0, 1.0, 2.0]}}
