"""MFD Prepare runs the shared excitation-window pre-flight on the detector gates it applies.

The simulated PIE demo of Excitation Windows (32 ps, 3125 channels, pulses at 2 and 52 ns; routing
0 donor, 1 acceptor) prepared with the gates of another instrument carries the warning in its
result, its report and the window's status line; with gates that hold the pulses it carries none;
a donor-only measurement gives the note. The gates are reported only -- the bursts were selected
with them -- so the window offers no replacement.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.burst.photons import StreamDef  # noqa: E402
from chisurf.plugins.burst.mfd_prepare.api.prepare import window_warnings  # noqa: E402
from chisurf.plugins.core.excitation_windows.demo import make_demo  # noqa: E402

PROMPT_DELAYED = {"prompt": [50, 1613], "delayed": [1613, 3125]}
WRONG = {"prompt": [0, 2048], "delayed": [2048, 4095]}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("demo"))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    """The demo without its acceptor pulse: routing-1 photons after 51 ns dropped."""
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream(n_photons=100_000)
    keep = ~((routing == 1) & (micro.astype(float) * d.RESOLUTION_S * 1e9 > 51.0))
    path = tmp_path_factory.mktemp("donly") / "donor_only.ptu"
    cfg = demo_lib.config(macro_resolution_s=d.MACRO_S, micro_resolution_s=d.RESOLUTION_S,
                          n_micro=d.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], np.asarray(routing)[keep])
    return path


def _prep(path, streams, folder):
    """A preparation as prepare_burst_folder leaves it, reduced to what the pre-flight reads."""
    return SimpleNamespace(
        streams=tuple(streams),
        summary={"_tttrs": {"demo": tttrlib.TTTR(str(path))}},
        folder=Path(folder),
        file_key=np.array(["demo"], dtype=object),
    )


def _manifest(folder: Path, windows: dict) -> None:
    from chisurf.core.fio.fluorescence.burst_manifest import write_analysis_manifest

    write_analysis_manifest(folder, [{"path": "demo", "settings": {"windows": windows}}])


def test_gates_of_another_instrument_are_reported(demo, tmp_path):
    _manifest(tmp_path, WRONG)
    streams = [StreamDef("green", [0], [(2048, 4094)]), StreamDef("red", [1], [(0, 2047)])]
    warnings = window_warnings(_prep(demo, streams, tmp_path))
    assert len(warnings) == 1 and "do not match the data" in warnings[0], warnings
    assert "1613" in warnings[0]  # the detected windows are named


def test_gates_that_hold_the_pulses_say_nothing(demo, tmp_path):
    _manifest(tmp_path, PROMPT_DELAYED)
    streams = [StreamDef("green", [0], [(0, 1612)]), StreamDef("red", [1], [])]
    assert window_warnings(_prep(demo, streams, tmp_path)) == []


def test_the_canonical_pie_split_of_the_acceptor_says_nothing(demo, tmp_path):
    _manifest(tmp_path, PROMPT_DELAYED)
    streams = [
        StreamDef("green", [0], [(0, 1612)]),
        StreamDef("red", [1], [(0, 1612)]),
        StreamDef("yellow", [1], [(1613, 3124)]),
    ]
    assert window_warnings(_prep(demo, streams, tmp_path)) == []


def test_ungated_detectors_are_not_checked(demo, tmp_path):
    streams = [StreamDef("green", [0], []), StreamDef("red", [1], [])]
    assert window_warnings(_prep(demo, streams, tmp_path)) == []


def test_a_donor_only_measurement_gives_the_note(donor_only, tmp_path):
    _manifest(tmp_path, WRONG)
    streams = [StreamDef("green", [0], [(0, 1612)]), StreamDef("red", [1], [])]
    warnings = window_warnings(_prep(donor_only, streams, tmp_path))
    assert len(warnings) == 1 and "One excitation pulse" in warnings[0], warnings


def test_the_window_shows_the_warning_and_offers_no_replacement(demo, tmp_path):
    from chisurf.plugins.burst.mfd_prepare.gui.client import MfdPrepareClient
    from chisurf.plugins.burst.mfd_prepare.gui.model import MfdPrepareModel

    _manifest(tmp_path, WRONG)
    streams = [StreamDef("green", [0], [(2048, 4094)]), StreamDef("red", [1], [(0, 2047)])]
    warning = window_warnings(_prep(demo, streams, tmp_path))[0]

    class Rpc:
        def call(self, method, params):
            return {"ok": True, "result": {"report": "prepared", "n_bursts": 3, "channels": ["green"],
                                           "verified_channels": ["green"], "summary": {},
                                           "warnings": [warning]}}

    model = MfdPrepareModel(client=MfdPrepareClient(rpc_client=Rpc()))
    model.folder = str(tmp_path)
    model.prepare()
    assert model.windows_check_text() == warning and not model.windows_check_quiet
    assert warning.split(":")[0] + " (see below)" in model.status_text
    assert not hasattr(model, "use_detected_windows")
