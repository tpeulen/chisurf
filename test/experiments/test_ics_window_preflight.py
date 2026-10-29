"""The ICS reader holds the micro-time ranges it fills a TTTR stack through against the data.

The scan is the confocal PIE scan of the FRC pre-flight tests (32 ps, 3125 channels, pulses at 2
and 52 ns, donor on routing 0). A range made for another instrument puts the line in the curve's
``meta_data['warnings']`` and offers the detected gate on the reader (the reader form shows both);
a range that holds the pulse, no range, a donor-only scan and a TIFF stack say nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.experiments.ics import ICSReader  # noqa: E402
from chisurf.plugins.microscopy.img_frc.test.test_window_preflight import pie_scan  # noqa: E402


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    return str(pie_scan(tmp_path_factory.mktemp("scan") / "pie_scan.ptu"))


def _read(path, ranges, channels=(0, 5)):
    reader = ICSReader(channel=0, micro_time_ranges=ranges)
    reader.channel_numbers = list(channels)  # the stack of both detectors: both pulses are seen
    group = reader.read(path)
    return reader, group[0].meta_data


def test_a_range_of_another_instrument_warns_and_is_offered(scan):
    reader, meta = _read(scan, [[2048, 4095]])
    assert len(meta["warnings"]) == 1 and "do not match the data" in meta["warnings"][0]
    assert reader.windows_check_offer and not reader.windows_check_quiet
    assert reader.use_detected_windows()
    ((lo, hi),) = reader.micro_time_ranges
    assert lo <= 2e-9 / 32e-12 < hi
    meta = reader.read(scan)[0].meta_data
    assert meta["warnings"] == [] and reader.windows_check_quiet


def test_a_range_that_holds_the_pulse_and_no_range_say_nothing(scan, tmp_path):
    assert _read(scan, [[0, 3124]])[1]["warnings"] == []
    assert _read(scan, None)[1]["warnings"] == []
    donor = str(pie_scan(tmp_path / "donor_only.ptu", donor_only=True))
    assert _read(donor, [[0, 1612]])[1]["warnings"] == []


@pytest.mark.xfail(
    strict=True,
    reason="a detector that sees one pulse (the donor channel alone) and a gate leaving it out: "
    "check_setup finds gate_misses_pulse and offers the gate, but windows_message says nothing "
    "for a non-alternating detection (excitation/preflight.py), so the offer stands without its "
    "line; flips to a pass when the message names a gate that misses the only pulse",
)
def test_a_gate_that_misses_the_only_pulse_a_detector_sees_warns(scan):
    reader, meta = _read(scan, [[2048, 4095]], channels=(0,))
    assert reader.windows_check_offer
    assert len(meta["warnings"]) == 1


def test_a_tiff_stack_is_not_checked(tmp_path):
    import tifffile

    path = tmp_path / "stack.tif"
    tifffile.imwrite(
        str(path),
        np.random.default_rng(0).poisson(5, (4, 32, 32)).astype(np.uint16),
        photometric="minisblack",
    )
    reader, meta = _read(str(path), [[2048, 4095]])
    assert meta["warnings"] == [] and reader.windows_check is None


def test_the_check_is_not_serialised():
    reader = ICSReader(micro_time_ranges=[[0, 10]])
    reader.windows_check = object()
    assert "windows_check" not in reader._reader_settings_dict()
    assert "_windows_check" not in reader._reader_settings_dict()
