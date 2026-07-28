"""A sub-population of a burst is a column of its row, not a row of its own.

The burst table has one row per burst and every companion is merged onto it by
position, so a variable number of dwells cannot become a variable number of
rows. Splitting the fit by H2MM state therefore widens the row: `Tau S0 (green)`
beside `Tau (green)`. These pin that, and the reason it is worth doing — the
all-photon fit of a dynamic burst is a blend that belongs to neither state.
"""

from __future__ import annotations

from multiprocessing import shared_memory

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_mle_analysis._mp_worker import (  # noqa: E402
    process_one_file_worker,
)

N_BINS, BINNING, PERIOD = 128, 32, 13.5
DT = PERIOD / N_BINS


def _cfg(state_min_photons=20, min_photons=10):
    x = np.arange(N_BINS)
    g = np.exp(-0.5 * ((x - 8) / 1.5) ** 2)
    g /= g.sum()
    return dict(
        sb=0, eb=N_BINS, half_len=N_BINS, dt=DT, period=PERIOD, g_factor=1.0,
        l1=0.0, l2=0.0, p2s_twoIstar=True, BIFL_scatter=False,
        min_photons=min_photons, state_min_photons=state_min_photons,
        x0=np.array([2.0, 0.0, 0.38, 1.22]),
        fixed=np.array([0, 1, 1, 1], dtype=np.int32),
        irf=np.concatenate([g, g]), bg=np.zeros(2 * N_BINS),
        class_lut=np.array([0, 1], dtype=np.int8), model="fit23", method="Fit23",
        param_names=["tau", "gamma", "r0", "rho"],
    )


def _run(taus=(3.6, 1.0), n_bursts=40, per_state=300, seed=0, **cfg_kw):
    """Two states per burst with known lifetimes, through the real worker."""
    rng = np.random.default_rng(seed)
    mt, rc, st = [], [], []
    for _ in range(n_bursts):
        for s, tau in enumerate(taus):
            m = np.clip(rng.exponential(tau / DT, per_state) + 8, 0, N_BINS - 1)
            mt.append(m.astype(np.int32))
            rc.append(rng.integers(0, 2, per_state))
            st.append(np.full(per_state, s))
    mt = np.concatenate(mt).astype(np.uint16)
    rc = np.concatenate(rc).astype(np.uint16)
    st = np.concatenate(st).astype(np.int8)
    width = len(taus) * per_state
    bursts = [(i * width, (i + 1) * width) for i in range(n_bursts)]

    blocks = []

    def put(a):
        sh = shared_memory.SharedMemory(create=True, size=a.nbytes)
        np.ndarray(a.shape, dtype=a.dtype, buffer=sh.buf)[:] = a
        blocks.append(sh)
        return sh

    try:
        rc_sh, mt_sh, st_sh = put(rc), put(mt), put(st)
        args = ("m000.spc", bursts, rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg(**cfg_kw)}, 0,
                (st_sh.name, st.shape, str(st.dtype), len(taus)))
        out, n = process_one_file_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()
    import pandas as pd

    return pd.DataFrame(out), n


def test_each_state_gets_its_own_lifetime_column():
    df, n = _run()
    assert len(df) == 40 == n, "still one row per burst — the grain is the burst"
    assert {"Tau (green)", "Tau S0 (green)", "Tau S1 (green)"} <= set(df.columns)

    tau0 = df["Tau S0 (green)"].median()
    tau1 = df["Tau S1 (green)"].median()
    assert 2.8 < tau0 < 4.6, tau0
    assert 0.6 < tau1 < 1.5, tau1

    # …and the reason the split exists: the all-photon fit of a dynamic burst
    # lands between the two states and belongs to neither.
    blended = df["Tau (green)"].median()
    assert tau1 < blended < tau0, (tau1, blended, tau0)


def test_the_state_columns_never_collide_with_the_all_photon_ones():
    """A duplicate name is dropped on merge, taking its data with it."""
    df, _ = _run(n_bursts=4)
    assert len(set(df.columns)) == len(df.columns)
    identity = {"First File", "Detector"}
    assert identity <= set(df.columns)
    # The identity columns appear once, not once per state.
    assert sum(c.startswith("First File") for c in df.columns) == 1


def test_a_state_too_thin_to_fit_is_reported_not_dropped():
    """The row must survive: a missing row shifts every later burst."""
    df, _ = _run(per_state=5, n_bursts=6, state_min_photons=1000, min_photons=1)
    assert len(df) == 6
    assert df["Tau S0 (green)"].isna().all()
    assert (df["Ng-p S0"] + df["Ng-s S0"] > 0).all(), "counts are still reported"


def test_without_state_info_the_worker_behaves_exactly_as_before():
    """The split is opt-in; an ordinary run must be untouched."""
    rng = np.random.default_rng(1)
    n = 600
    mt = np.clip(rng.exponential(3.0 / DT, n) + 8, 0, N_BINS - 1).astype(np.uint16)
    rc = rng.integers(0, 2, n).astype(np.uint16)
    blocks = []

    def put(a):
        sh = shared_memory.SharedMemory(create=True, size=a.nbytes)
        np.ndarray(a.shape, dtype=a.dtype, buffer=sh.buf)[:] = a
        blocks.append(sh)
        return sh

    try:
        rc_sh, mt_sh = put(rc), put(mt)
        args = ("m000.spc", [(0, n)], rc_sh.name, rc.shape, str(rc.dtype),
                mt_sh.name, mt.shape, str(mt.dtype), ["green"],
                {"green": _cfg()}, 0, None)
        out, _ = process_one_file_worker(args)
    finally:
        for sh in blocks:
            sh.close()
            sh.unlink()

    assert len(out) == 1
    assert not [c for c in out[0] if " S0" in c or " S1" in c]
    assert "Tau (green)" in out[0]
