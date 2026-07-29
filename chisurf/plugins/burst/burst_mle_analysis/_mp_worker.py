# -*- coding: utf-8 -*-
import numpy as np
from multiprocessing import shared_memory as _shm

def _hist2_split_core_classlut(mt_bins: np.ndarray,
                               rc_slice: np.ndarray,
                               class_lut: np.ndarray,
                               half_len: int):
    """
    class_lut: int8 array (size max_rc+1) with {-1 ignore, 0=P, 1=S}.
    Returns (cp_u32, cs_u32).
    """
    cls = class_lut[rc_slice]  # int8 view
    valid = cls >= 0
    if not np.any(valid):
        return (np.zeros(half_len, dtype=np.uint32),
                np.zeros(half_len, dtype=np.uint32))
    b = mt_bins[valid]
    c = cls[valid].astype(np.int32, copy=False)
    h2 = np.bincount(b * 2 + c, minlength=2 * half_len)
    return (h2[0::2].astype(np.uint32, copy=False),
            h2[1::2].astype(np.uint32, copy=False))

def _copy_shifted(src_u32: np.ndarray,
                  dst_f64: np.ndarray,
                  dst_off: int,
                  s0: int, s1: int,
                  shift: int,
                  n: int):
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
        dst_f64[dst_off + s0 + first : dst_off + s1] = src_u32[0 : rem]


def _burst_slice(first_ph, last_ph) -> slice:
    """Return the photons of one burst as a slice into the file's arrays.

    ``Last Photon`` is the burst's last photon **inclusive** — that is what the
    ``.bur`` writer stores (``Number of Photons == last - first + 1``) and what
    the wizard's own photon-coverage mask assumes (``stops + 1``). The slice
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

    The batch worker and the interactive wizard now build through the same
    ``Fit2x`` facade, so batch results match the live preview by construction
    rather than by both of them independently reproducing the same setup. The
    facade also area-normalises the background, so gamma is a true 0..1 fraction
    (see okf/subsystems/mle-lifetime-fitting.md); it is no longer done here.
    """
    from chisurf.core.fluorescence.mle.fit2x import (
        Fit2x, Fit2xModel, Fit2xSettings,
    )
    return Fit2x(
        Fit2xSettings(
            dt=float(cfg['dt']),
            irf=np.asarray(cfg['irf'], dtype=np.float64),
            background=np.asarray(cfg['bg'], dtype=np.float64),
            period=float(cfg['period']),
            g_factor=float(cfg['g_factor']),
            l1=float(cfg['l1']),
            l2=float(cfg['l2']),
            p2s_twoIstar=bool(cfg['p2s_twoIstar']),
            soft_bifl_scatter=bool(cfg['BIFL_scatter']),
        ),
        model=Fit2xModel(cfg.get('model', 'fit23')),
    )


def _state_suffix(state):
    """How a sub-population is named in a column. ``None`` = all photons."""
    return "" if state is None else f" S{int(state)}"


def _record(fname, det, color, cfg, x, two_istar, cp_sum, cs_sum, state=None,
            extras=None):
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

    With ``state`` set, every measured column is suffixed (``Tau S0 (green)``)
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
            return float('nan')

    extras = extras or {}

    sfx = _state_suffix(state)
    rec = {}
    if state is None:
        rec['First File'] = fname
        rec['Detector'] = det
        rec['Ng-p-all'] = cp_sum
        rec['Ng-s-all'] = cs_sum
    else:
        rec[f'Ng-p{sfx}'] = cp_sum
        rec[f'Ng-s{sfx}'] = cs_sum
    # The all-photon 2I* column has two spaces after the star — historical, and
    # part of the .b?4 format, so it is preserved exactly rather than tidied.
    two_istar_key = f'2I*  ({color})' if state is None else f'2I*{sfx} ({color})'
    rec.update({
        f'Number of Photons (fit window){sfx} ({color})': cp_sum + cs_sum,
        two_istar_key: two_istar,
        f'Tau{sfx} ({color})': g(0),
        f'BIFL scatter?{sfx} ({color})': int(cfg['BIFL_scatter']),
        f'2I*: P+2S?{sfx} ({color})': int(cfg['p2s_twoIstar']),
    })
    if cfg.get('model', 'fit23') == 'fit23':
        rec[f'gamma{sfx} ({color})'] = g(1)
        rec[f'r0{sfx} ({color})'] = g(2)
        rec[f'rho{sfx} ({color})'] = g(3)
        rec[f'r Scatter{sfx} ({color})'] = float(extras.get('r_scatter', float('nan')))
        rec[f'r Experimental{sfx} ({color})'] = float(
            extras.get('r_experimental', float('nan')))
    else:
        for i, nm in enumerate(cfg.get('param_names') or ()):
            rec[f'{nm}{sfx} ({color})'] = g(i)
    return rec


