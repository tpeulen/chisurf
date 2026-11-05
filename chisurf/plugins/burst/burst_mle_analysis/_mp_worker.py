import dataclasses
from multiprocessing import shared_memory as _shm

import numpy as np

from chisurf.core.fluorescence.detector_names import canonical, is_default, role

#: The legacy ``b?4`` folder letter of each FRET role (``bg4`` / ``br4`` / ``by4``).
_ROLE_LETTER = {"donor": "g", "acceptor": "r", "acceptor_direct": "y"}


def colour_of(det: str) -> str:
    """How detector *det* names its result columns (``Tau (G|G)``): a detector name as it is,
    any other name lower-cased, as before."""
    name = canonical(det)
    return name if is_default(name) else str(det).lower()


def letter_of(det: str) -> str:
    """The ``b?4`` table letter of *det*: by its role (``G|G`` g, ``R|G`` r, ``R|R`` y), else its first
    character -- ``R|G`` and ``R|R`` share their first letter."""
    return _ROLE_LETTER.get(role(det)) or colour_of(det)[0]


def _hist2_split_core_classlut(
    mt_bins: np.ndarray, rc_slice: np.ndarray, class_lut: np.ndarray, half_len: int
):
    """
    class_lut: int8 array (size max_rc+1) with {-1 ignore, 0=P, 1=S}.
    Returns (cp_u32, cs_u32).
    """
    cls = class_lut[rc_slice]  # int8 view
    valid = cls >= 0
    if not np.any(valid):
        return (np.zeros(half_len, dtype=np.uint32), np.zeros(half_len, dtype=np.uint32))
    b = mt_bins[valid]
    c = cls[valid].astype(np.int32, copy=False)
    h2 = np.bincount(b * 2 + c, minlength=2 * half_len)
    return (h2[0::2].astype(np.uint32, copy=False), h2[1::2].astype(np.uint32, copy=False))


def _copy_shifted(
    src_u32: np.ndarray, dst_f64: np.ndarray, dst_off: int, s0: int, s1: int, shift: int, n: int
):
    """
    Copy src_u32 into dst_f64 window [dst_off+s0 : dst_off+s1] applying
    a circular shift by 'shift' (positive = right shift) without np.roll.
    """
    if s1 <= s0:
        return
    length = s1 - s0
    # We need dst[...] = src[(s0 - shift) % n : ...] with wraparound
    start = (s0 - shift) % n
    first = min(length, n - start)
    dst_f64[dst_off + s0 : dst_off + s0 + first] = src_u32[start : start + first]
    rem = length - first
    if rem:
        dst_f64[dst_off + s0 + first : dst_off + s1] = src_u32[0:rem]


def _burst_slice(first_ph, last_ph) -> slice:
    """Return the photons of one burst as a slice into the file's arrays.

    ``Last Photon`` is the burst's last photon **inclusive** — that is what the
    ``.bur`` writer stores (``Number of Photons == last - first + 1``) and what
    the session's photon-coverage mask assumes (``stops + 1``). The slice
    therefore runs to ``last + 1``; a burst with ``first == last`` is one
    photon, not none.

    Parameters
    ----------
    first_ph : int
        Index of the burst's first photon.
    last_ph : int
        Index of the burst's last photon, inclusive.

    Returns
    -------
    slice
        ``slice(first_ph, last_ph + 1)``.
    """
    return slice(int(first_ph), int(last_ph) + 1)


