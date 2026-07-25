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

_SDT = pathlib.Path(__file__).resolve().parents[2] / "test" / "data" / "tcspc" / "BH_SDT" / "140507p.sdt"

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