def pool_states_worker(args):
    """Sum one file's burst photons into a decay per ``(detector, state)``.

    The cheap first pass of a split-by-state run: no fitting, only binning. Its
    product is the *pooled* decay of a state — every burst's photons of that
    state, over the whole measurement — which is the robust lifetime of the
    state (a single burst holds tens of photons; a state holds all of them) and
    the start value the per-burst fits of that state are then given.

    Photons outside a burst never enter it: the sum runs over exactly the burst
    slices the fit pass uses, so the pooled decay is the same population, only
    added up.

    args = (bursts,
            rc_name, rc_shape, rc_dtype_str,
            mt_name, mt_shape, mt_dtype_str,
            det_order, perdet_cfg, state_info)

    Returns ``{detector: ndarray(n_states, 2, half_len)}`` — parallel and
    perpendicular counts, unwindowed and unshifted, because both are cheap
    linear operations the caller applies once to the sum rather than per burst.
    """
    (bursts, rc_name, rc_shape, rc_dtype_str,
     mt_name, mt_shape, mt_dtype_str, det_order, perdet_cfg, state_info) = args

    if rc_name is None or mt_name is None or state_info is None:
        return {}

    st_name, st_shape, st_dtype, n_states = state_info
    if n_states <= 0:
        return {}

    rc_sh = _shm.SharedMemory(name=rc_name)
    mt_sh = _shm.SharedMemory(name=mt_name)
    st_sh = _shm.SharedMemory(name=st_name)
    try:
        rc_full = np.ndarray(rc_shape, dtype=np.dtype(rc_dtype_str), buffer=rc_sh.buf)
        mt_full = np.ndarray(mt_shape, dtype=np.dtype(mt_dtype_str), buffer=mt_sh.buf)
        state_full = np.ndarray(st_shape, dtype=np.dtype(st_dtype), buffer=st_sh.buf)

        pooled = {
            det: np.zeros((n_states, 2, int(perdet_cfg[det]['half_len'])), dtype=np.int64)
            for det in det_order
        }
        for first_ph, last_ph in bursts:
            sl = _burst_slice(first_ph, last_ph)
            rc_slice = rc_full[sl]
            mt_slice = mt_full[sl]
            st_slice = state_full[sl]
            for state in range(n_states):
                pick = st_slice == state
                if not pick.any():
                    continue
                mt_sel, rc_sel = mt_slice[pick], rc_slice[pick]
                for det in det_order:
                    cfg = perdet_cfg[det]
                    cp, cs = _hist2_split_core_classlut(
                        mt_sel, rc_sel, cfg['class_lut'], int(cfg['half_len'])
                    )
                    pooled[det][state, 0] += cp
                    pooled[det][state, 1] += cs
        return pooled
    finally:
        rc_sh.close()
        mt_sh.close()
        st_sh.close()