def _build_fitter(cfg):
    """Build the estimator for this detector's configuration.

    The batch worker and the interactive preview build through the same
    ``Fit2x`` facade, so batch results match the live preview by construction
    rather than by both of them independently reproducing the same setup. The
    facade also area-normalises the background, so gamma is a true 0..1 fraction
    (see okf/subsystems/mle-lifetime-fitting.md); it is no longer done here.
    """
    from chisurf.core.fluorescence.mle.fit2x import (
        Fit2x,
        Fit2xModel,
        Fit2xSettings,
    )

    return Fit2x(
        Fit2xSettings(
            dt=float(cfg["dt"]),
            irf=np.asarray(cfg["irf"], dtype=np.float64),
            background=np.asarray(cfg["bg"], dtype=np.float64),
            period=float(cfg["period"]),
            g_factor=float(cfg["g_factor"]),
            l1=float(cfg["l1"]),
            l2=float(cfg["l2"]),
            p2s_twoIstar=bool(cfg["p2s_twoIstar"]),
            soft_bifl_scatter=bool(cfg["BIFL_scatter"]),
            fit_window=cfg.get("fit_window"),
        ),
        model=Fit2xModel(cfg.get("model", "fit23")),
    )


def _state_suffix(state):
    """How a sub-population is named in a column. ``None`` = all photons."""
    return "" if state is None else f" S{int(state)}"


def tail_lifetime(counts: np.ndarray, dt: float) -> float:
    """Maximum-likelihood lifetime of an exponential seen over a truncated window.

    *counts* are the photons per bin from the tail start to the window's end, *dt* the bin width
    (ns). The likelihood of a decay truncated to ``[0, T]`` has its maximum where the photons' mean
    time equals ``tau - T / (exp(T / tau) - 1)``; that mean rises monotonically with tau towards
    ``T / 2``, so a bisection finds it. NaN for fewer than two photons or a flat window.
    """
    return float(tail_lifetimes(np.asarray(counts, dtype=np.float64)[None, :], dt)[0])


def tail_lifetimes(tails: np.ndarray, dt: float) -> np.ndarray:
    """:func:`tail_lifetime` of every row of *tails* (``(n_bursts, n_bins)``), the bisection
    run on all rows at once (a loop of it per burst held the GIL for seconds)."""
    tails = np.asarray(tails, dtype=np.float64)
    k, m = tails.shape
    out = np.full(k, np.nan)
    if m < 2 or dt <= 0 or not k:
        return out
    n = tails.sum(axis=1)  # whole counts: exact in any order
    t = (np.arange(m) + 0.5) * dt
    T = m * dt
    mean = np.array([float((row * t).sum()) for row in tails]) / np.where(n > 0, n, 1.0)
    ok = (n >= 2) & ~(mean >= 0.5 * T * 0.999)  # else no decay in the window
    if not ok.any():
        return out
    target = mean[ok]
    lo = np.full(target.size, 1e-4)
    hi = np.full(target.size, 1e4)
    for _ in range(80):
        mid = np.sqrt(lo * hi)
        r = T / mid
        with np.errstate(over="ignore"):
            value = np.where(r < 700, mid - T / np.expm1(np.minimum(r, 700.0)), mid)
        below = value < target
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    out[ok] = np.sqrt(lo * hi)
    return out


#: Why a burst's fit is not a lifetime (the ``Fit rejected (<det>)`` row key, never exported):
#: the row's fitted values are written as NaN -- the companion's skipped sentinel -- and the
#: Lifetime table counts the burst as excluded instead of averaging it in.
REJECT_REASONS = {
    1: "too few photons",
    2: "not converged",
    3: "not finite",
    4: "lifetime at or below zero / under half a bin",
    5: "lifetime longer than the fit window",
    6: "all background (gamma at its bound)",
}
#: gamma at or above this is a fit that gave every photon to the background.
GAMMA_BOUND = 0.99


def reject_reason(cfg, x, converged: float | None = None, two_istar: float | None = None) -> int:
    """``0`` when fitted values *x* of *cfg*'s model are a lifetime, else the code of
    :data:`REJECT_REASONS`. The physical range: above half a bin and shorter than the fit window
    (a longer lifetime is not resolved by it -- the batch's mean of 882 ns was such fits)."""
    if x is None:
        return 1
    x = np.asarray(x, dtype=float)
    tau_index = 1 if cfg.get("model") == "tail" else 0
    # a NaN 2I* alone is no reason: some held configurations report none
    if x.size <= tau_index or not np.isfinite(x[tau_index]):
        return 3
    if converged is not None and np.isfinite(converged) and converged <= 0:
        return 2
    dt = float(cfg.get("dt") or 0.0)
    tau = float(x[tau_index])
    if tau <= 0.5 * dt or tau <= 0.0:
        return 4
    window = cfg.get("fit_window")
    lo, hi = (window if window else (cfg.get("sb", 0), cfg.get("eb", 0)))
    span = (int(hi) - int(lo)) * dt
    if span > 0 and tau > span:
        return 5
    if cfg.get("model", "fit23") == "fit23" and x.size > 1 and np.isfinite(x[1]) and x[1] >= GAMMA_BOUND:
        return 6
    return 0


