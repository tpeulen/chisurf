"""Burst fusion runs the shared excitation-window check on the photons it regenerates bursts from.

The simulated PIE demo of Excitation Windows (32 ps, pulses at 2 and 52 ns) holds a burst run in
its analysis container. Fused with the windows of another instrument, the result carries the
warning and the detected windows; with matching windows it carries none; a donor-only measurement
gives the note, not a warning. Estimate offers the detected windows and the user takes them.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings  # noqa: E402
from chisurf.plugins.burst.burst_fusion.core.fusion import fuse_folder  # noqa: E402

DETECTORS = {"green": {"chs": [0], "micro_time_ranges": []},
             "red": {"chs": [1], "micro_time_ranges": []}}
WRONG = {"prompt": [0, 2048], "delayed": [2048, 4095]}
RIGHT = {"prompt": [50, 1613], "delayed": [1613, 3125]}
RUN = "search"


def _burst_run(ptu, out_dir) -> str:
    """A burst run of *ptu*'s analysis container: closely spaced bursts, so fusion has work."""
    import tttrlib

    from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    tttr = tttrlib.TTTR(str(ptu))
    n = len(tttr)
    starts = np.linspace(100, n - 2000, 60).astype(int)
    intervals = [(int(s), int(s) + 400) for s in starts]
    bursts = generate_burst_dataframe(
        intervals, str(ptu), tttr, windows=RIGHT, detectors=DETECTORS,
        include_interleaved_zeros=False,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    container = write_container(ptu, bursts, parameters={"search": 1}, out_dir=out_dir, run=RUN,
                                raw_data="sidecar")
    return f"{container}/{RUN}"


@pytest.fixture
def pie_run(tmp_path):
    from chisurf.plugins.core.excitation_windows.demo import make_demo

    return _burst_run(make_demo(tmp_path / "data"), tmp_path / "analysis")


@pytest.fixture
def donor_only_run(tmp_path):
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream(n_photons=100_000)
    routing = np.asarray(routing)
    keep = ~((routing == 1) & (micro.astype(float) * d.RESOLUTION_S > 51e-9))  # no acceptor pulse
    path = tmp_path / "data" / "donor_only.ptu"
    path.parent.mkdir(parents=True)
    cfg = demo_lib.config(macro_resolution_s=d.MACRO_S, micro_resolution_s=d.RESOLUTION_S,
                          n_micro=d.N_MICRO)
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], routing[keep])
    return _burst_run(path, tmp_path / "analysis")


def _fuse(run, windows):
    return fuse_folder(run, FusionSettings(threshold=0.5), detectors=DETECTORS, windows=windows)


def test_wrong_windows_are_reported_in_the_result(pie_run):
    result = _fuse(pie_run, WRONG)
    assert any("PIE windows do not match" in w for w in result["warnings"]), result["warnings"]
    assert "prompt 50–1613" in result["warnings"][0]


def test_matching_windows_say_nothing(pie_run):
    assert _fuse(pie_run, RIGHT)["warnings"] == []


def test_a_donor_only_measurement_gives_a_note_not_a_warning(donor_only_run):
    warnings = _fuse(donor_only_run, WRONG)["warnings"]
    assert len(warnings) == 1 and "One excitation pulse" in warnings[0], warnings
    assert "do not match" not in warnings[0]


def test_estimate_offers_the_detected_windows(pie_run):
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    model = FusionViewModel()
    model.detectors, model.windows = dict(DETECTORS), dict(WRONG)
    model.set_folder(pie_run)
    model.analyze()
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    assert "do not match" in model.status_text()
    assert model.use_detected_windows()
    assert model.windows_check_quiet and not model.windows_check_offer
    assert model.windows["prompt"][0] < 2e-9 / 32e-12 < model.windows["prompt"][1]
    assert model.windows["delayed"][0] < 52e-9 / 32e-12 < model.windows["delayed"][1]
    # The taken windows are what the writer now regenerates with: nothing left to warn about.
    model.write()
    assert "Warning" not in model._status
    assert model.check_windows() is None


def test_the_editor_shows_the_taken_windows(pie_run):
    import json

    from chisurf.plugins.burst.burst_fusion.gui.controller import FusionController
    from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

    model = FusionViewModel()
    model.detectors, model.windows = dict(DETECTORS), dict(WRONG)
    controller = FusionController(model)
    model.set_folder(pie_run)
    model.analyze()
    model.use_detected_windows()
    controller.sync_channel_text()
    assert json.loads(controller.channel_text)["windows"] == model.windows
    controller.close()
