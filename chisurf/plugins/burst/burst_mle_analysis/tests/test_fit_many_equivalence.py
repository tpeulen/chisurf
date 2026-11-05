"""The burst fit through ``Fit2x.fit_many`` on threads gives, burst for burst, what one
``Fit2x.fit`` per burst gave: every number of the row (tau, gamma, rho, 2I*, the anisotropies),
the rejected flag of the outlier rules, for each objective (2I*: P+2S, BIFL scatter), model,
background pattern, fit window, VH shift and one-channel detector.

The reference below is the per-burst loop the process workers ran before (its histogram, its
shifted VH copy, one fit per burst), kept here as the definition the batch must meet.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_mle_analysis import _mp_worker as worker  # noqa: E402

N, DT = 96, 0.128


def _photons(n_bursts=70, seed=0):
    rng = np.random.default_rng(seed)
    mt, rc, bursts, at = [], [], [], 0
    for i in range(n_bursts):
        size = int(rng.integers(5, 400))  # some below the photon floor
        tau = rng.uniform(0.5, 5.0)
        t = rng.normal(10, 1.2, size) + rng.exponential(tau / DT, size)
        flat = rng.random(size) < 0.1  # a background floor
        t[flat] = rng.uniform(0, N, int(flat.sum()))
        mt.append(np.rint(t).astype(np.int64) % (N + 8))  # a few past the histogram's end
        rc.append(rng.choice([0, 1, 5], size, p=[0.55, 0.4, 0.05]))  # channel 5: no detector's
        bursts.append((at, at + size - 1))
        at += size
    return np.concatenate(mt).astype(np.uint16), np.concatenate(rc).astype(np.uint8), bursts


def _cfg(model="fit23", p2s=True, bifl=False, window=True, background=True, mirror=False):
    x = np.arange(N)
    g = np.exp(-0.5 * ((x - 10) / 1.2) ** 2)
    names = {"fit23": ["tau", "gamma", "r0", "rho"],
             "fit24": ["tau1", "gamma", "tau2", "A2", "offset"],
             "fit25": ["tau1", "tau2", "tau3", "tau4", "gamma"]}[model]
    x0 = {"fit23": [2.0, 0.05, 0.38, 1.2], "fit24": [1.0, 0.05, 4.0, 0.3, 0.0],
          "fit25": [0.5, 1.5, 3.0, 4.5, 0.05]}[model]
    fixed = {"fit23": [0, 0, 1, 0], "fit24": [0, 0, 0, 0, 1], "fit25": [1, 1, 1, 1, 0]}[model]
    lut = np.full(6, -1, np.int8)
    lut[0] = 0
    if not mirror:
        lut[1] = 1
    bg = np.ones(2 * N) + np.concatenate([g, g]) * 3 if background else np.zeros(2 * N)
    return dict(
        sb=4 if window else 0, eb=N - 6 if window else N, vh_sb=5 if window else 0,
        vh_eb=N - 6 if window else N, half_len=N, dt=DT, period=N * DT, g_factor=1.05,
        l1=0.01, l2=0.02, p2s_twoIstar=p2s, BIFL_scatter=bifl, min_photons=30,
        state_min_photons=20, x0=np.asarray(x0, float), fixed=np.asarray(fixed, np.int32),
        irf=np.concatenate([g, g]), bg=bg, class_lut=lut, mirror=mirror, model=model,
        param_names=names, fit_window=(4, N - 6) if window else None,
    )


def _per_burst(fname, bursts, rc, mt, det, cfg, shift):
    """The per-burst loop of the former process worker."""
    fitter = worker._build_fitter(cfg)
    n = int(cfg["half_len"])
    out = []
    for first, last in bursts:
        sl = worker._burst_slice(first, last)
        cp, cs = worker._hist2_split_core_classlut(mt[sl], rc[sl], cfg["class_lut"], n)
        if cfg.get("mirror"):
            cs = cp
        s0, s1 = max(0, int(cfg["sb"])), min(n, int(cfg["eb"]))
        t0, t1 = max(0, int(cfg["vh_sb"])), min(n, int(cfg["vh_eb"]))
        cp_sum, cs_sum = int(cp[s0:s1].sum()), int(cs[t0:t1].sum())
        if cfg.get("mirror"):
            cs_sum = 0
        color = worker.colour_of(det)
        if cp_sum + cs_sum < int(cfg["min_photons"]):
            out.append(worker._record(fname, det, color, cfg, None, float("nan"), cp_sum, cs_sum,
                                      reason=1))
            continue
        d = np.zeros(2 * n)
        d[s0:s1] = cp[s0:s1]
        if shift:
            worker._copy_shifted(cs, d, n, t0, t1, shift, n)
        else:
            d[n + t0 : n + t1] = cs[t0:t1]
        res = fitter(data=d, initial_values=cfg["x0"], fixed=cfg["fixed"])
        x = np.asarray(res.x, float)
        reason = worker.reject_reason(cfg, x, res.result("converged"), float(res.twoIstar))
        out.append(worker._record(
            fname, det, color, cfg, None if reason else x, float(res.twoIstar), cp_sum, cs_sum,
            extras=None if reason else {"r_scatter": res.r_scatter,
                                        "r_experimental": res.r_experimental,
                                        "selected_index": res.result("selected_index")},
            reason=reason))
    return out


def _same(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


@pytest.mark.parametrize(
    "options",
    [
        dict(),
        dict(p2s=False),
        dict(bifl=True),
        pytest.param(dict(p2s=False, bifl=True), marks=pytest.mark.xfail(
            strict=False,
            reason="tttrlib fit23 (soft BIFL + Poisson objective) carries the previous fit's gamma "
            "in thread_local state into the next fit's first gradient: the per-burst result "
            "depends on which fits ran before it on that thread, in the old process path as in "
            "this one (okf/references/known-issues.md)")),
        dict(background=False, window=False),
        dict(mirror=True),
        dict(shift=3),
        dict(model="fit24"),
        dict(model="fit25"),
    ],
    ids=lambda o: ",".join(f"{k}={v}" for k, v in o.items()) or "default",
)
def test_fit_many_rows_are_the_per_burst_rows(monkeypatch, options):
    options = dict(options)
    shift = options.pop("shift", 0)
    mt, rc, bursts = _photons()
    cfg = _cfg(**options)
    expected = _per_burst("m.ptu", bursts, rc, mt, "G|G", cfg, shift)
    monkeypatch.setattr(worker, "CHUNK_ROWS", 16)  # several chunks, on several threads
    job = worker.BurstJob("m.ptu", bursts, rc, mt, ["G|G"], {"G|G": cfg}, shift)
    seen = []
    got = worker.fit_jobs([job], threads=3, progress=lambda done, total: seen.append((done, total)))
    assert len(got) == len(expected) == len(bursts)
    assert any(r["Fit rejected (G|G)"] == 1 for r in got), "the floor is exercised"
    assert any(r["Fit rejected (G|G)"] == 0 for r in got), "and real fits"
    for a, b in zip(expected, got):
        assert list(a) == list(b), "the same columns, in the same order"
        assert all(_same(a[k], b[k]) for k in a), {k: (a[k], b[k]) for k in a if not _same(a[k], b[k])}
    assert seen[-1] == (len(bursts), len(bursts))


def test_a_stop_ends_the_fit_between_chunks(monkeypatch):
    mt, rc, bursts = _photons()
    monkeypatch.setattr(worker, "CHUNK_ROWS", 8)
    job = worker.BurstJob("m.ptu", bursts, rc, mt, ["G|G"], {"G|G": _cfg()}, 0)
    with pytest.raises(InterruptedError):
        worker.fit_jobs([job], threads=2, should_stop=lambda: True)