def _record(fname, det, color, cfg, x, two_istar, cp_sum, cs_sum, state=None, extras=None,
            reason=0):
    """One result row, laid out by the fitted model.

    ``fit23`` keeps its historical column set (tau/gamma/r0/rho + the two
    anisotropy columns) so its ``.b?4`` export is byte-for-byte unchanged. Every
    other model writes ``Tau`` (= ``x[0]``, the best lifetime) plus one column per
    free parameter named by the registry schema (``cfg['param_names']``). Pass
    ``x=None`` for a skipped/failed burst to emit NaN in every numeric slot.

    ``extras`` carries the fit's *derived* results by name (``r_scatter``,
    ``r_experimental``). They used to be read out of ``x`` at indices 6 and 7,
    because the estimator returned parameters and outputs in one array; the
    fitted parameters now stand alone, so anything derived arrives here by name.
    Reading them positionally would silently write NaN into two columns of the
    ``.b?4`` export.

    ``reason`` (:func:`reject_reason`) is kept as the row key ``Fit rejected (<det>)`` -- not an
    export column: a rejected fit's values are NaN, the skipped sentinel, already.

    With ``state`` set, every measured column is suffixed (``Tau S0 (G|G)``)
    and the identity columns are omitted: a sub-population of a burst is a
    *column* of that burst's row, not a row of its own — the burst is still the
    unit of observation, and a burst table has one row per burst. The suffixed
    names must not collide with the all-photon ones, because every companion is
    merged into a single frame and a duplicate name is silently dropped.
    """

    def g(i):
        try:
            return float(x[i])
        except (TypeError, IndexError):
            return float("nan")

    # the tail fit's parameters are (tail start, tau1, tau2): its lifetime is the second
    tau_index = 1 if cfg.get("model") == "tail" else 0

    extras = extras or {}

    sfx = _state_suffix(state)
    rec = {f"Fit rejected{sfx} ({color})": int(reason)}
    if state is None:
        rec["First File"] = fname
        rec["Detector"] = det
        rec["Ng-p-all"] = cp_sum
        rec["Ng-s-all"] = cs_sum
    else:
        rec[f"Ng-p{sfx}"] = cp_sum
        rec[f"Ng-s{sfx}"] = cs_sum
    # The all-photon 2I* column has two spaces after the star — historical, and
    # part of the .b?4 format, so it is preserved exactly rather than tidied.
    two_istar_key = f"2I*  ({color})" if state is None else f"2I*{sfx} ({color})"
    rec.update(
        {
            f"Number of Photons (fit window){sfx} ({color})": cp_sum + cs_sum,
            two_istar_key: two_istar,
            f"Tau{sfx} ({color})": g(tau_index),
            f"BIFL scatter?{sfx} ({color})": int(cfg["BIFL_scatter"]),
            f"2I*: P+2S?{sfx} ({color})": int(cfg["p2s_twoIstar"]),
        }
    )
    if cfg.get("model", "fit23") == "fit23":
        rec[f"gamma{sfx} ({color})"] = g(1)
        rec[f"r0{sfx} ({color})"] = g(2)
        rec[f"rho{sfx} ({color})"] = g(3)
        rec[f"r Scatter{sfx} ({color})"] = float(extras.get("r_scatter", float("nan")))
        rec[f"r Experimental{sfx} ({color})"] = float(extras.get("r_experimental", float("nan")))
    else:
        for i, nm in enumerate(cfg.get("param_names") or ()):
            rec[f"{nm}{sfx} ({color})"] = (
                (
                    float(cfg["x0"][i])
                    if cfg.get("model") == "fit25" and nm.startswith("tau")
                    else g(i)
                )
                if x is not None
                else float("nan")
            )
        from .engine import fit_result_names

        for name in fit_result_names(cfg["model"]):
            rec[f"{name}{sfx} ({color})"] = float(extras.get(name, float("nan")))
    return rec




