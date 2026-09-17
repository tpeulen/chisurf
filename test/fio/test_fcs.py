"""FCS metadata and the correlator.com SIN reader."""
from __future__ import annotations

import pathlib

import pytest

from chisurf.core.fluorescence.fcs.normalization import resolve_total_mean_count_rate


def test_resolve_total_rate_prefers_explicit_total() -> None:
    meta = {
        "mean_count_rate_total": 120.0,
        "mean_count_rate": 60.0,
        "mean_count_rate_semantics": "per_detector_mean",
        "detector_count": 2,
    }
    assert resolve_total_mean_count_rate(meta) == pytest.approx(120.0)


def test_resolve_total_rate_from_per_detector_semantics() -> None:
    meta = {
        "mean_count_rate": 55.0,
        "mean_count_rate_semantics": "per_detector_mean",
        "detector_count": 2,
    }
    assert resolve_total_mean_count_rate(meta) == pytest.approx(110.0)


def test_resolve_total_rate_falls_back_to_mean_rate() -> None:
    meta = {
        "mean_count_rate": 42.0,
    }
    assert resolve_total_mean_count_rate(meta) == pytest.approx(42.0)


def test_resolve_total_rate_returns_none_for_invalid_meta() -> None:
    assert resolve_total_mean_count_rate({}) is None
    assert resolve_total_mean_count_rate({"mean_count_rate": "nan"}) is None
    assert resolve_total_mean_count_rate(None) is None


import chisurf as cs
import chisurf.core.fio.fluorescence.fcs as fcs_io
import chisurf.core.fio.fluorescence.fcs.sin_correlator as sin_reader


DATA_ROOT = pathlib.Path(__file__).parent / "data" / "fcs"
if DATA_ROOT.is_dir():
    SIN_FILES = list(DATA_ROOT.rglob("*.sin"))
else:
    SIN_FILES = []

# If no correlator.com SIN example files are available in the test data
# directory, leave the SIN reader effectively untested but do not fail the
# test suite.
_needs_sin_files = pytest.mark.skipif(
    len(SIN_FILES) == 0,
    reason="No correlator.com .sin test files found; SIN reader left untested.",
)


def _assert_fcs_dataset_dict(ds: dict) -> None:
    """Lightweight structural checks for a FCSDataset-style dict.

    This intentionally does not check numerical values, only that required
    keys are present and array-like fields have consistent lengths.
    """

    required_keys = [
        "filename",
        "measurement_id",
        "acquisition_time",
        "mean_count_rate",
        "correlation_times",
        "correlation_amplitudes",
        "correlation_amplitude_weights",
    ]
    for key in required_keys:
        assert key in ds, f"missing key '{key}' in FCSDataset"

    t = ds["correlation_times"]
    g = ds["correlation_amplitudes"]
    w = ds["correlation_amplitude_weights"]
    assert len(t) == len(g) == len(w)


@_needs_sin_files
def test_read_sin_low_level() -> None:
    """Low-level reader should return a non-empty list of FCSDataset dicts."""

    fn = SIN_FILES[0]
    ds_list = sin_reader.read_sin(str(fn), verbose=False)

    assert isinstance(ds_list, list)
    assert ds_list, "read_sin should return at least one dataset"

    for ds in ds_list:
        _assert_fcs_dataset_dict(ds)


@_needs_sin_files
def test_read_sin_via_read_fcs_dispatcher() -> None:
    """High-level read_fcs dispatcher should wrap SIN datasets into DataCurves."""

    fn = SIN_FILES[0]
    group = fcs_io.read_fcs(filename=str(fn), reader_name="sin")

    # Expect some curves in the ExperimentDataCurveGroup.
    data = getattr(group, "data", None)
    assert data is not None
    assert len(data) > 0

    for curve in data:
        # DataCurve should at least have x, y, ey arrays of matching length.
        assert hasattr(curve, "x")
        assert hasattr(curve, "y")
        assert hasattr(curve, "ey")
        n = curve.x.size
        assert n > 0
        assert curve.y.size == n
        assert curve.ey.size == n
