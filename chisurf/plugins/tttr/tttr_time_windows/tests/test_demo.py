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
    result = analyze_files_handler([str(path)], time_window_ms=50.0)
    assert result.get("ok", True), result
    return path, result


def test_a_40_s_measurement_cuts_into_50_ms_windows(example):
    """800 windows of 50 ms cover the whole demonstration stream, in the .pto."""
    from chisurf.core.datastore import row_count
    from chisurf.core.fio.fluorescence.burst_tree import list_runs, read_burst_table

    path, result = example
    payload = result.get("result", {})
    n_windows = payload["n_windows"][str(path)]
    assert n_windows == 800
    container = path.with_suffix(".pto")
    assert container.is_file(), payload.get("output_paths")
    runs = list_runs(container)
    assert any("time_window 50 ms" in run for run in runs), runs
    table = read_burst_table(container)
    assert table is not None and row_count(table) == 800


def test_a_shorter_window_yields_more_windows(example):
    """The window duration actually controls the cut."""
    path, _ = example
    result = analyze_files_handler([str(path)], time_window_ms=25.0)
    assert result.get("result", {})["n_windows"][str(path)] == 1600
