"""A dual-channel ALV-7004 file (two AC + two CC curves) must be readable.

In mode ``a-ch0+1  c-ch0/1+1/0`` the reader collects one trace per
autocorrelation and a *pair* of traces per cross-correlation, so the trace list
is ragged. Packing it into `np.array` raised `ValueError: setting an array
element with a sequence` from NumPy 1.24 on, which made every FCCS measurement
from this instrument unopenable. The list must stay a plain Python list — that
is what `openASC_old` returns and what `read_asc` branches on.

The second half of the contract is that the traces come back in seconds *once*:
the autocorrelation branch of `read_asc` hands out a view into the reader's own
trace array, and the same array is reused for the cross-correlation curves, so
an in-place conversion would scale those by 1e-6 instead of 1e-3.
"""

from __future__ import annotations

import pathlib

import numpy as np

FCS_ASC = pathlib.Path(__file__).parent.parent / "data" / "fcs" / "asc"

DUAL_CHANNEL = FCS_ASC / "ALV-7004USB_ac01_cc01_10.ASC"

#: ``Duration [s] :	30.00000`` in the file header.
DURATION_S = 30.0


def test_dual_channel_file_opens():
    """The four-curve FCCS mode parses instead of raising on a ragged array."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import openASC

    d = openASC(DUAL_CHANNEL)

    assert d["Type"] == ["AC1", "AC2", "CC12", "CC21"]
    assert d["Duration"] == DURATION_S


def test_trace_list_stays_a_list_of_ragged_entries():
    """Autocorrelations carry one trace, cross-correlations carry a pair."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import openASC

    traces = openASC(DUAL_CHANNEL)["Trace"]

    assert isinstance(traces, list)
    # `read_asc` dispatches on exactly this distinction.
    assert not isinstance(traces[0], list)
    assert not isinstance(traces[1], list)
    assert isinstance(traces[2], list) and len(traces[2]) == 2
    assert isinstance(traces[3], list) and len(traces[3]) == 2

    n_points = traces[0].shape[0]
    for pair in traces[2:]:
        for trace in pair:
            assert trace.shape == (n_points, 2)


def test_read_asc_returns_four_datasets_with_traces_in_seconds():
    """Every curve's trace spans the measurement, and none is scaled twice."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import read_asc

    datasets = read_asc(DUAL_CHANNEL)

    assert len(datasets) == 4
    for dataset in datasets:
        times = np.asarray(dataset["intensity_trace_times"])
        # A second in-place division would end the trace at 3e-2 s.
        assert 0.9 * DURATION_S < float(times.flat[-1]) <= DURATION_S
        assert float(times.flat[0]) > 0.0
        assert np.all(np.isfinite(dataset["correlation_amplitude_weights"]))

    # The two cross-correlations carry a trace per channel, the two
    # autocorrelations a single one.
    shapes = [np.asarray(d["intensity_trace_times"]).ndim for d in datasets]
    assert shapes == [1, 1, 2, 2]


def test_reader_does_not_mutate_its_own_trace_arrays():
    """Reading twice gives the same traces; the first read leaves no scaling behind."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import read_asc

    first = read_asc(DUAL_CHANNEL)
    second = read_asc(DUAL_CHANNEL)

    for a, b in zip(first, second):
        np.testing.assert_allclose(
            np.asarray(a["intensity_trace_times"]),
            np.asarray(b["intensity_trace_times"]),
        )