# -- the fit of every burst: Fit2x.fit_many on threads ---------------------------------------- #
#: Bursts per ``fit_many`` call. Under tttrlib's 1024 rows its batch runs on the calling thread,
#: so the threads of :func:`fit_jobs` are the only ones (as many as ``fit_workers()``), and a
#: chunk is about 0.8 s of fit23 at 3 ms a fit: Stop and the progress bar answer within that.
CHUNK_ROWS = 256


@dataclasses.dataclass
class BurstJob:
    """One measurement's bursts, as the fit reads them: the photons are arrays of this process.

    *rc* (routing channels) and *mt* (micro-time bins at the fit's binning) index as the burst
    table's ``First Photon`` / ``Last Photon`` (inclusive); *states* the per-photon H2MM state
    (``-1`` unassigned) when the fit is split by state. ``rc is None``: the raw measurement could
    not be read, every burst gets the no-data row. *perdet* holds each detector's constants
    (:meth:`~.engine.MleSession.batch_config` plus ``class_lut``, ``mirror``, ``half_len``).
    """

    fname: str
    bursts: list
    rc: np.ndarray | None
    mt: np.ndarray | None
    det_order: list
    perdet: dict
    shift: int = 0
    states: np.ndarray | None = None
    n_states: int = 0


def burst_counts(rc, mt, bursts, class_lut, n, states=None, state=None):
    """``(cp, cs)``: the ``(len(bursts), n)`` parallel and perpendicular micro-time histograms of
    each burst's photons (*class_lut*: routing channel -> -1 ignore / 0 P / 1 S), all bursts in one
    ``bincount``; with *state*, only the photons of that state. Bins at or past *n* are dropped,
    as the per-burst histogram's windows never read them."""
    nb = len(bursts)
    if not nb:
        return np.zeros((0, n), np.int64), np.zeros((0, n), np.int64)
    pairs = np.asarray(bursts, dtype=np.int64).reshape(nb, 2)
    first = pairs[:, 0]
    stop = np.minimum(pairs[:, 1] + 1, len(rc))  # Last Photon is inclusive (_burst_slice)
    lengths = np.maximum(stop - first, 0)
    owner = np.repeat(np.arange(nb, dtype=np.int64), lengths)
    idx = np.arange(int(lengths.sum()), dtype=np.int64) + np.repeat(
        first - (np.cumsum(lengths) - lengths), lengths
    )
    cls = class_lut[rc[idx]]
    b = mt[idx].astype(np.int64)
    keep = (cls >= 0) & (b < n)
    if states is not None and state is not None:
        keep &= states[idx] == state
    flat = owner[keep] * (2 * n) + b[keep] * 2 + cls[keep]
    h = np.bincount(flat, minlength=nb * 2 * n).reshape(nb, n, 2)
    return h[:, :, 0], h[:, :, 1]


def decay_rows(cp, cs, cfg, n, shift):
    """The decays the fit takes, one row a burst: VV in the detector's VV gate, VH in its VH
    gate rolled by *shift* (``dst[j] = cs[(j - shift) % n]``, as :func:`_copy_shifted`), zeros
    elsewhere."""
    s0, s1 = max(0, int(cfg["sb"])), min(n, int(cfg["eb"]))
    t0 = max(0, int(cfg.get("vh_sb", cfg["sb"])))
    t1 = min(n, int(cfg.get("vh_eb", cfg["eb"])))
    d = np.zeros((cp.shape[0], 2 * n), dtype=np.float64)
    if s1 > s0:
        d[:, s0:s1] = cp[:, s0:s1]
    if t1 > t0:
        cols = (np.arange(t0, t1) - int(shift)) % n if shift else np.arange(t0, t1)
        d[:, n + t0 : n + t1] = cs[:, cols]
    return d


