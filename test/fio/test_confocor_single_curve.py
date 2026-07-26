"""The single-curve ConfoCor branch had been dead since the Python 3 port.

``openFCS`` dispatches to ``openFCS_Single`` for every ``.fcs`` file whose
first line is not ``Carl Zeiss ConfoCor3`` -- ConfoCor2 and older AIM exports.
That function sliced its line list with ``list.__getslice__``, a Python 2
method removed in Python 3, so both the trace and the correlogram import
raised ``AttributeError`` the moment they were reached. Every committed
ConfoCor sample carries the multi-curve header, which is why no test noticed.

A section announced with ``##NPOINTS = 0`` used to leave ``newtrace``/``corr``
undefined and fail with ``NameError`` instead of naming the malformed file.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.fcs.confocor3 import openFCS, read_zeiss_fcs

# The single-curve layout the parser expects: "##NPOINTS" directly below the
# "##DATA TYPE" line, count-rate values three lines below "##NPOINTS" and
# correlogram values two lines below it.
HEADER = "Carl Zeiss - ConfoCor2 - measurement data file\n##TITLE = Single curve\n"

TRACE = [(0.0, 10.0), (0.5, 12.0), (1.0, 14.0), (1.5, 16.0)]
CORRELOGRAM = [(1e-3, 1.4), (1e-2, 1.3), (1e-1, 1.15), (1.0, 1.02), (10.0, 1.0)]


def _write_single_curve(path: pathlib.Path, trace=TRACE, correlogram=CORRELOGRAM):
    """Write a minimal single-curve ConfoCor file and return its path.

    Parameters
    ----------
    path : pathlib.Path
        File to write.
    trace : list of tuple
        ``(time / s, count rate / kHz)`` pairs; an empty list writes a
        section announcing ``##NPOINTS = 0``.
    correlogram : list of tuple
        ``(lag time / ms, G)`` pairs, likewise.

    Returns
    -------
    pathlib.Path
        The path that was written.
    """
    lines = [HEADER]
    lines.append("##DATA TYPE = FCS Count Rates\n")
    lines.append(f"##NPOINTS = {len(trace)}\n")
    lines.append("##XUNITS = Time [s]\n")
    lines.append("##YUNITS = Count Rate [kHz]\n")
    lines += [f"{x},{y}\n" for x, y in trace]
    lines.append("##DATA TYPE = FCS Correlogram\n")
    lines.append(f"##NPOINTS = {len(correlogram)}\n")
    lines.append("##XUNITS = Time [ms]\n")
    lines += [f"{x},{y}\n" for x, y in correlogram]
    lines.append("##END =\n")
    path.write_text("".join(lines), encoding="iso8859_15")
    return path


def test_single_curve_file_loads(tmp_path):
    """A single-curve file parses into one correlogram and one trace.

    The regression: this raised ``AttributeError: 'list' object has no
    attribute '__getslice__'`` before anything was parsed.
    """
    d = openFCS(_write_single_curve(tmp_path / "confocor2.fcs"))

    assert len(d["Correlation"]) == 1
    assert len(d["Trace"]) == 1
    # tau in ms and G - 1, exactly as stored.
    np.testing.assert_allclose(d["Correlation"][0][:, 0], [t for t, _ in CORRELOGRAM])
    np.testing.assert_allclose(d["Correlation"][0][:, 1], [g - 1.0 for _, g in CORRELOGRAM])
    # The trace is short enough not to be down-sampled; times are in ms.
    np.testing.assert_allclose(d["Trace"][0][:, 0], [t * 1000 for t, _ in TRACE])
    np.testing.assert_allclose(d["Trace"][0][:, 1], [c for _, c in TRACE])


def test_single_curve_reaches_a_dataset(tmp_path):
    """The reader on top of the parser produces a usable weighted curve."""
    path = _write_single_curve(tmp_path / "confocor2.fcs")
    records = read_zeiss_fcs(str(path))

    assert len(records) == 1
    record = records[0]
    # read_zeiss_fcs adds the 1.0 back to the correlation amplitude.
    np.testing.assert_allclose(record["correlation_amplitudes"], [g for _, g in CORRELOGRAM])
    # Mean of the trace in kHz, and the acquisition time in seconds.
    assert record["mean_count_rate"] == pytest.approx(13.0)
    assert record["acquisition_time"] == pytest.approx(1.5)
    assert np.all(np.isfinite(record["correlation_amplitude_weights"]))


@pytest.mark.parametrize(
    "trace, correlogram, expected",
    [
        (TRACE, [], "FCS Correlogram"),
        ([], CORRELOGRAM, "FCS Count Rates"),
    ],
)
def test_empty_section_reports_a_malformed_file(tmp_path, trace, correlogram, expected):
    """An empty section names the file instead of raising ``NameError``."""
    path = _write_single_curve(tmp_path / "confocor2.fcs", trace=trace, correlogram=correlogram)
    with pytest.raises(SyntaxError, match=expected):
        openFCS(path)
