"""The time-window splitter demonstration stream drives the real plugin layer with known answers.

The photons come from the shared generator (``chisurf.plugins.tttr.demo_lib``):
a deterministic µs-ALEX measurement — donor (routing 0) and acceptor (routing 1)
detectors, single-molecule bursts over a weak background, micro times from
per-channel exponential decays that begin at each channel's rise bin — so every assertion below
is a property the generator put there on purpose.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.tttr.tttr_time_windows.backend.services import analyze_files_handler
from chisurf.plugins.tttr.tttr_time_windows.demo import make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the demonstration stream once for this module."""
    path = make_demo(tmp_path_factory.mktemp("time-windows-demo"))
    out = path.parent / "bids"
    result = analyze_files_handler([str(path)], time_window_ms=50.0, output_dir=str(out))
    assert result.get("ok", True), result
    return path, out, result


def test_a_40_s_measurement_cuts_into_50_ms_windows(example):
    """800 windows of 50 ms cover the whole demonstration stream."""
    path, out, result = example
    payload = result.get("result", {})
    n_windows = payload["n_windows"][str(path)]
    bst = sorted(out.rglob("*.bst"))
    assert n_windows == 800
    assert len(bst) == 1
    assert bst[0].stat().st_size > 0


def test_a_shorter_window_yields_more_windows(example):
    """The window duration actually controls the cut."""
    path, out, _ = example
    result = analyze_files_handler(
        [str(path)], time_window_ms=25.0, output_dir=str(out.parent / "bids25")
    )
    assert result.get("result", {})["n_windows"][str(path)] == 1600