def _fit_chunk(job: BurstJob, det: str, fitter, bursts, state) -> list[dict]:
    """The result rows of *det* (and *state*, ``None`` = all photons) for a chunk of *job*'s
    bursts: their histograms, one ``fit_many`` call for those above the photon floor."""
    cfg = job.perdet[det]
    n = int(cfg["half_len"])
    color = colour_of(det)
    cp, cs = burst_counts(job.rc, job.mt, bursts, cfg["class_lut"], n, job.states, state)
    if cfg.get("mirror"):
        cs = cp
    s0, s1 = max(0, int(cfg["sb"])), min(n, int(cfg["eb"]))
    t0 = max(0, int(cfg.get("vh_sb", cfg["sb"])))
    t1 = min(n, int(cfg.get("vh_eb", cfg["eb"])))
    cp_sum = cp[:, s0:s1].sum(axis=1) if s1 > s0 else np.zeros(len(bursts), np.int64)
    cs_sum = cs[:, t0:t1].sum(axis=1) if t1 > t0 else np.zeros(len(bursts), np.int64)
    if cfg.get("mirror"):
        cs_sum = np.zeros_like(cs_sum)  # the same photons twice: counted once
    if state is None:
        floor = int(cfg["min_photons"])
    else:
        # split by colour *and* state a burst is thin: the state passes have their own floor
        floor = int(cfg.get("state_min_photons") or cfg["min_photons"])
    fitted = np.flatnonzero(cp_sum + cs_sum >= floor)
    rows = [
        _record(job.fname, det, color, cfg, None, float("nan"), int(a), int(b), state=state, reason=1)
        for a, b in zip(cp_sum.tolist(), cs_sum.tolist())
    ]
    if not fitted.size:
        return rows
    if fitter is None:
        # the tail fit: from the tail start (after the decay's peak) to the window's end, both
        # polarisations summed
        start = min(max(int(cfg.get("tail_bin", s0)), s0), s1)
        tails = cp[fitted, start:s1].astype(np.float64)
        if not cfg.get("mirror"):
            tails = tails + cs[fitted, start:s1]
        taus = tail_lifetimes(tails, float(cfg["dt"]))
        for i, tau in zip(fitted.tolist(), taus.tolist()):
            x = np.array([float(start), tau, np.nan])
            reason = reject_reason(cfg, x)
            rows[i] = _record(job.fname, det, color, cfg, None if reason else x, float("nan"),
                              int(cp_sum[i]), int(cs_sum[i]), state=state, reason=reason)
        return rows
    # a state's fits start from that state's pooled lifetime when one was fitted
    # (state_split.seed_state_fits): at the panel's one guess every state is pulled to it
    x0 = cfg["x0"] if state is None else (cfg.get("state_x0") or {}).get(state, cfg["x0"])
    d = decay_rows(cp[fitted], cs[fitted], cfg, n, job.shift)
    batch = fitter.fit_many(d, x0, fixed=cfg["fixed"])
    converged = batch.result("converged")
    r_scatter, r_experimental = batch.result("r_scatter"), batch.result("r_experimental")
    selected = batch.result("selected_index")
    for k, i in enumerate(fitted.tolist()):
        x = np.asarray(batch.x[k], dtype=np.float64)
        two_istar = float(batch.twoIstar[k])
        reason = reject_reason(cfg, x, float(converged[k]), two_istar)
        rows[i] = _record(
            job.fname, det, color, cfg, None if reason else x, two_istar,
            int(cp_sum[i]), int(cs_sum[i]), state=state, reason=reason,
            extras=None if reason else {
                "r_scatter": float(r_scatter[k]), "r_experimental": float(r_experimental[k]),
                "selected_index": float(selected[k]),
            },
        )
    return rows


