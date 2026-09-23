"""ALEX (alternating laser excitation) analysis of Shimon Weiss lab ``.sm`` files in chisurf.

Exercises the full chisurf smFRET path on Shimon Weiss lab single-molecule ``.sm`` data:

* load the ``.sm`` container (tttrlib ``SM`` record type) through the chisurf
  ALEX plugin core (:func:`chisurf.plugins.tttr.ptu_alex_creator.core.load`);
* recover the excitation window with :func:`...core.apply_alex`, which wraps
  ``TTTR.alex_to_microtime`` — micro-second ALEX encodes the green/red laser
  alternation in the macro-time, folded into a synthetic micro-time;
* **auto-detect** the green/red windows from the folded-phase distribution with
  :func:`...core.auto_alex_windows` (guard bands drop the laser rise/fall), gate
  each burst into the DD / DA / AA streams via :func:`...core.alex_stream_masks`;
* turn the per-burst counts into ``E``/``S`` with
  ``tttrlib.apparent_es`` / ``tttrlib.corrected_es``.

A ground-truth ALEX stream with realistic laser windows (on-plateaus separated
by rise/fall gaps, plus edge smear) is round-tripped through the ``.sm``
container so the recovered windows and ``E``/``S`` can be checked against
injected values. The reference ``sm/data.sm`` file is loaded when present.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fluorescence.simulation.alex_sm import (
    ALEX_PERIOD,
    CH_ACCEPTOR,
    CH_DONOR,
    GREEN_WINDOW,
    RED_WINDOW,
)
from chisurf.core.fluorescence.simulation.alex_sm import (
    simulate_alex_sm as _simulate_alex_sm,
)

tttrlib = pytest.importorskip("tttrlib")

from tttrlib import apparent_es, corrected_es

from chisurf.plugins.tttr.ptu_alex_creator.core import (  # noqa: E402
    CONTAINER_INFO,
    alex_stream_masks,
    apply_alex,
    auto_alex_windows,
    load,
)

# .sm container/record ids and macro-time clock (12.5 ns).
SM_CONTAINER, SM_RECORD_TYPE = 7, 11
MACRO_RESOLUTION = 1.25e-8
TY_FLOAT8 = 536870920  # tttrlib tag type for an 8-byte float


def _es_per_burst(tttr, bursts, windows):
    """Count DD/DA/AA per burst using the detected ALEX windows."""
    masks = alex_stream_masks(
        tttr.micro_times,
        tttr.routing_channels,
        windows,
        donor_channels=[CH_DONOR],
        acceptor_channels=[CH_ACCEPTOR],
    )
    dd, da, aa = masks["DD"], masks["DA"], masks["AA"]
    i_dd = np.zeros(len(bursts))
    i_da = np.zeros(len(bursts))
    i_aa = np.zeros(len(bursts))
    for k, (s, e) in enumerate(bursts):
        sl = slice(int(s), int(e) + 1)
        i_dd[k] = np.count_nonzero(dd[sl])
        i_da[k] = np.count_nonzero(da[sl])
        i_aa[k] = np.count_nonzero(aa[sl])
    return i_dd, i_da, i_aa


def test_container_info_has_sm():
    """The ALEX plugin core knows the ``.sm`` container."""
    assert CONTAINER_INFO["SM"] == ("sm", SM_RECORD_TYPE, SM_CONTAINER)


def test_load_sm_through_chisurf():
    """The chisurf ``load`` helper reads a synthetic ``.sm`` file."""
    fn = tempfile.mktemp(suffix=".sm")
    try:
        _simulate_alex_sm(fn, [dict(E=0.5, S=0.5, n=40)], seed=7)
        tttr = load(fn, "SM")
        assert len(tttr) > 0
        assert set(np.unique(tttr.routing_channels)) == {CH_DONOR, CH_ACCEPTOR}
        # SM carries no micro-time until ALEX folding.
        assert int(np.asarray(tttr.micro_times).max()) == 0
    finally:
        if os.path.isfile(fn):
            os.unlink(fn)


def test_apply_alex_folds_macro_time():
    """``apply_alex`` folds the macro-time into the ALEX phase."""
    fn = tempfile.mktemp(suffix=".sm")
    try:
        _simulate_alex_sm(fn, [dict(E=0.5, S=0.5, n=40)], seed=7)
        tttr = load(fn, "SM")
        macro = np.asarray(tttr.macro_times)
        apply_alex(tttr, ALEX_PERIOD, 0)
        np.testing.assert_array_equal(
            np.asarray(tttr.micro_times),
            (macro % ALEX_PERIOD).astype(np.asarray(tttr.micro_times).dtype),
        )
    finally:
        if os.path.isfile(fn):
            os.unlink(fn)


def test_auto_alex_windows_recovers_laser_windows():
    """Auto-split finds the two laser windows and guard-bands their edges."""
    fn = tempfile.mktemp(suffix=".sm")
    try:
        _simulate_alex_sm(fn, [dict(E=0.3, S=0.55, n=300)], seed=2)
        tttr = load(fn, "SM")
        apply_alex(tttr, ALEX_PERIOD, 0)
        win = auto_alex_windows(
            tttr.micro_times,
            tttr.routing_channels,
            donor_channels=[CH_DONOR],
            acceptor_channels=[CH_ACCEPTOR],
            alex_period=ALEX_PERIOD,
            guard=0.06,
        )

        g_lo, g_hi = win["green"]
        r_lo, r_hi = win["red"]
        # Detected windows sit inside the true laser windows (guard trims edges),
        # never reaching into the rise/fall gaps.
        assert GREEN_WINDOW[0] <= g_lo < g_hi <= GREEN_WINDOW[1] + 1
        assert RED_WINDOW[0] <= r_lo < r_hi <= RED_WINDOW[1] + 1
        # Edges trimmed by roughly the guard fraction (a few hundred units).
        assert g_lo - GREEN_WINDOW[0] > 50
        assert RED_WINDOW[1] - r_hi > 50
    finally:
        if os.path.isfile(fn):
            os.unlink(fn)


def test_auto_split_raises_on_continuous_wave():
    """A single fully-occupied period is not ALEX and raises."""
    rng = np.random.RandomState(0)
    n = 20000
    phase = rng.randint(0, ALEX_PERIOD, n)  # uniform over the whole period
    rc = rng.randint(0, 2, n).astype(np.int8)
    with pytest.raises(ValueError):
        auto_alex_windows(
            phase,
            rc,
            donor_channels=[CH_DONOR],
            acceptor_channels=[CH_ACCEPTOR],
            alex_period=ALEX_PERIOD,
        )


def test_alex_es_recovers_two_populations():
    """End-to-end: load .sm -> ALEX -> auto-split -> burst -> es recovery."""
    populations = [
        dict(E=0.20, S=0.55, n=300),
        dict(E=0.80, S=0.55, n=300),
    ]
    fn = tempfile.mktemp(suffix=".sm")
    try:
        n_sim = _simulate_alex_sm(fn, populations, seed=1)

        tttr = load(fn, "SM")
        apply_alex(tttr, ALEX_PERIOD, 0)
        win = auto_alex_windows(
            tttr.micro_times,
            tttr.routing_channels,
            donor_channels=[CH_DONOR],
            acceptor_channels=[CH_ACCEPTOR],
            alex_period=ALEX_PERIOD,
        )

        bursts = np.asarray(tttr.burst_search(L=40, m=10, T=1.0e-3, mode="sliding_window")).reshape(
            -1, 2
        )
        assert len(bursts) == n_sim

        i_dd, i_da, i_aa = _es_per_burst(tttr, bursts, win)

        es = apparent_es(i_dd, i_da, i_aa)
        E, S = np.asarray(es["E"]), np.asarray(es["S"])

        assert float(S.mean()) == pytest.approx(0.55, abs=0.04)
        low, high = E[E < 0.5], E[E >= 0.5]
        assert len(low) == 300 and len(high) == 300
        assert float(low.mean()) == pytest.approx(0.20, abs=0.03)
        assert float(high.mean()) == pytest.approx(0.80, abs=0.03)

        # With an identity calibration corrected_es must agree with apparent_es.
        ces = corrected_es(i_dd, i_da, i_aa, gamma=1.0, alpha=0.0, beta=1.0, delta=0.0)
        np.testing.assert_allclose(np.asarray(ces["E"]), E, atol=1e-9)
        np.testing.assert_allclose(np.asarray(ces["S"]), S, atol=1e-9)
    finally:
        if os.path.isfile(fn):
            os.unlink(fn)


def _reference_sm():
    """Locate the ``sm/data.sm`` reference file if the data set is present."""
    for root in (
        os.environ.get("TTTRLIB_DATA"),
        os.environ.get("TTTR_DATA"),
        Path(__file__).resolve().parents[2].parent / "tttr-data",
    ):
        if not root:
            continue
        cand = Path(root) / "sm" / "data.sm"
        if cand.is_file():
            return str(cand)
    return None


def test_real_reference_sm_loads():
    """The ``sm/data.sm`` reference file loads through chisurf."""
    fn = _reference_sm()
    if fn is None:
        pytest.skip("tttr-data sm/data.sm not available")
    tttr = load(fn, "SM")
    assert len(tttr) > 0
    assert int(np.asarray(tttr.micro_times).max()) == 0
    assert tttr.header.macro_time_resolution == pytest.approx(MACRO_RESOLUTION, rel=1e-6)
    # Folding + burst search must run on real data.
    apply_alex(tttr, ALEX_PERIOD, 0)
    bursts = np.asarray(tttr.burst_search(L=40, m=10, T=1.0e-3, mode="sliding_window")).reshape(
        -1, 2
    )
    assert len(bursts) >= 0
