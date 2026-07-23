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


def _record(fname, det, color, cfg, x, two_istar, cp_sum, cs_sum):
    """One result row, laid out by the fitted model.

    ``fit23`` keeps its historical column set (tau/gamma/r0/rho + the two
    anisotropy columns) so its ``.b?4`` export is byte-for-byte unchanged. Every
    other model writes ``Tau`` (= ``x[0]``, the best lifetime) plus one column per
    free parameter named by the registry schema (``cfg['param_names']``). Pass
    ``x=None`` for a skipped/failed burst to emit NaN in every numeric slot.
    """
    def g(i):
        try:
            return float(x[i])
        except (TypeError, IndexError):
            return float('nan')

    rec = {
        'First File': fname,
        'Detector': det,
        'Ng-p-all': cp_sum,
        'Ng-s-all': cs_sum,
        f'Number of Photons (fit window) ({color})': cp_sum + cs_sum,
        f'2I*  ({color})': two_istar,
        f'Tau ({color})': g(0),
        f'BIFL scatter? ({color})': int(cfg['BIFL_scatter']),
        f'2I*: P+2S? ({color})': int(cfg['p2s_twoIstar']),
    }
    if cfg.get('model', 'fit23') == 'fit23':
        rec[f'gamma ({color})'] = g(1)
        rec[f'r0 ({color})'] = g(2)
        rec[f'rho ({color})'] = g(3)
        rec[f'r Scatter ({color})'] = g(6)
        rec[f'r Experimental ({color})'] = g(7)
    else:
        for i, nm in enumerate(cfg.get('param_names') or ()):
            rec[f'{nm} ({color})'] = g(i)
    return rec


def process_one_file_worker(args):
    """
    Process a single file in a separate process using shared memory
    for arrays. Returns (list_of_dicts, n_bursts_processed).

    args = (fname, bursts,
            rc_name, rc_shape, rc_dtype_str,
            mt_name, mt_shape, mt_dtype_str,
            det_order, perdet_cfg, shift_int)
    """
    (fname, bursts, rc_name, rc_shape, rc_dtype_str,
     mt_name, mt_shape, mt_dtype_str, det_order, perdet_cfg, shift_int) = args

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

            for det in det_order:
                cfg = perdet_cfg[det]
                n = half_len[det]
                cp_u32, cs_u32 = _hist2_split_core_classlut(
                    mt_bins, rc_slice, cfg['class_lut'], n
                )

                cp_sum = int(cp_u32.sum()); cs_sum = int(cs_u32.sum())
                color = det.lower()

                if (cp_sum + cs_sum) < int(cfg['min_photons']):
                    out.append(_record(fname, det, color, cfg,
                                       None, float('nan'), cp_sum, cs_sum))
                    continue

                # Write window only (no full clears)
                sb = int(cfg['sb']); eb = int(cfg['eb'])
                s0 = max(0, sb); s1 = min(n, eb)
                d = decay_buf[det]

                # zero previous windows
                pv_vv0, pv_vv1, pv_vh0, pv_vh1 = prev_ranges[det]
                if pv_vv1 > pv_vv0:
                    d[pv_vv0:pv_vv1] = 0.0
                if pv_vh1 > pv_vh0:
                    d[n + pv_vh0 : n + pv_vh1] = 0.0

                # copy current VV
                if s1 > s0:
                    d[s0:s1] = cp_u32[s0:s1]
                    # copy current VH with wrap shift (no np.roll)
                    if do_shift:
                        _copy_shifted(cs_u32, d, n, s0, s1, do_shift, n)
                    else:
                        d[n + s0 : n + s1] = cs_u32[s0:s1]

                # remember current ranges
                prev_ranges[det] = (s0, s1, s0, s1)

                # Fit (maximum likelihood via the raw tttrlib estimator)
                res = fitters[det](
                    data=d, initial_values=cfg['x0'], fixed=cfg['fixed'],
                )
                x = np.asarray(res['x'], dtype=np.float64)
                two_istar = float(res.get('twoIstar', float('nan')))
                out.append(_record(fname, det, color, cfg, x, two_istar,
                                   cp_sum, cs_sum))
        return out, len(bursts)
    finally:
        rc_sh.close()
        mt_sh.close()
