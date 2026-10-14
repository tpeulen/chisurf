"""Reading Becker & Hickl SDT files.

The reader was unusable: every ``measure_info`` field reads back as a
one-element record array, and modern NumPy refuses those where a scalar is
required, so opening any SDT raised ``TypeError`` from ``np.arange``. These
tests open the repository's own SDT and check what came out, which is what
would have caught it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.sdtfile import SdtFile

_SDT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test"
    / "data"
    / "tcspc"
    / "BH_SDT"
    / "140507p.sdt"
)

pytestmark = pytest.mark.skipif(not _SDT.exists(), reason="SDT test data not present")


def test_an_sdt_file_opens_at_all():
    """The regression: reading any SDT used to raise from the time axis."""
    sdt = SdtFile(str(_SDT))
    assert len(sdt.data) > 0
    assert len(sdt.data) == len(sdt.times)


def test_every_block_has_a_decay_and_a_matching_time_axis():
    """Each data block carries counts and a time axis of the same length."""
    sdt = SdtFile(str(_SDT))
    for data, times in zip(sdt.data, sdt.times):
        data = np.asarray(data)
        assert data.ndim in (2, 3), f"unexpected block shape {data.shape}"
        assert times.ndim == 1
        assert data.shape[-1] == times.shape[0], "decay length must match the time axis"


def test_the_time_axis_is_monotonic_and_physical():
    """Micro-times run from zero upward over a nanosecond-scale window."""
    sdt = SdtFile(str(_SDT))
    times = sdt.times[0]
    assert times[0] == 0.0
    assert np.all(np.diff(times) > 0)
    # a TCSPC window is tens of nanoseconds, expressed in seconds
    assert 1e-9 < float(times[-1]) < 1e-6


def test_the_decays_carry_counts():
    """A file that parses but yields empty decays would be a silent failure."""
    sdt = SdtFile(str(_SDT))
    totals = [float(np.asarray(d).sum()) for d in sdt.data]
    assert all(t > 0 for t in totals), f"empty decay blocks: {totals}"


def test_this_file_is_a_point_measurement_not_an_image():
    """Documents what the fixture is, so an imaging assumption fails loudly."""
    sdt = SdtFile(str(_SDT))
    shapes = {np.asarray(d).shape for d in sdt.data}
    assert all(len(s) == 2 and s[0] == 1 for s in shapes), (
        f"expected single-curve blocks, got {shapes}"
    )


def test_measurement_info_follows_each_data_block_header():
    """A data block resolves its own descriptor rather than its positional index."""
    sdt = SdtFile(str(_SDT))
    for index, header in enumerate(sdt.block_headers):
        expected = sdt.measure_info[header.meas_desc_block_no]
        assert sdt.block_measure_info(index) is expected


def test_measurement_info_supports_reordered_or_shared_descriptors():
    """Measurement descriptors may be reused or ordered unlike the data blocks."""
    sdt = SdtFile.__new__(SdtFile)
    sdt.measure_info = [object(), object()]
    sdt.block_headers = np.array([(1,), (0,), (1,)], dtype=[("meas_desc_block_no", "i2")])

    assert sdt.block_measure_info(0) is sdt.measure_info[1]
    assert sdt.block_measure_info(1) is sdt.measure_info[0]
    assert sdt.block_measure_info(2) is sdt.measure_info[1]


def test_the_documented_import_is_the_maintained_reader():
    """``chisurf.core.fio.fluorescence.SdtFile`` once was a stale copy.

    The copy rejected every "Setup & Data" file and ignored the NumPy fixes, so
    the import the reference page shows could not open the repository's own SDT.
    """
    import chisurf.core.fio.fluorescence as fluorescence

    assert fluorescence.SdtFile is SdtFile
    sdt = fluorescence.SdtFile(_SDT)  # a pathlib.Path, not only a str
    assert len(sdt.data) == len(sdt.times) > 0
