"""The concatenated timeline behind the diagnostics' visible-window slider."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.gui import timeline


class _Header:
    def __init__(self, resolution_s):
        self.macro_time_resolution = resolution_s


class _Tttr:
    """The two attributes the timeline reads off a TTTR object."""

    def __init__(self, macro_times, resolution_s):
        self.macro_times = np.asarray(macro_times)
        self.header = _Header(resolution_s)


def _diagnostics(n_files=3, per_file=1000, duration_s=10.0):
    """``n_files`` files of ``per_file`` photons, evenly spaced over ``duration_s``."""
    resolution_s = 1e-6
    ticks = np.linspace(0, duration_s / resolution_s, per_file).astype(np.int64)
    return [
        {
            "path": f"/tmp/file{index:03d}.ptu",
            "tttr": _Tttr(ticks, resolution_s),
            "selected": np.zeros(per_file, dtype=bool),
        }
        for index in range(n_files)
    ]


def _offsets(n_files, duration_s):
    """File starts on the shared timeline, in ms — files laid end to end."""
    return [index * duration_s * 1000.0 for index in range(n_files)]


def test_span_is_the_whole_measurement():
    segments = timeline.build_timeline(_diagnostics(), _offsets(3, 10.0))
    assert len(segments) == 3
    assert timeline.span(segments) == pytest.approx(30.0, abs=0.1)


def test_a_ten_second_window_selects_one_files_photons():
    segments = timeline.build_timeline(_diagnostics(), _offsets(3, 10.0))
    first, last = timeline.photon_range(segments, 10.0, 20.0)
    # The second file is photons 1000..1999. The window starts exactly on the
    # boundary, where the previous file's last photon also sits, so it is taken
    # too -- the window is closed at both ends and that photon really is at
    # 10.0 s. The upper edge behaves the same way. One photon of overlap per
    # boundary, symmetric, and never a whole file.
    assert (first, last) == (999, 2000)


def test_a_window_inside_one_file_is_a_slice_of_it():
    segments = timeline.build_timeline(_diagnostics(), _offsets(3, 10.0))
    first, last = timeline.photon_range(segments, 2.0, 4.0)
    # Photons are evenly spaced, so 2-4 s of a 10 s file is a fifth of it.
    assert first == pytest.approx(200, abs=2)
    assert last == pytest.approx(400, abs=2)


def test_the_window_never_leaves_the_photon_range():
    segments = timeline.build_timeline(_diagnostics(), _offsets(3, 10.0))
    first, last = timeline.photon_range(segments, 0.0, 1e9)
    assert first == 0
    assert last == 3 * 1000 - 1


def test_the_position_names_the_file_under_it():
    segments = timeline.build_timeline(_diagnostics(), _offsets(3, 10.0))
    assert timeline.locate(segments, 0.0).name == "file000.ptu"
    assert timeline.locate(segments, 15.0).name == "file001.ptu"
    assert timeline.locate(segments, 25.0).name == "file002.ptu"
    # Past the end: the nearest file, rather than nothing.
    assert timeline.locate(segments, 1e6).name == "file002.ptu"


def test_an_empty_selection_has_no_timeline():
    assert timeline.build_timeline([], []) == []
    assert timeline.span([]) == 0.0
    assert timeline.photon_range([], 0.0, 10.0) == (0, 0)
    assert timeline.locate([], 0.0) is None


def test_a_file_with_no_photons_does_not_shift_the_indices():
    diagnostics = _diagnostics(2)
    diagnostics.insert(1, {"path": "/tmp/empty.ptu",
                           "tttr": _Tttr([], 1e-6),
                           "selected": np.zeros(0, dtype=bool)})
    segments = timeline.build_timeline(diagnostics, [0.0, 10.0, 10.0])
    assert [s.first_photon for s in segments] == [0, 1000]
