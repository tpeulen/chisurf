"""The Qt-free diagnostics of Burst Selection (``gui/diagnostics.py`` and ``gui/adapter.py``).

These functions were methods of the Qt ``BurstSelectionTool``; the tests that pinned them through
``BurstSelectionTool.__new__`` (``test_new_gui.py``, ``test_proximity_ratio_is_not_faked.py``) now call them directly.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from chisurf.core.datastore import column_names, numeric_column
from chisurf.plugins.burst.burst_selection.gui import diagnostics as diag
from chisurf.plugins.burst.burst_selection.gui.adapter import make_ui_dataframe


class _Header:
    """TTTR header stand-in."""

    def __init__(self, resolution: float = 0.001) -> None:
        self.macro_time_resolution = resolution


class _Tttr:
    """TTTR stand-in."""

    def __init__(self, macro_times, resolution: float = 0.001) -> None:
        self.header = _Header(resolution)
        self.macro_times = np.asarray(macro_times)


def test_macro_time_offsets_continue_across_file_boundaries() -> None:
    """Diagnostic macro times should continue at file boundaries instead of restarting."""
    tttr_a, tttr_b = _Tttr([10, 15, 30]), _Tttr([10, 15, 30])
    diagnostics = [
        {"tttr": tttr_a, "selected": np.ones(3, dtype=bool)},
        {"tttr": tttr_b, "selected": np.ones(3, dtype=bool)},
    ]
    offsets = diag.macro_time_offsets_ms(diagnostics)
    delta_b = diag.delta_macro_time_ms(tttr_b, offsets[1])

    assert offsets == [0.0, 20.0]
    assert delta_b.tolist() == [20.0, 5.0, 15.0]


def test_macro_time_offsets_accumulate_over_three_files() -> None:
    """File 3 continues from file 2's *continued* end, not its raw end.

    With the raw end, ten 642 s files showed as 126 s and files 2-10 overlapped;
    two identical files cannot tell the difference.
    """
    diagnostics = [
        {"tttr": _Tttr([10, 15, 30]), "selected": np.ones(3, dtype=bool)} for _ in range(3)
    ]
    assert diag.macro_time_offsets_ms(diagnostics) == [0.0, 20.0, 40.0]


def test_histogram_data_ignores_interleaved_zero_rows() -> None:
    """Histogram updates should ignore Margarita zero separator rows."""
    frame = pd.DataFrame(
        {"Number of Photons": [0, 10, 0, 20], "Proximity Ratio": [0.0, 0.1, 0.0, 0.3]}
    )
    assert diag.histogram_data_from_frame(frame, "Proximity Ratio").tolist() == [0.1, 0.3]


def test_histogram_data_for_a_plain_column_is_a_plain_array() -> None:
    """A non-Proximity-Ratio feature takes the generic numeric_column path.

    Regression: this used to end in `.to_numpy(dtype=float)` on a value `numeric_column` already returns as a plain
    `numpy.ndarray` (not a pandas Series) -- broken since `numeric_column` was written, but never caught because every
    other histogram test asks for "Proximity Ratio", which takes the early-return branch.
    """
    frame = pd.DataFrame(
        {"Number of Photons": [0, 10, 0, 20], "Proximity Ratio": [0.0, 0.1, 0.0, 0.3]}
    )
    result = diag.histogram_data_from_frame(frame, "Number of Photons")
    assert isinstance(result, np.ndarray)
    assert result.tolist() == [10.0, 20.0]


def test_make_ui_dataframe_computes_proximity_ratio() -> None:
    """The histogram feature list should include computed proximity ratios."""
    frame = pd.DataFrame(
        {"Number of Photons (red)": [0, 10, 30], "Number of Photons (green)": [0, 40, 70]}
    )
    ui_frame = make_ui_dataframe(frame)

    assert "Proximity Ratio" in column_names(ui_frame)
    assert np.round(numeric_column(ui_frame, "Proximity Ratio"), 6).tolist() == [0.2, 3 / 10]


def test_histogram_data_uses_computed_proximity_ratio() -> None:
    """Histogram data should use the computed proximity-ratio column."""
    frame = pd.DataFrame(
        {"Number of Photons (red)": [10, 30], "Number of Photons (green)": [40, 70]}
    )
    assert diag.histogram_data_from_frame(frame, "Proximity Ratio").tolist() == [0.2, 3 / 10]


def test_burst_durations_use_macro_time_resolution_ms() -> None:
    """Burst duration values should be reported in milliseconds."""
    entry = {
        "tttr": _Tttr([0, 5, 8, 20], resolution=0.002),
        "start_stop": np.array([[0, 1], [1, 3]]),
    }
    assert diag.burst_durations_ms(entry).tolist() == [10.0, 30.0]
    assert diag.burst_durations_ms({}).size == 0


def test_a_count_rate_is_a_rate_not_counts_per_bin() -> None:
    """The trace is drawn as a count *rate* in Hz, not as counts per bin.

    At a 0.25 ms bin width that is x 4000. Plotting counts made the y axis depend on a display setting, so the same
    burst read 80 at 0.25 ms and 40 at 0.125 ms and no threshold could be quoted against it.
    """
    assert diag.as_count_rate_hz([1.0, 2.0, 3.0], 0.25).tolist() == [4000.0, 8000.0, 12000.0]
    # an unusable bin width must not fill the trace with infinities
    assert diag.as_count_rate_hz([1.0, 2.0], 0.0).tolist() == [1.0, 2.0]

    class Slice:
        header = _Header(0.001)
        macro_times = np.array([0, 1, 2])

        def get_intensity_trace(self, time_window_length):
            assert time_window_length == 0.00025
            return np.array([1.0, 2.0, 3.0])

    time_s, rate = diag.trace_rate_hz(Slice(), 0.00025, 0.25, 0.0)
    assert rate.tolist() == [4000.0, 8000.0, 12000.0]
    assert time_s.tolist() == [0.0, 0.00025, 0.0005]


def test_a_windowed_trace_does_not_start_with_the_empty_run_in_front() -> None:
    """``get_intensity_trace`` bins from macro time zero, so a window taken at 65 s would come back 75 s long."""

    class Slice:
        header = _Header(1.0)  # one tick per second
        macro_times = np.array([5, 6, 7])

        def get_intensity_trace(self, time_window_length):
            return np.array([0, 0, 0, 0, 0, 4.0, 5.0, 6.0])

    time_s, rate = diag.trace_rate_hz(Slice(), 1.0, 1000.0, 0.0)
    assert rate.tolist() == [4.0, 5.0, 6.0]
    assert time_s.tolist() == [5.0, 6.0, 7.0], (
        "the trace stays where it belongs on the file's clock"
    )


def test_the_destination_follows_the_input() -> None:
    """`.pto` in, `.pto` out; anything else gets the companion folder."""
    decide = diag.output_formats_for_inputs
    assert decide([Path("m000.pto")]) == ["pto"]
    assert decide([Path("m000.spc")]) == ["bur"]
    # Each measurement still gets the one destination it can use.
    assert decide([Path("a.pto"), Path("b.ptu")]) == ["pto", "bur"]
    # Nothing loaded: the container, which is what a fresh panel should say.
    assert decide([]) == ["pto"]


def test_the_gate_mismatch_is_named() -> None:
    """The sentence that explains an all-zero table, rather than a silent one."""

    class _Unconverted:
        micro_times = np.zeros(1000, dtype=int)

    gated = {"green": {"chs": [1], "micro_time_ranges": [[616, 3784]]}}
    message = diag.gate_mismatch_warning(_Unconverted(), gated)
    assert message is not None and "micro-time" in message
    assert "Alternation" in message, "the message must say what to do about it"

    # A file that *has* a micro time is not warned about.
    assert diag.gate_mismatch_warning(SimpleNamespace(micro_times=np.arange(1000)), gated) is None
    # Nor is an ungated setup.
    assert diag.gate_mismatch_warning(_Unconverted(), {"green": {"chs": [1]}}) is None


def test_normalised_file_types_and_the_setup_summary() -> None:
    assert diag.normalize_filetype("auto") is None or isinstance(
        diag.normalize_filetype("auto"), str
    )
    assert diag.normalize_filetype(None) is None
    assert "SPC-130" in diag.setup_summary("probe", "SPC-130") and "probe" in diag.setup_summary(
        "probe", "SPC-130"
    )
