"""Render ``fcs_toolbox_channels.png``: the FCS workflow on *1. Channel Definitions* with a two-detector setup.

The setup (Green = routing channels 0, 8; Red = 1, 9) and the preset file live in a temporary folder, so the
user's detector setups and presets are neither read nor written. Run from the repository root::

    CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/fcs_toolbox_channels.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emtk_shot import app_from, render  # noqa: E402

from chisurf.plugins.fcs.fcs_channel_preset.gui.view_model import FCSChannelViewModel  # noqa: E402


def main() -> None:
    """Add the two autocorrelations and the cross-correlation, then grab the step at 1280 x 800."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="fcs-channels-"))
    detectors = tmp / "detector_setups.json"
    setup = {
        "windows": {"prompt": [0, 4095]},
        "detectors": {
            "Green": {"chs": [0, 8], "micro_time_ranges": [[0, 4095]]},
            "Red": {"chs": [1, 9], "micro_time_ranges": [[0, 4095]]},
        },
    }
    detectors.write_text(json.dumps({"setups": {"MFD green/red": setup}}))
    hub = app_from("fcs_correlator")
    preset = hub.ensure_child("channel_def")
    preset.model = FCSChannelViewModel(
        detector_file=detectors, preset_file=tmp / "fcs_channel_setups.json"
    )
    preset.select_setup("MFD green/red")
    for a, b in (("Green", "Green"), ("Red", "Red"), ("Green", "Red")):
        preset.channel_a, preset.channel_b, preset.pair_name = a, b, ""
        preset.add_pair()
    hub.select("channel_def")
    render(hub, "fcs_toolbox_channels.png", size=(1280, 800))


if __name__ == "__main__":
    main()
    os._exit(0)
