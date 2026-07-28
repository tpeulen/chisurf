"""RF-805: the NumPy BVA fallback must stay aligned to the burst frame.

A ``.bur`` frame is interleaved — every other row is a sentinel whose
``First File`` names no measurement — so the fallback skips roughly half the
rows. It used to *append* one value per processed row, which made the result
column shorter than the frame and raised on assignment (or, worse, silently
misaligned one burst's result onto another). The values must be addressed by
original row index, as the tttrlib path already does.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import tttrlib

from chisurf.plugins.burst.burst_bva.core.computation import compute_bva


class _Header:
    """Minimal stand-in for a ``tttrlib`` header exposing the time calibration."""

    @staticmethod
    def tag(name: str) -> dict:
        """Return the requested tag; only the global resolution is used here."""
        assert name == "MeasDesc_GlobalResolution"
        return {"value": 1e-8}


class _Tttr:
    """Minimal stand-in for a ``tttrlib.TTTR`` holding eight photons."""

    def __init__(self, routing_channels) -> None:
        self.routing_channels = np.asarray(routing_channels, dtype=np.int32)
        n = len(self.routing_channels)
        self.micro_times = np.zeros(n, dtype=np.int32)
        self.macro_times = np.arange(n, dtype=np.int64)
        self.header = _Header()


@pytest.fixture()
def interleaved_frame() -> pd.DataFrame:
    """Build an interleaved burst frame: two real bursts, two sentinel rows."""
    return pd.DataFrame(
        {
            "First File": ["m000.spc", "0", "m000.spc", "0"],
            "First Photon": [0, 0, 4, 0],
            "Last Photon": [4, 0, 8, 0],
        }
    )


def test_numpy_fallback_keeps_sentinel_rows(monkeypatch, interleaved_frame) -> None:
    """Rows whose file is absent keep the frame length and come back as NaN."""
    monkeypatch.delattr(tttrlib, "BVA", raising=False)
    tttrs = {"m000.spc": _Tttr([0, 1, 0, 1, 1, 1, 0, 1])}

    df = compute_bva(
        interleaved_frame,
        tttrs,
        donor_channels=[0],
        acceptor_channels=[1],
        number_of_photons_per_slice=2,
    )

    means = df["Proximity Ratio Mean"].to_numpy()
    stds = df["Proximity Ratio Std"].to_numpy()
    assert len(means) == len(interleaved_frame)
    # The two sentinel rows carry no result, and the two real bursts keep their
    # own row — a shifted result would put 0.75 on row 1.
    assert np.isnan(means[1]) and np.isnan(means[3])
    assert np.isnan(stds[1]) and np.isnan(stds[3])
    assert means[0] == pytest.approx(0.5)
    assert stds[0] == pytest.approx(0.0)
    assert means[2] == pytest.approx(0.75)
    assert stds[2] == pytest.approx(0.25)
