"""The diagnostics are computed over the visible window, not the whole file.

Two invariants make this safe, and both are easy to break:

1. the returned arrays keep their **full length** — every index downstream is a
   global photon index, so a shortened array silently moves all of them;
2. the window's photon range is the one the slider asked for, at any position,
   not only at the start.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.gui.client import BurstSelectionClient


class _Header:
    def __init__(self, resolution_s):
        self.macro_time_resolution = resolution_s


class _Tttr:
    """A 300 s stream of evenly spaced photons."""

    def __init__(self, n=300_000, duration_s=300.0, resolution_s=1e-6):
        self.macro_times = np.linspace(0, duration_s / resolution_s, n).astype(np.int64)
        self.header = _Header(resolution_s)


_indices = BurstSelectionClient._window_indices


def test_no_window_means_the_whole_file():
    tttr = _Tttr()
    assert _indices(tttr, None) is None
    assert _indices(tttr, 0.0) is None


def test_a_window_longer_than_the_file_is_the_whole_file():
    tttr = _Tttr(duration_s=300.0)
    assert _indices(tttr, 600.0) is None


def test_the_first_window_starts_at_the_first_photon():
    tttr = _Tttr(n=300_000, duration_s=300.0)
    first, last = _indices(tttr, 10.0)
    assert first == 0
    # 10 s of a 300 s file with evenly spaced photons is a thirtieth of them.
    assert last == pytest.approx(10_000, abs=50)


@pytest.mark.parametrize("start_s", [0.0, 50.0, 150.0, 290.0])
def test_the_window_lands_where_the_slider_put_it(start_s):
    tttr = _Tttr(n=300_000, duration_s=300.0)
    first, last = _indices(tttr, 10.0, start_s)
    resolution_s = tttr.header.macro_time_resolution
    assert float(tttr.macro_times[first]) * resolution_s == pytest.approx(start_s, abs=0.01)
    assert last > first


def test_the_window_is_clamped_to_the_file():
    tttr = _Tttr(n=300_000, duration_s=300.0)
    first, last = _indices(tttr, 10.0, 299.0)
    assert last <= tttr.macro_times.size
    assert first < last


def test_a_window_past_the_end_is_still_a_valid_range():
    """Dragging the slider to the very end must not produce an inverted range."""
    tttr = _Tttr(n=300_000, duration_s=300.0)
    first, last = _indices(tttr, 10.0, 10_000.0)
    assert 0 <= first < last <= tttr.macro_times.size


def test_the_selection_stays_full_length(monkeypatch):
    """The invariant that keeps every global photon index valid."""
    from chisurf.plugins.burst.burst_selection.gui import client as client_module

    tttr = _Tttr(n=300_000, duration_s=300.0)

    class _Sliceable(_Tttr):
        def __getitem__(self, index):
            out = _Tttr(n=1)
            out.macro_times = self.macro_times[index]
            out.header = self.header
            return out

    sliceable = _Sliceable(n=300_000, duration_s=300.0)
    monkeypatch.setattr(client_module, "logger", client_module.logger)

    c = BurstSelectionClient.__new__(BurstSelectionClient)
    window = c._window_indices(sliceable, 10.0, 100.0)
    assert window is not None
    first, last = window
    # What load_diagnostics does with the slice: scatter into a full-length mask.
    sliced = np.ones(last - first, dtype=bool)
    selected = np.zeros(len(np.asarray(sliceable.macro_times)), dtype=bool)
    selected[first : first + len(sliced)] = sliced
    assert selected.size == 300_000
    assert selected[:first].sum() == 0
    assert selected[last:].sum() == 0
    assert selected.sum() == last - first
    del tttr


class _CountingTttr:
    """Counts how often the macro times are read: tttrlib copies all of them on every read."""

    def __init__(self, **kwargs):
        plain = _Tttr(**kwargs)
        self._times, self.header, self.reads = plain.macro_times, plain.header, 0

    @property
    def macro_times(self):
        self.reads += 1
        return self._times


def test_the_plots_read_the_window_once_not_every_frame():
    """Every frame keys the trace and dt curves on the window and asks the slider's range; that
    copied all 20 M macro times of a real file and searched them each time (~50 ms a frame)."""
    from types import SimpleNamespace

    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    tttr = _CountingTttr(n=300_000, duration_s=300.0)
    model = SimpleNamespace(
        diagnostic={"tttr": tttr, "selected": np.zeros(300_000, dtype=bool)},
        window_length_s=10.0,
        window_start_s=50.0,
        client=BurstSelectionClient,
    )
    window = BurstSelectionModel._window_indices(model)
    span = BurstSelectionModel.timeline_span(model)
    for _ in range(100):  # a hundred frames
        assert BurstSelectionModel._window_indices(model) == window
        assert BurstSelectionModel.timeline_span(model) == span
    assert tttr.reads == 2, "one read for the window, one for the span"
    model.window_start_s = 60.0  # the slider moved: read again, once
    moved = BurstSelectionModel._window_indices(model)
    assert moved != window and tttr.reads == 3
    assert span == pytest.approx(300.0, rel=1e-3)
