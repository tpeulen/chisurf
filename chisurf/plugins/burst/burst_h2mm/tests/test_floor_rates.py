"""A rate the data cannot show is a bound, not a measurement.

EM keeps every transition probability at or above ``MIN_TRANS`` (1e-12 per base time unit). A transition the data
do not contain settles there, and its "rate" ``MIN_TRANS / base_time_s`` is a property of the floor and the clock.
The *Rates* table listed it as ``0.0`` with a waiting time of ``1.35e+07`` ms (the BH SPC-132 clock, 13.5 ns), as if
measured, and the *Dwell FRET* kinetic scheme still drew it as an arrow. Rates a few times above the floor (the
three-state fit of the same sample gives S2 -> S0 = 2.8e-4 1/s) are just as unmeasured: they predict less than one
event in the ~seconds spent inside bursts. Anything below ``1 / T_bursts`` is listed as that bound.
"""

from types import SimpleNamespace

import numpy as np

from chisurf.plugins.burst.burst_h2mm.core.h2mm import MIN_TRANS, prepare_bursts
from chisurf.plugins.burst.burst_h2mm.gui import result_view
from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel

BASE = 13.5e-9  # s per tick of the BH SPC-132 sample
T_BURSTS = 2.5  # s inside bursts -> bound 0.4 1/s


def _analysis(observed=T_BURSTS):
    """Three states; S0 -> S2 and S2 -> S0 never happen (floor, and 3x the floor), the rest are measured."""
    trans = np.array(
        [
            [1.0, 4.5e-7, MIN_TRANS],
            [6.1e-7, 1.0, 2.0e-6],
            [MIN_TRANS * 3.8, 9.0e-7, 1.0],
        ]
    )
    rates = trans / BASE
    np.fill_diagonal(rates, 0.0)
    return SimpleNamespace(
        fret=np.array([0.03, 0.42, 0.87]),
        trans_rates=rates,
        base_time_s=BASE,
        observed_time_s=observed,
    )


def _rows(ana):
    model = H2mmViewModel.__new__(H2mmViewModel)
    model.bundle = SimpleNamespace(analysis=ana)
    return {row["transition"]: row for row in H2mmViewModel.rate_rows(model)}


def test_the_bound_is_one_event_in_the_burst_time():
    assert np.isclose(result_view.rate_bound(_analysis()), 1.0 / T_BURSTS)
    # without the burst time, the EM floor (with its margin) is the bound
    assert np.isclose(result_view.rate_bound(_analysis(float("nan"))), 2.0 * MIN_TRANS / BASE)


def test_burst_time_is_first_to_last_photon_of_each_burst():
    data = prepare_bursts(
        [np.array([0, 10, 30]), np.array([100, 105])], [np.zeros(3), np.zeros(2)], 2
    )
    assert data.total_time == 30 + 5


def test_unmeasured_rates_are_listed_as_a_bound():
    rows = _rows(_analysis())
    for key in ("S0 -> S2", "S2 -> S0"):
        assert rows[key]["rate"] == "< 0.4" and rows[key]["time"] == "> 2.5e+03"
    measured = rows["S0 -> S1"]
    assert measured["rate"] == f"{4.5e-7 / BASE:.1f}"
    assert float(measured["time"]) == float(f"{1e3 / (4.5e-7 / BASE):.3g}")


def test_small_measured_rates_keep_their_digits():
    ana = _analysis()
    ana.trans_rates = ana.trans_rates.copy()
    ana.trans_rates[0, 1] = 4.2  # above the bound, below 10 1/s: was printed with one decimal
    assert _rows(ana)["S0 -> S1"]["rate"] == "4.2"
    ana.trans_rates[0, 1] = 0.842
    assert _rows(ana)["S0 -> S1"]["rate"] == "0.842"


def test_no_arrow_for_an_unmeasured_transition():
    arrows = {(i, j) for i, j, *_ in result_view.transition_arrows(_analysis(), 1000.0)}
    assert arrows == {(0, 1), (1, 0), (1, 2), (2, 1)}