def _missing_rows(job: BurstJob) -> list[dict]:
    """The rows of a measurement whose photons could not be read: cp = cs = -1, the historical
    "no data" sentinel (photon count -2)."""
    return [
        _record(job.fname, det, colour_of(det), job.perdet.get(det, {}), None, float("nan"), -1, -1,
                reason=1)
        for _burst in job.bursts
        for det in job.det_order
    ]


def fit_jobs(jobs: list[BurstJob], threads: int = 1, *, should_stop=None, progress=None,
             errors: list | None = None) -> list[dict]:
    """Fit every burst of every job and detector: one row per ``(burst, detector)``, in job and
    burst order, a state split's columns in the same row.

    The fits are ``Fit2x.fit_many`` calls of :data:`CHUNK_ROWS` bursts on *threads* threads (the
    call releases the GIL, so the threads fit in parallel in one process: no worker processes,
    shared memory or pickling). *should_stop()* is read as each chunk finishes (then
    :class:`InterruptedError`); *progress(done, total)* counts bursts. A chunk that raises is
    named in *errors* and its bursts get rejected rows ("not finite"), never missing rows -- the
    table is merged by position.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    fitters: dict = {}
    tasks = []  # (job index, det, state, start, bursts)
    for j, job in enumerate(jobs):
        if job.rc is None or job.mt is None:
            continue
        for det in job.det_order:
            cfg = job.perdet[det]
            key = (id(job.perdet), det)
            if key not in fitters:
                fitters[key] = None if cfg.get("model") == "tail" else _build_fitter(cfg)
            for state in [None] + list(range(int(job.n_states))):
                for start in range(0, len(job.bursts), CHUNK_ROWS):
                    tasks.append((j, det, state, start, job.bursts[start : start + CHUNK_ROWS]))
    parts: dict = {}
    total = sum(len(job.bursts) for job in jobs)
    units = {j: max(1, len(job.det_order) * (1 + int(job.n_states))) for j, job in enumerate(jobs)}
    done = float(sum(len(job.bursts) for job in jobs if job.rc is None or job.mt is None))
    if progress is not None and done:
        progress(int(done), total)
    ex = ThreadPoolExecutor(max_workers=max(1, int(threads)), thread_name_prefix="burst-fit")
    try:
        pending = {
            ex.submit(_fit_chunk, jobs[j], det, fitters[(id(jobs[j].perdet), det)], bursts, state):
            (j, det, state, start, bursts)
            for j, det, state, start, bursts in tasks
        }
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            if should_stop is not None and should_stop():
                raise InterruptedError("The burst fit was stopped.")
            for fut in finished:
                j, det, state, start, bursts = pending.pop(fut)
                try:
                    rows = fut.result()
                except Exception as exc:  # noqa: BLE001 - named, and the bursts keep their rows
                    if errors is not None:
                        errors.append(f"{jobs[j].fname} ({det}) failed: {exc}")
                    cfg = jobs[j].perdet[det]
                    rows = [_record(jobs[j].fname, det, colour_of(det), cfg, None, float("nan"),
                                    0, 0, state=state, reason=3) for _b in bursts]
                parts[(j, det, state, start)] = rows
                done += len(bursts) / units[j]
                if progress is not None:
                    progress(min(int(done), total), total)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    out: list[dict] = []
    for j, job in enumerate(jobs):
        if job.rc is None or job.mt is None:
            out.extend(_missing_rows(job))
            continue
        states = [None] + list(range(int(job.n_states)))
        for i in range(len(job.bursts)):
            start, k = i - i % CHUNK_ROWS, i % CHUNK_ROWS
            for det in job.det_order:
                rec: dict = {}
                for state in states:
                    rec.update(parts[(j, det, state, start)][k])
                out.append(rec)
    return out


def pool_state_counts(job: BurstJob) -> dict:
    """Sum *job*'s burst photons into a decay per ``(detector, state)``: the cheap first pass of
    a split-by-state run, binning only. The pooled decay of a state -- every burst's photons of it
    -- is the state's robust lifetime and the start of its per-burst fits. Photons outside a
    burst never enter it: the sum runs over the burst slices the fit uses.

    Returns ``{detector: ndarray(n_states, 2, half_len)}`` -- parallel and perpendicular counts,
    unwindowed and unshifted (both linear, applied once to the sum by the caller); empty without
    photons or states."""
    if job.rc is None or job.mt is None or job.states is None or int(job.n_states) <= 0:
        return {}
    pooled = {}
    for det in job.det_order:
        cfg = job.perdet[det]
        n = int(cfg["half_len"])
        arr = np.zeros((int(job.n_states), 2, n), dtype=np.int64)
        for state in range(int(job.n_states)):
            for start in range(0, len(job.bursts), 4 * CHUNK_ROWS):
                cp, cs = burst_counts(job.rc, job.mt, job.bursts[start : start + 4 * CHUNK_ROWS],
                                      cfg["class_lut"], n, job.states, state)
                if cfg.get("mirror"):
                    cs = cp
                arr[state, 0] += cp.sum(axis=0)
                arr[state, 1] += cs.sum(axis=0)
        pooled[det] = arr
    return pooled


# -- a job in shared memory (one process of its own) ------------------------------------------ #
def _shared_job(names, bursts, det_order, perdet, fname="", shift=0, state_info=None):
    """``(BurstJob, blocks)`` of arrays in shared memory, attached by name (*names*:
    ``(rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype)``); close the blocks after."""
    rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype = names
    if rc_name is None or mt_name is None:
        return BurstJob(fname, list(bursts), None, None, list(det_order), perdet or {}, int(shift or 0)), []
    blocks = [_shm.SharedMemory(name=rc_name), _shm.SharedMemory(name=mt_name)]
    rc = np.ndarray(rc_shape, dtype=np.dtype(rc_dtype), buffer=blocks[0].buf)
    mt = np.ndarray(mt_shape, dtype=np.dtype(mt_dtype), buffer=blocks[1].buf)
    states, n_states = None, 0
    if state_info is not None:
        st_name, st_shape, st_dtype, n_states = state_info
        blocks.append(_shm.SharedMemory(name=st_name))
        states = np.ndarray(st_shape, dtype=np.dtype(st_dtype), buffer=blocks[2].buf)
    job = BurstJob(fname, list(bursts), rc, mt, list(det_order), perdet, int(shift or 0), states,
                   int(n_states))
    return job, blocks


def process_one_file_worker(args):
    """:func:`fit_jobs` of one file whose arrays are in shared memory (a process of its own);
    returns ``(rows, n_bursts)``.

    args = (fname, bursts, rc_name, rc_shape, rc_dtype_str, mt_name, mt_shape, mt_dtype_str,
            det_order, perdet_cfg, shift_int, state_info)
    """
    (fname, bursts, rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype, det_order, perdet,
     shift, state_info) = args
    job, blocks = _shared_job((rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype), bursts,
                              det_order, perdet, fname, shift, state_info)
    try:
        return fit_jobs([job]), len(bursts)
    finally:
        for block in blocks:
            block.close()


def pool_states_worker(args):
    """:func:`pool_state_counts` of one file whose arrays are in shared memory.

    args = (bursts, rc_name, rc_shape, rc_dtype_str, mt_name, mt_shape, mt_dtype_str,
            det_order, perdet_cfg, state_info)
    """
    (bursts, rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype, det_order, perdet,
     state_info) = args
    if state_info is None:
        return {}
    job, blocks = _shared_job((rc_name, rc_shape, rc_dtype, mt_name, mt_shape, mt_dtype), bursts,
                              det_order, perdet, state_info=state_info)
    try:
        return pool_state_counts(job)
    finally:
        for block in blocks:
            block.close()


def warm() -> None:
    """Load the fit's imports in a fresh worker, so the first real chunk does not pay for them."""
    from chisurf.core.fluorescence.mle.fit2x import Fit2x  # noqa: F401
