"""The native burst fit in chunks (a thread count that may change while it runs) gives the rows
of the one-call fit, burst for burst: Burst MLE ahead of Next fits on half the threads and takes
every one once the user waits, from its next chunk."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.burst import fused_pipeline  # noqa: E402
from test.core.test_fused_burst_pipeline import DETECTORS, _stream  # noqa: E402

pytestmark = pytest.mark.skipif(not fused_pipeline.available(), reason="tttrlib without BurstPipeline")

N, BINNING = 100, 5


def _session(n_bursts=180):
    tttr = _stream(n_bursts=n_bursts)
    macro = np.asarray(tttr.macro_times)
    gaps = np.diff(macro) > 400  # the simulated bursts: photons 55 ticks apart, background 7500
    edges = np.flatnonzero(np.diff(np.concatenate([[0], (~gaps).astype(int), [0]])))
    first, last = edges[0::2], edges[1::2]
    keep = last - first >= 20
    first, last = first[keep], last[keep]
    table = {"First File": np.array(["m.ptu"] * first.size, dtype=object),
             "First Photon": first.astype(float), "Last Photon": last.astype(float)}
    return SimpleNamespace(
        split_by_state=False, df_bursts=table, settings=SimpleNamespace(shift=0),
        tttrs={"m": tttr}, detectors=DETECTORS,
        timing_ns=lambda t, b: (0.08 * b, 40.0),
    ), int(first.size)


def _configs():
    x = np.arange(N)
    g = np.exp(-0.5 * ((x - 4) / 1.0) ** 2)
    irf = np.concatenate([g, g])
    base = dict(sb=1, eb=N - 2, vh_sb=1, vh_eb=N - 2, half_len=N, g_factor=1.05, l1=0.01, l2=0.02,
                p2s_twoIstar=True, BIFL_scatter=False, min_photons=30, state_min_photons=20,
                irf=irf, bg=np.ones(2 * N), model="fit23", param_names=["tau", "gamma", "r0", "rho"],
                fit_window=(1, N - 2), x0=np.array([2.0, 0.05, 0.38, 1.2]),
                fixed=np.array([0, 0, 1, 0], np.int32))
    return {d: dict(base) for d in DETECTORS}


def _same(a, b):
    assert a.keys() == b.keys()
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, float) and np.isnan(x):
            assert isinstance(y, float) and np.isnan(y), k
        else:
            assert x == y, k


def test_the_fit_in_chunks_is_the_fit_in_one_call():
    session, bursts = _session()
    assert bursts > 2 * fused_pipeline.FIT_CHUNKS
    dets = list(DETECTORS)
    whole = fused_pipeline.fit_session(session, _configs(), dets, BINNING, threads=2)
    asked = []

    def threads():  # half until "Next", then all: a count that changes between chunks
        asked.append(1)
        return 1 if len(asked) < 3 else 4

    chunked = fused_pipeline.fit_session(session, _configs(), dets, BINNING, threads=threads)
    assert len(asked) == fused_pipeline.FIT_CHUNKS, "read again before every chunk"
    assert len(whole) == len(chunked) == bursts * len(dets)
    fitted = [r for r in whole if not next(v for k, v in r.items() if k.startswith("Fit rejected"))]
    assert len(fitted) > bursts, "most bursts fitted on every detector"
    for a, b in zip(whole, chunked):
        _same(a, b)
