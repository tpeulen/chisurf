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


def _build_fitter(cfg):
    """Build the raw tttrlib estimator for this detector's configuration.

    The batch worker uses the same estimator the interactive wizard builds
    (``wizard.create_fit_instance``): the class named by the registry
    (``cfg['method']``, e.g. ``Fit23``/``Fit24``/``Fit25``) rather than the
    ``Fit2x`` facade, so batch results match the live preview exactly for every
    model. The background is area-normalised here (gamma is then a true 0..1
    fraction) — the same normalisation the facade does in
    ``Fit2xSettings.__post_init__``; see okf/subsystems/mle-lifetime-fitting.md.
    """
    import tttrlib
    bg = np.asarray(cfg['bg'], dtype=np.float64)
    bg_sum = float(bg.sum())
    if bg_sum > 0.0:
        bg = bg / bg_sum
    cls = getattr(tttrlib, cfg.get('method', 'Fit23'))
    return cls(
        dt=float(cfg['dt']),
        irf=np.asarray(cfg['irf'], dtype=np.float64),
        background=bg,
        period=float(cfg['period']),
        g_factor=float(cfg['g_factor']),
        l1=float(cfg['l1']),
        l2=float(cfg['l2']),
        p2s_twoIstar_flag=bool(cfg['p2s_twoIstar']),
        soft_bifl_scatter_flag=bool(cfg['BIFL_scatter']),
    )


def _state_suffix(state):
    """How a sub-population is named in a column. ``None`` = all photons."""
    return "" if state is None else f" S{int(state)}"


def _record(fname, det, color, cfg, x, two_istar, cp_sum, cs_sum, state=None):
    """One result row, laid out by the fitted model.

    ``fit23`` keeps its historical column set (tau/gamma/r0/rho + the two
    anisotropy columns) so its ``.b?4`` export is byte-for-byte unchanged. Every
    other model writes ``Tau`` (= ``x[0]``, the best lifetime) plus one column per
    free parameter named by the registry schema (``cfg['param_names']``). Pass
    ``x=None`` for a skipped/failed burst to emit NaN in every numeric slot.

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
        rec[f'r Scatter{sfx} ({color})'] = g(6)
        rec[f'r Experimental{sfx} ({color})'] = g(7)
    else:
        for i, nm in enumerate(cfg.get('param_names') or ()):
            rec[f'{nm}{sfx} ({color})'] = g(i)
    return rec


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
            sl = slice(int(first_ph), int(last_ph))
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

                    res = fitters[det](
                        data=d, initial_values=cfg['x0'], fixed=cfg['fixed'],
                    )
                    x = np.asarray(res['x'], dtype=np.float64)
                    two_istar = float(res.get('twoIstar', float('nan')))
                    rec.update(_record(fname, det, color, cfg, x, two_istar,
                                       cp_sum, cs_sum, state=state))
                out.append(rec)
        return out, len(bursts)
    finally:
        rc_sh.close()
        if st_sh is not None:
            st_sh.close()
        mt_sh.close()