def process_one_file_worker(args):
    """
    Process a single file in a separate process using shared memory
    for arrays. Returns (list_of_dicts, n_bursts_processed).

    args = (fname, bursts,
            rc_name, rc_shape, rc_dtype_str,
            mt_name, mt_shape, mt_dtype_str,
            det_order, perdet_cfg, shift_int, state_info)

    ``state_info`` is ``None`` for an ordinary run, or
    ``(shm_name, shape, dtype_str, n_states)`` naming a per-photon state array
    (``-1`` = unassigned). With it, each burst is additionally fitted once per
    state, and those results are merged into the *same* row as extra columns —
    a sub-population is a column of the burst, not a row of its own.
    """
    (fname, bursts, rc_name, rc_shape, rc_dtype_str,
     mt_name, mt_shape, mt_dtype_str, det_order, perdet_cfg, shift_int,
     state_info) = args

    # Missing TTTR: emit defaults (cp=cs=-1 → photon count -2, matching the
    # historical "no data" sentinel).
    if rc_name is None or mt_name is None:
        out = []
        for _first, _last in bursts:
            for det in det_order:
                cfg = perdet_cfg.get(det, {})
                out.append(_record(fname, det, det.lower(), cfg,
                                    None, float('nan'), -1, -1))
        return out, len(bursts)

    # Attach shared memory
    rc_sh = _shm.SharedMemory(name=rc_name)
    mt_sh = _shm.SharedMemory(name=mt_name)
    st_sh = None
    state_full = None
    n_states = 0
    if state_info is not None:
        st_name, st_shape, st_dtype, n_states = state_info
        st_sh = _shm.SharedMemory(name=st_name)
        state_full = np.ndarray(st_shape, dtype=np.dtype(st_dtype), buffer=st_sh.buf)
    try:
        rc_full = np.ndarray(rc_shape, dtype=np.dtype(rc_dtype_str), buffer=rc_sh.buf)
        mt_bins_full = np.ndarray(mt_shape, dtype=np.dtype(mt_dtype_str), buffer=mt_sh.buf)

        # Per-detector fitters, buffers, previous ranges
        fitters = {}
        half_len = {}
        decay_buf = {}
        prev_ranges = {}  # det -> (vv_s0,vv_s1,vh_s0,vh_s1)
        for det in det_order:
            cfg = perdet_cfg[det]
            fitters[det] = _build_fitter(cfg)
            n = int(cfg['half_len'])
            half_len[det] = n
            decay_buf[det] = np.zeros(2 * n, dtype=np.float64)
            prev_ranges[det] = (0, 0, 0, 0)

        out = []
        do_shift = int(shift_int) if shift_int else 0

        for first_ph, last_ph in bursts:
            sl = _burst_slice(first_ph, last_ph)
            rc_slice = rc_full[sl]
            mt_bins = mt_bins_full[sl]
            st_slice = state_full[sl] if state_full is not None else None

            for det in det_order:
                cfg = perdet_cfg[det]
                n = half_len[det]
                color = det.lower()

                # All the burst's photons, then one pass per state. Each pass
                # contributes columns to the *same* row: a sub-population is a
                # column of the burst, not a row of its own.
                rec = {}
                for state in [None] + list(range(n_states)):
                    if state is None:
                        mt_sel, rc_sel = mt_bins, rc_slice
                        floor = int(cfg['min_photons'])
                    else:
                        pick = st_slice == state
                        mt_sel, rc_sel = mt_bins[pick], rc_slice[pick]
                        # Split by colour *and* state a burst is thin, so the
                        # state passes get their own (lower) threshold.
                        floor = int(cfg.get('state_min_photons') or cfg['min_photons'])

                    cp_u32, cs_u32 = _hist2_split_core_classlut(
                        mt_sel, rc_sel, cfg['class_lut'], n
                    )
                    cp_sum = int(cp_u32.sum()); cs_sum = int(cs_u32.sum())

                    if (cp_sum + cs_sum) < floor:
                        rec.update(_record(fname, det, color, cfg, None,
                                           float('nan'), cp_sum, cs_sum, state=state))
                        continue

                    # Write only the fit window, zeroing the previous burst's.
                    sb = int(cfg['sb']); eb = int(cfg['eb'])
                    s0 = max(0, sb); s1 = min(n, eb)
                    d = decay_buf[det]
                    pv_vv0, pv_vv1, pv_vh0, pv_vh1 = prev_ranges[det]
                    if pv_vv1 > pv_vv0:
                        d[pv_vv0:pv_vv1] = 0.0
                    if pv_vh1 > pv_vh0:
                        d[n + pv_vh0 : n + pv_vh1] = 0.0
                    if s1 > s0:
                        d[s0:s1] = cp_u32[s0:s1]
                        if do_shift:
                            _copy_shifted(cs_u32, d, n, s0, s1, do_shift, n)
                        else:
                            d[n + s0 : n + s1] = cs_u32[s0:s1]
                    prev_ranges[det] = (s0, s1, s0, s1)

                    # A state's fit starts from that state's *pooled* lifetime
                    # when one was fitted (see ``pool_states_worker``): the
                    # sub-population of a single burst is thin, and starting it
                    # at the panel's one global guess pulls every state toward
                    # the same answer, which is the thing the split exists to
                    # tell apart.
                    x0 = cfg['x0']
                    if state is not None:
                        x0 = (cfg.get('state_x0') or {}).get(state, x0)
                    res = fitters[det](
                        data=d, initial_values=x0, fixed=cfg['fixed'],
                    )
                    x = np.asarray(res.x, dtype=np.float64)
                    two_istar = float(res.twoIstar)
                    rec.update(_record(
                        fname, det, color, cfg, x, two_istar, cp_sum, cs_sum,
                        state=state,
                        extras={'r_scatter': res.r_scatter,
                                'r_experimental': res.r_experimental}))
                out.append(rec)
        return out, len(bursts)
    finally:
        rc_sh.close()
        if st_sh is not None:
            st_sh.close()
        mt_sh.close()
