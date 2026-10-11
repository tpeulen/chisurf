"""A rate at the EM floor is a bound, not a measurement.

EM keeps every transition probability at or above ``MIN_TRANS`` (1e-12 per base time unit). A transition the data
do not contain settles there, and its "rate" ``MIN_TRANS / base_time_s`` is a property of the floor and the clock.
The *Rates* table listed it as ``0.0`` with a waiting time of ``1.35e+07`` ms (the BH SPC-132 clock, 13.5 ns), as if
measured, and the *Dwell FRET* kinetic scheme still drew it as an arrow.
"""

from types import SimpleNamespace

import numpy as np

from chisurf.plugins.burst.burst_h2mm.core.h2mm import MIN_TRANS
from chisurf.plugins.burst.burst_h2mm.gui import result_view
from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel

BASE = 13.5e-9  # s per tick of the BH SPC-132 sample


def _analysis():
    """Three states; S0 <-> S2 never happens (both directions at the floor), the rest are measured."""
    trans = np.array(
        [
            [1.0, 4.5e-7, MIN_TRANS],
            [6.1e-7, 1.0, 2.0e-6],
            [MIN_TRANS * 1.000001, 9.0e-7, 1.0],
        ]
    )
    rates = trans / BASE
    np.fill_diagonal(rates, 0.0)
    return SimpleNamespace(fret=np.array([0.03, 0.42, 0.87]), trans_rates=rates, base_time_s=BASE)


def test_the_floor_is_the_em_floor_over_the_clock():
    assert np.isclose(result_view.floor_rate(_analysis()), MIN_TRANS / BASE)


def test_floor_rates_are_listed_as_a_bound():
    model = H2mmViewModel.__new__(H2mmViewModel)
    model.bundle = SimpleNamespace(analysis=_analysis())
    rows = {row["transition"]: row for row in H2mmViewModel.rate_rows(model)}
    floor = MIN_TRANS / BASE
    for key in ("S0 -> S2", "S2 -> S0"):
        assert rows[key]["rate"] == f"< {floor:.2g}"
        assert rows[key]["time"].startswith("> ")
        assert rows[key]["rate"] != "0.0"
    measured = rows["S0 -> S1"]
    assert measured["rate"] == f"{4.5e-7 / BASE:.1f}" and not measured["rate"].startswith("<")
    assert float(measured["time"]) == float(f"{1e3 / (4.5e-7 / BASE):.3g}")


def test_small_measured_rates_keep_their_digits():
    ana = _analysis()
    ana.trans_rates = ana.trans_rates.copy()
    ana.trans_rates[0, 1] = 0.042  # well above the floor (7.4e-5 1/s), below one per second
    model = H2mmViewModel.__new__(H2mmViewModel)
    model.bundle = SimpleNamespace(analysis=ana)
    rows = {row["transition"]: row for row in H2mmViewModel.rate_rows(model)}
    assert rows["S0 -> S1"]["rate"] == "0.042"


def test_no_arrow_for_a_transition_at_the_floor():
    arrows = {(i, j) for i, j, *_ in result_view.transition_arrows(_analysis(), 1000.0)}
    assert arrows == {(0, 1), (1, 0), (1, 2), (2, 1)}
