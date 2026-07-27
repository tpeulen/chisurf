"""The fine lag axis is scaled by the micro-time resolution.

Regression tests for RF-503: ``correlate_single_burst`` used to build the fine
axis by *dividing* the macro-time axis by the micro-time resolution instead of
scaling the correlator's own axis by it, which put every lag time (and every
fitted diffusion time) off by ``macro_res * 1e6 / micro_res**2`` — a factor of
3e19 for the shipped Becker & Hickl file.
"""

import pathlib

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
TTTR_FILE = REPO_ROOT / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not TTTR_FILE.exists(), reason="TTTR test file not available")


def _photons(n_events: int = 20000):
    """Read the first ``n_events`` photons of the shipped BH file."""
    import tttrlib

    return tttrlib.TTTR(str(TTTR_FILE))[0:n_events]


def test_fine_lag_axis_is_one_micro_time_tick_per_step():
    from chisurf.plugins.burst.burst_fcs_correlator.core import correlate_single_burst

    tttr = _photons()
    tau, g = correlate_single_burst(tttr, [0], [0], None, None, 5, 15, True)

    assert tau is not None and g is not None
    # One fine tick is one micro-time unit, so the first non-zero lag is exactly
    # the micro-time resolution (~3.3 ps here, not 4.1e9 ms).
    assert tau[1] == pytest.approx(tttr.header.micro_time_resolution * 1000.0, rel=1e-12)
    assert tau[-1] < 1.0  # the whole fine axis stays well below a millisecond


def test_the_fine_axis_is_finer_than_the_coarse_one():
    from chisurf.plugins.burst.burst_fcs_correlator.core import correlate_single_burst

    tttr = _photons()
    tau_coarse, _ = correlate_single_burst(tttr, [0], [0], None, None, 5, 15, False)
    tau_fine, _ = correlate_single_burst(tttr, [0], [0], None, None, 5, 15, True)

    assert tau_fine[1] < tau_coarse[1]
    assert tau_fine[-1] < tau_coarse[-1]
    # The two grids differ by exactly the number of micro-time channels.
    n_mt = tttr.get_number_of_micro_time_channels()
    assert tau_coarse[1] / tau_fine[1] == pytest.approx(n_mt, rel=1e-9)


def test_a_fine_request_without_micro_times_raises_instead_of_returning_a_coarse_axis():
    import tttrlib

    from chisurf.plugins.burst.burst_fcs_correlator.core import correlate_single_burst

    class _NoMicroTimes(tttrlib.TTTR):
        """A photon stream whose micro-time channel count cannot be read."""

        def get_number_of_micro_time_channels(self):
            raise RuntimeError("no micro times")

    n_events = 5000
    tttr = _NoMicroTimes(_photons(n_events), np.arange(n_events, dtype=np.int32))

    with pytest.raises(ValueError, match="micro-time"):
        correlate_single_burst(tttr, [0], [0], None, None, 5, 10, True)

    # The coarse path is unaffected.
    tau, g = correlate_single_burst(tttr, [0], [0], None, None, 5, 10, False)
    assert tau is not None and g is not None
