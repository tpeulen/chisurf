"""The decay histograms count emitted photons only.

The regression these guard: ``get_histogram``/``get_histogram_fret`` used to
histogram the whole photon trace. A photon lost to quenching or to transfer
comes back from ``_photon_rate_walk`` as ``dt = 0.0`` with its emitted flag
clear, so the unfiltered histogram piled every non-emitted photon into the
first bin. Both curves then totalled the *excitation* count whatever the
quantum yield -- the D--A curve carried no amplitude information at all, and
the plot opened with a ~300x spike on the log axis.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.quenching_estimator.core.dye_diffusion import DonorDecay

#: Three emitted photons at 1, 2 and 3 ns; two quenched ones at t = 0.
TRACE_DTS = np.array([1.0, 0.0, 2.0, 0.0, 3.0], dtype=np.float64)
TRACE_PHS = np.array([1, 0, 1, 0, 1], dtype=np.uint8)


def _histogram_of(trace_dts, trace_phs, fret=False):
    model = DonorDecay()
    if fret:
        model._photon_trace_fret = (trace_dts, trace_phs)
        return model.get_histogram_fret(nbins=10, range=(0, 10))
    model._photon_trace = (trace_dts, trace_phs)
    return model.get_histogram(nbins=10, range=(0, 10))


class TestTheDonorHistogramDropsNonEmittedPhotons:
    def test_the_total_is_the_emitted_count_not_the_excitation_count(self) -> None:
        _, y = _histogram_of(TRACE_DTS, TRACE_PHS)
        assert y.sum() == int(TRACE_PHS.sum()) == 3

    def test_the_first_bin_holds_no_quenched_photons(self) -> None:
        _, y = _histogram_of(TRACE_DTS, TRACE_PHS)
        assert y[0] == 0

    def test_the_emitted_photons_land_in_their_own_bins(self) -> None:
        x, y = _histogram_of(TRACE_DTS, TRACE_PHS)
        assert x[0] == 0.0 and x[-1] == 10.0
        np.testing.assert_array_equal(y, [0, 1, 1, 1, 0, 0, 0, 0, 0, 0])

    def test_a_genuine_zero_lifetime_photon_is_still_counted(self) -> None:
        """The filter is on the emitted flag, not on ``dt == 0``."""
        dts = np.array([0.0, 1.0], dtype=np.float64)
        phs = np.array([1, 1], dtype=np.uint8)
        _, y = _histogram_of(dts, phs)
        assert y[0] == 1 and y.sum() == 2


class TestTheFretHistogramDropsNonEmittedPhotons:
    def test_the_total_is_the_emitted_count(self) -> None:
        _, y = _histogram_of(TRACE_DTS, TRACE_PHS, fret=True)
        assert y.sum() == 3

    def test_the_first_bin_holds_no_transferred_photons(self) -> None:
        _, y = _histogram_of(TRACE_DTS, TRACE_PHS, fret=True)
        assert y[0] == 0

    def test_a_lower_quantum_yield_gives_a_smaller_curve(self) -> None:
        """The amplitude is the signal the spike used to destroy."""
        dts = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float64)
        bright = np.array([1, 1, 1, 1], dtype=np.uint8)
        dim = np.array([1, 0, 0, 0], dtype=np.uint8)
        _, y_bright = _histogram_of(dts, bright, fret=True)
        _, y_dim = _histogram_of(dts, dim, fret=True)
        assert y_bright.sum() == 4
        assert y_dim.sum() == 1
