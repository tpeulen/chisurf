"""A burst ends *on* its last photon, in the workers as well as in the table.

``Last Photon`` is inclusive — the ``.bur`` writer stores
``Number of Photons == Last - First + 1``, and this plugin's own photon-coverage
mask (``wizard._covered_photon_indices``, ``stops + 1``) reads it that way. The
two multiprocessing workers used to slice the same pair exclusively, so every
per-burst lifetime, every ``Number of Photons (fit window)`` and every pooled
per-state decay was computed on one photon less than the row describes, and a
burst sitting exactly on ``min_photons`` was rejected.

These pin the convention at both worker sites (RF-808).
"""

from __future__ import annotations

from multiprocessing import shared_memory

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_mle_analysis._mp_worker import (  # noqa: E402
    _burst_slice,
    pool_states_worker,
    process_one_file_worker,
)

N_BINS, PERIOD = 128, 13.5
DT = PERIOD / N_BINS

#: A micro-time bin used by exactly one photon — the last one of the burst.
MARKER_BIN = 100


def _cfg(min_photons=1):
    """Build the one-detector configuration the workers expect."""
    x = np.arange(N_BINS)
    g = np.exp(-0.5 * ((x - 8) / 1.5) ** 2)
    g /= g.sum()
    return dict(
        sb=0, eb=N_BINS, half_len=N_BINS, dt=DT, period=PERIOD, g_factor=1.0,
        l1=0.0, l2=0.0, p2s_twoIstar=True, BIFL_scatter=False,
        min_photons=min_photons, state_min_photons=min_photons,
        x0=np.array([2.0, 0.0, 0.38, 1.22]),
        fixed=np.array([0, 1, 1, 1], dtype=np.int32),
        irf=np.concatenate([g, g]), bg=np.zeros(2 * N_BINS),
        class_lut=np.array([0, 1], dtype=np.int8), model="fit23", method="Fit23",
        param_names=["tau", "gamma", "r0", "rho"],
    )


def _photons(n=64, marker_at=None):
    """``n`` photons of one state, with ``marker_at`` alone in ``MARKER_BIN``."""
    rng = np.random.default_rng(7)
    mt = (rng.integers(0, 40, n) + 8).astype(np.uint16)
    if marker_at is not None:
        mt[marker_at] = MARKER_BIN
    rc = (np.arange(n) % 2).astype(np.uint16)
    st = np.zeros(n, dtype=np.int8)
    return mt, rc, st


def _in_shared_memory(arrays):
    """Yield shared-memory blocks holding ``arrays``."""
    blocks = []
    for a in arrays:
        sh = shared_memory.SharedMemory(create=True, size=a.nbytes)
        np.ndarray(a.shape, dtype=a.dtype, buffer=sh.buf)[:] = a
        blocks.append(sh)
    return blocks


def _pool(bursts, mt, rc, st, **cfg_kw):
    """Run the pooling worker over ``bursts`` of a synthetic file."""
    blocks = _in_shared_memory([rc, mt, st])
    try:
        rc_sh, mt_sh, st_sh = blocks
        args = (bursts, rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg(**cfg_kw)},
                (st_sh.name, st.shape, str(st.dtype), 1))
        return pool_states_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()


def _fit(bursts, mt, rc, **cfg_kw):
    """Run the per-burst fit worker over ``bursts`` of a synthetic file."""
    blocks = _in_shared_memory([rc, mt])
    try:
        rc_sh, mt_sh = blocks
        args = ("m000.spc", bursts, rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg(**cfg_kw)}, 0, None)
        out, _ = process_one_file_worker(args)
        return out
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()


def test_the_slice_helper_counts_the_last_photon():
    assert _burst_slice(10, 19) == slice(10, 20)
    assert _burst_slice(300, 300) == slice(300, 301)  # a one-photon burst
    assert len(np.arange(64)[_burst_slice(10, 19)]) == 10


def test_the_pooled_decay_holds_the_bursts_last_photon():
    """The photon at ``Last Photon`` is inside the burst, not after it."""
    mt, rc, st = _photons(marker_at=19)
    green = _pool([(10, 19)], mt, rc, st)["green"]

    assert int(green[0].sum()) == 10, "Last - First + 1 photons"
    assert int(green[0, :, MARKER_BIN].sum()) == 1, (
        "the last photon reaches the pooled decay of its state"
    )


def test_a_one_photon_burst_pools_one_photon():
    mt, rc, st = _photons(marker_at=5)
    green = _pool([(5, 5)], mt, rc, st)["green"]
    assert int(green[0].sum()) == 1
    assert int(green[0, :, MARKER_BIN].sum()) == 1


def test_the_fit_window_photon_count_matches_the_burst_row():
    """``Number of Photons (fit window)`` is the row's own photon count."""
    mt, rc, _ = _photons(marker_at=19)
    rows = _fit([(10, 19), (30, 30), (40, 63)], mt, rc)

    counts = [r["Number of Photons (fit window) (green)"] for r in rows]
    assert counts == [10, 1, 24]
    assert [r["Ng-p-all"] + r["Ng-s-all"] for r in rows] == [10, 1, 24]


def test_a_burst_exactly_on_the_photon_floor_is_fitted():
    """The floor is applied to the burst's real count, so 10 >= 10 passes."""
    mt, rc, _ = _photons(marker_at=19)
    (row,) = _fit([(10, 19)], mt, rc, min_photons=10)
    assert np.isfinite(row["Tau (green)"]), (
        "with the last photon dropped the burst held 9 and was rejected"
    )
