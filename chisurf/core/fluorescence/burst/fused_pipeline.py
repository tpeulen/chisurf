"""The burst pipeline as one tttrlib call per measurement (``tttrlib.BurstPipeline``).

ChiSurf's burst pipeline crossed into Python between every stage: the photon arrays were
copied out for each filter, a mask per detector was built for the summary, the per-burst decays
were histogrammed into a dense matrix and that matrix became a list of floats on its way into the
fit. ``tttrlib.BurstPipeline`` does the same work natively and keeps the results in buffers it owns;
this module is the thin layer between it and ChiSurf's settings and call sites:

* :func:`search_and_summarize` -- the burst search, selection mask and the burst table of
  :func:`~chisurf.plugins.burst.burst_selection.api.selection.analyze_file` (the search,
  :func:`apply_photon_filters`, :func:`find_bursts`, :func:`drop_short_bursts` and
  :func:`~chisurf.core.fio.fluorescence.burst.generate_burst_dataframe`), in one call.
* :func:`strict_background` -- :func:`~.irf_bg.strict_background_mask` with the accept test, its
  histograms instead of a photon mask, and the ``bg`` patterns of
  :func:`~.irf_bg.extract_mle_irf_background` made from those histograms.
* :func:`fit_session` -- the per-burst fits of ``MleSession.run_batch``: decays and fits of every
  burst in two calls per file, the rows ``_mp_worker.fit_jobs`` returns.

Each entry point returns ``None`` when the configuration is one the native pipeline does not cover
(another search algorithm, a photon pre-filter, a split by state); the caller then runs the
Python path. It is used when :func:`enabled`: on by default since its equivalence with the Python
path was shown on DNA13bp_3 (2026-11-05); setting ``burst.fused_pipeline`` or environment
``CHISURF_FUSED_BURST_PIPELINE=0`` turns it off. The design and the measured equivalence are the
OKF concept ``okf/architecture/fused-burst-pipeline.md``.
"""

from __future__ import annotations

import json
import os
import typing

import numpy as np

#: Environment switch; overrides the setting.
ENV = "CHISURF_FUSED_BURST_PIPELINE"
#: The setting (``chisurf.core.settings.cs_settings["burst"]["fused_pipeline"]``) when present.
SETTING = ("burst", "fused_pipeline")
#: Used when neither the environment nor the setting says.
DEFAULT = True

#: Crossings of the last calls (Python -> C++ calls and bytes handed over), for the benchmark.
last_stats: dict = {}


def available() -> bool:
    """Whether the installed tttrlib has the fused pipeline."""
    try:
        import tttrlib
    except ImportError:  # pragma: no cover - tttrlib is a hard dependency
        return False
    return hasattr(tttrlib, "BurstPipeline") and hasattr(tttrlib, "StrictBackground")


def enabled() -> bool:
    """Whether the call sites should use the fused pipeline (and it is installed)."""
    value = os.environ.get(ENV)
    if value is None:
        try:
            import chisurf.core.settings as _settings

            value = (_settings.cs_settings.get(SETTING[0]) or {}).get(SETTING[1])
        except Exception:  # noqa: BLE001 - no settings (a bare test process): the default
            value = None
    if value is None:
        on = DEFAULT
    elif isinstance(value, str):
        on = value.strip().lower() not in ("", "0", "false", "no", "off")
    else:
        on = bool(value)
    return on and available()


def _gates(ranges) -> list:
    return [[int(r[0]), int(r[1])] for r in (ranges or []) if r is not None and len(r) >= 2]


def _detectors(detectors: typing.Mapping[str, typing.Mapping]) -> list:
    return [
        {"name": str(name), "chs": [int(c) for c in (info or {}).get("chs", [])],
         "gates": _gates((info or {}).get("micro_time_ranges"))}
        for name, info in (detectors or {}).items()
    ]


def _windows(windows: typing.Mapping[str, tuple]) -> list:
    return [{"name": str(w), "lo": int(r[0]), "hi": int(r[1])} for w, r in (windows or {}).items()]


# ---------------------------------------------------------------------------------------------- #
# Burst search and table
# ---------------------------------------------------------------------------------------------- #

def search_config(tttr, settings, detectors: dict, windows: dict, *,
                  feature_resolution: float | None = None) -> dict | None:
    """The ``BurstPipeline`` configuration of *settings* (``AnalysisSettings``), or ``None``.

    ``None`` when the native pipeline does not reproduce the configuration: a filter mode other
    than the tttrlib registry, an algorithm other than ``cusum_sprt`` / ``sliding_window``, or a
    channel / micro-time pre-filter. *detectors* and *windows* are the ones applied to this
    measurement (``applied_windows``), as ``generate_burst_dataframe`` gets them.
    """
    from chisurf.core.fio.fluorescence.burst import micro_time_resolution_ns
    from chisurf.core.fluorescence.burst import tttrlib_search
    from chisurf.plugins.burst.burst_selection.api.models import BurstFilterMode

    pf = settings.photon_filter
    if pf.channels or pf.microtime_ranges:
        return None
    mode = BurstFilterMode(pf.used_filter)
    search: dict = {"algorithm": "sliding_window", "scope": "all", "parameters": {}}
    if pf.filter_active:
        if mode != BurstFilterMode.TTTRLIB or not tttrlib_search.is_available():
            return None
        algorithm = pf.tttrlib_search.algorithm
        if algorithm not in ("cusum_sprt", "sliding_window"):
            return None
        params = dict(tttrlib_search.defaults(algorithm))
        params.update(dict(pf.tttrlib_search.parameters or {}))
        search_detectors = params.pop(tttrlib_search.SEARCH_DETECTORS, None)
        search = {"algorithm": algorithm, "scope": "all", "parameters": params}
        if algorithm == "cusum_sprt":
            if search_detectors:
                search["scope"] = "detectors"
                search["detectors"] = _detectors(search_detectors)
            if float(params.get("background_cps") or 0.0) <= 0.0:
                # the two estimates of tttrlib_search, which read the photons in Python; only
                # reached when no background rate is set
                if search_detectors:
                    total = sum(tttrlib_search.detector_backgrounds_cps(tttr, search_detectors).values())
                    if total <= 0:
                        total = tttrlib_search.estimate_background_cps(
                            tttr, sorted({c for d in search_detectors.values() for c in (d or {}).get("chs", [])}))
                else:
                    total = tttrlib_search.estimate_background_cps(tttr)
                if total > 0:
                    params["background_cps"] = float(total)
    dt = pf.delta_macro_time_filter
    gap = int(pf.max_gap) if (pf.use_gap_fill and int(pf.max_gap) > 0) else 0
    res = float(tttr.header.macro_time_resolution)
    return {
        "detectors": _detectors(detectors),
        "windows": _windows(windows),
        "search": search,
        "selection": {
            "filter_active": bool(pf.filter_active),
            "invert": bool(pf.invert_filter) and mode != BurstFilterMode.COUNT_RATE,
            "max_gap": gap,
            "min_photons": max(2, int(settings.burst_detection.min_photons)),
            "dt_min_active": bool(dt.dT_min_active), "dt_min_ms": float(dt.dT_min),
            "dt_max_active": bool(dt.dT_max_active), "dt_max_ms": float(dt.dT_max),
        },
        "decays": {"binning": 1, "n_bins": 1},
        "micro_time_resolution_ns": float(micro_time_resolution_ns(tttr)),
        "macro_time_resolution": res,
        "feature_macro_time_resolution": float(feature_resolution or res),
    }


def search(tttr, settings, detectors: dict, windows: dict, *, feature_resolution=None,
           pipeline_out: list | None = None):
    """Run the configured search natively: the ``BurstPipelineResult``, or ``None`` (see
    :func:`search_config`). *pipeline_out* receives the ``BurstPipeline`` (for progress and Stop
    from another thread)."""
    import tttrlib

    cfg = search_config(tttr, settings, detectors, windows, feature_resolution=feature_resolution)
    if cfg is None:
        return None
    text = json.dumps(cfg)
    pipe = tttrlib.BurstPipeline(text)
    if pipeline_out is not None:
        pipeline_out.append(pipe)
    result = pipe.run(tttr)
    last_stats["search"] = {"calls": 2, "bytes_in": len(text), **result.stats()}
    return result


def start_stop(result) -> np.ndarray:
    """``(n, 2)`` inclusive ``[first, last]`` photon indices of *result* (a copy: 2 x n int64)."""
    return np.column_stack([result.column_view("first_photon"), result.column_view("last_photon")])


def burst_table(result, file_name: str, detectors: dict, windows: dict,
                include_interleaved_zeros: bool = True):
    """The burst table ``generate_burst_dataframe`` writes, filled from *result*'s columns.

    Walks ``burst_features.yaml`` exactly as the Python summary does: the declaration names the
    columns, the native result holds their values.
    """
    import pathlib

    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst import burst_feature_declaration
    from chisurf.core.fluorescence import detector_names as dn

    n = len(result)
    file_name = pathlib.Path(file_name).name  # as generate_burst_dataframe writes it
    declaration = burst_feature_declaration()
    cols, values, text = [], [], []
    for group in declaration["groups"]:
        scope = group["scope"]
        entries = [(e["column"], e["source"]) for e in group["columns"]]
        if scope == "static":
            for template, source in entries:
                cols.append(template)
                if source == "file_name":
                    values.append([file_name] * n)
                    text.append(True)
                else:
                    values.append(result.column_view(source))
                    text.append(False)
        elif scope == "detector":
            for d in detectors:
                for template, source in entries:
                    cols.append(template.format(detector=d, Detector=dn.label(d)))
                    values.append(result.column_view(f"{source}|{d}"))
                    text.append(False)
        elif scope == "window_detector":
            for w, (r0, r1) in windows.items():
                for d in detectors:
                    for template, source in entries:
                        cols.append(template.format(window=w, detector=d, Detector=dn.label(d), r0=r0, r1=r1))
                        values.append(result.column_view(f"{source}|{w}@{d}"))
                        text.append(False)
        else:
            raise ValueError(f"burst_features.yaml: unknown scope {scope!r}")
    if declaration.get("trailing_blank", False):
        cols.append("")
        values.append([""] * n)
        text.append(True)
    columns = []
    for v, is_text in zip(values, text):
        if is_text:
            filler = "" if (v and v[0] == "") else 0
            if include_interleaved_zeros and n:
                column = [filler] * (2 * n + 1)
                column[1::2] = v
            else:
                column = list(v)
            columns.append(np.array(column, dtype=object))
        else:
            v = np.asarray(v)
            if include_interleaved_zeros and n:
                column = np.zeros(2 * n + 1, dtype=v.dtype)
                column[1::2] = v
            else:
                column = np.array(v)
            columns.append(column)
    return store_from_arrays(dict(zip(cols, columns)))


def search_and_summarize(tttr, settings, applied: dict, file_name: str,
                         feature_resolution: float | None = None, pipeline_out: list | None = None):
    """``(start_stop, table, result)`` of the search and summary of ``analyze_file``, or ``None``."""
    detectors = applied.get("detectors") or {}
    windows = applied.get("windows") or {}
    result = search(tttr, settings, detectors, windows, feature_resolution=feature_resolution,
                    pipeline_out=pipeline_out)
    if result is None:
        return None
    return start_stop(result), burst_table(result, file_name, detectors, windows), result


# ---------------------------------------------------------------------------------------------- #
# Strict background
# ---------------------------------------------------------------------------------------------- #

class StrictBackground(typing.NamedTuple):
    """:class:`~.irf_bg.StrictBackground` without the photon mask, with the kept photons'
    raw micro-time histogram per routing channel instead (``histograms[channel]``)."""

    seconds: float
    total_seconds: float
    rate_khz: float
    threshold_khz: float
    photons: int
    iterations: int
    warning: str
    rate_scale: float
    histograms: dict

    @property
    def fraction(self) -> float:
        """The share of the measurement's time kept as background."""
        return self.seconds / self.total_seconds if self.total_seconds > 0 else 0.0

    @property
    def mask(self):
        """``None``: the native selection never builds a photon mask (use :attr:`histograms`)."""
        return None


def binned(hist: np.ndarray, binning: int) -> np.ndarray:
    """A raw micro-time histogram at *binning* (channel ``m`` to bin ``m // binning``)."""
    b = max(1, int(binning))
    if b == 1:
        return np.asarray(hist, dtype=np.float64)
    n = -(-hist.size // b)
    padded = np.zeros(n * b, dtype=np.float64)
    padded[: hist.size] = hist
    return padded.reshape(n, b).sum(axis=1)


def _summed(histograms: dict, channels) -> np.ndarray:
    rows = [histograms[c] for c in channels if c in histograms]
    if not rows:
        return np.zeros(0)
    return np.sum(rows, axis=0).astype(np.float64)


def strict_background(tttr, first, last, channels, *, accept_hist=None, margin_ms=2.0,
                      margin_fraction=0.5, photon_window=10, false_alarm=0.01, iterations=4,
                      min_fraction=0.01, min_seconds=1.0, rate_khz=None, tighten=0.7,
                      max_tighten=8, histogram_channels=None) -> StrictBackground:
    """:func:`~.irf_bg.strict_background_mask`, natively, on the bursts ``[first, last]``.

    *accept_hist(histograms)* is the accept test on the kept photons' histograms (``None``: no
    test). The accept loop is the original's; each tightening is one call.
    """
    import tttrlib

    chs = sorted({int(c) for c in (channels or [])})
    hist_chs = sorted({int(c) for c in (histogram_channels or chs)})
    cfg = json.dumps({
        "channels": chs, "histogram_channels": hist_chs, "margin_ms": float(margin_ms),
        "margin_fraction": float(margin_fraction), "photon_window": int(photon_window),
        "false_alarm": float(false_alarm), "iterations": int(iterations),
        "rate_khz": float(rate_khz or 0.0),
    })
    first = np.ascontiguousarray(first, dtype=np.int64)
    last = np.ascontiguousarray(last, dtype=np.int64)
    sb = tttrlib.StrictBackground(tttr, first, last, cfg)
    calls = 2

    def hists(r) -> dict:
        h = r.histogram
        return {c: h[k] for k, c in enumerate(r.histogram_channels())}

    r = sb.select()
    calls += 1
    seconds, threshold, rate, done = r.seconds, r.threshold_khz, r.rate_khz, r.iterations
    accepted = True
    if accept_hist is not None:
        accepted = r.photons > 0 and bool(accept_hist(hists(r)))
        steps = 0
        while not accepted and steps < int(max_tighten) and seconds >= min_seconds:
            steps += 1
            done += 1
            threshold *= float(tighten)
            r = sb.keep_at(threshold)
            calls += 1
            seconds = r.seconds
            if seconds < min_seconds or not r.photons:
                break
            accepted = bool(accept_hist(hists(r)))
        if accepted:
            rate = sb.gap_rate(threshold / sb.factor())
    total = r.total_seconds
    warning = ""
    if not accepted:
        warning = (
            f"no stretch of the measurement is at the background level (still fluorescence at "
            f"a local rate of {threshold:.2g} kHz, {seconds:.2g} s left)"
        )
    elif seconds < min_seconds or (total > 0 and seconds / total < min_fraction):
        warning = (
            f"only {seconds:.2g} s ({seconds / total:.1%} of the measurement) are at the "
            "background level: too little for a background"
            if total > 0
            else "no background time"
        )
    last_stats["strict"] = {"calls": calls, "bytes_in": int(first.nbytes + last.nbytes + len(cfg))}
    return StrictBackground(
        float(seconds), float(total), float(rate), float(threshold), int(r.photons), int(done),
        warning, float(sb.rate_scale_at(rate)), hists(r),
    )


def background_patterns(tttr, histograms: dict, detectors: dict, binning: int,
                        irf_model: str = "experimental") -> dict:
    """``{det: vv|vh bg}``: ``extract_mle_irf_background`` of the photons *histograms* counts."""
    from chisurf.core.fluorescence.burst import extract_mle_irf_background

    patterns = extract_mle_irf_background(tttr, detectors, micro_time_binning=int(binning),
                                          histograms=histograms, irf_model=irf_model)
    return {d: np.asarray(p["bg"], dtype=float) for d, p in patterns.items()}


def accept_from_histograms(judged: dict, detectors: dict, binning: int, dt: float, gate_window,
                           max_share: float):
    """The accept test of ``MleSession._background_shaped`` on histograms.

    *judged* maps a detector to its IRF; *gate_window(det, half)* is the session's. A detector's
    histogram is its channels' kept photons at *binning*, clipped into ``[0, half - 1]``.
    """
    from chisurf.core.fluorescence.burst.irf_bg import flat_scatter_background

    def accept(histograms: dict) -> bool:
        for det, irf in judged.items():
            chs = detectors[det].get("chs", [])
            half = irf.size // 2
            parts = [chs[::2], chs[1::2]] if len(chs) > 1 else [chs, chs]
            halves = []
            for p in parts:
                h = binned(_summed(histograms, p), binning)
                clipped = np.zeros(half)
                if h.size:
                    clipped[: min(half, h.size)] = h[:half]
                    if h.size > half:
                        clipped[half - 1] += h[half:].sum()
                halves.append(clipped)
            hist = np.hstack(halves)
            if hist.sum() <= 0:
                continue
            _, found = flat_scatter_background(hist, irf, float(dt or 1.0), gate_window(det, half))
            if sum(found["fluorescence"]) > max_share * hist.sum():
                return False
        return True

    return accept


# ---------------------------------------------------------------------------------------------- #
# Burst MLE fits
# ---------------------------------------------------------------------------------------------- #

def _poll(call, pipe, should_stop=None, progress=None, every: float = 0.05):
    """Run *call* (a ``BurstPipeline`` method, GIL released) on a thread while this one reads
    the pipeline's progress counter and turns *should_stop()* into ``pipe.cancel()``: Stop and the
    progress bar keep working with no callback into Python from the native loop."""
    import threading

    box: dict = {}

    def target():
        try:
            box["value"] = call()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            box["error"] = exc

    worker = threading.Thread(target=target, name="burst-pipeline", daemon=True)
    worker.start()
    stopped = False
    while worker.is_alive():
        worker.join(every)
        if should_stop is not None and not stopped and should_stop():
            pipe.cancel()
            stopped = True
        if progress is not None:
            progress(int(pipe.progress_fits()))
    if "error" in box:
        raise box["error"]
    if stopped:
        raise InterruptedError("The burst fit was stopped.")
    return box.get("value")


def _fit_entry(det: str, cfg: dict, n: int, shift: int, timing) -> tuple[dict, typing.Any]:
    """The pipeline's fit entry of *det* (``batch_config`` + ``half_len`` etc.), and the facade
    ``Fit2x`` it reproduces (``None`` for the tail fit)."""
    import tttrlib

    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import _build_fitter

    dt, period = timing
    window = cfg.get("fit_window")
    lo, hi = (window if window else (cfg.get("sb", 0), cfg.get("eb", 0)))
    entry = {
        "detector": det, "model": cfg.get("model", "fit23"), "n": int(n),
        "sb": int(cfg["sb"]), "eb": int(cfg["eb"]),
        "vh_sb": int(cfg.get("vh_sb", cfg["sb"])), "vh_eb": int(cfg.get("vh_eb", cfg["eb"])),
        "shift": int(shift), "min_photons": int(cfg["min_photons"]), "mirror": bool(cfg.get("mirror")),
        "dt": float(dt), "reject_lo": int(lo), "reject_hi": int(hi),
    }
    if entry["model"] == "tail":
        return entry, None
    fitter = _build_fitter(dict(cfg, dt=dt, period=period))
    s = fitter.settings
    setup_kwargs = dict(dt=s.dt, period=s.period, g_factor=s.g_factor, l1=s.l1, l2=s.l2,
                        soft_bifl_scatter_flag=s.soft_bifl_scatter,
                        objective="p2s_mle" if s.p2s_twoIstar else "poisson_mle")
    if s.convolution_stop is not None:
        setup_kwargs["convolution_stop"] = int(s.convolution_stop)
    n_par = int(fitter._n_parameters)
    fixed = np.asarray(cfg["fixed"]).ravel()
    names = list(tttrlib.result_names(entry["model"]))
    entry.update({
        "setup": list(tttrlib.setup_vector(entry["model"], **setup_kwargs)),
        "irf": list(fitter._problem.irf),
        "background": list(fitter._problem.background),
        "x0": [float(v) for v in fitter._parameters(np.asarray(cfg["x0"], dtype=np.float64))],
        "link": [-1 if (i >= fixed.size or int(fixed[i])) else 0 for i in range(n_par)],
        "fit_start": int(s.fit_window[0]) if s.fit_window else 0,
        "fit_stop": int(s.fit_window[1]) if s.fit_window else int(n),
        "converged_index": names.index("converged") if "converged" in names else -1,
    })
    return entry, fitter


#: Chunks of a file's bursts when the fit's thread count may change while it runs.
FIT_CHUNKS = 8


def fit_session(session, configs: dict, det_order: list, binning: int, *, threads=None,
                should_stop=None, progress=None, errors: list | None = None):
    """The rows ``_mp_worker.fit_jobs`` returns for *session*'s bursts, fitted natively.

    Per file: one ``decays`` call (the CSR decays of every burst and decay group, from the
    TTTR in place) and one ``fit`` call (every detector, every burst over the photon floor, on
    *threads* threads). ``None`` when the session splits by state (not fused).

    *threads* may be a callable: the count is then read again before each of
    :data:`FIT_CHUNKS` chunks of a file's bursts (one ``decays`` and one ``fit`` call each), so
    a fit started on few threads (Burst MLE ahead of Next) takes more once the user waits for it.
    A burst's fit does not depend on the others', so the rows are the same either way.
    """
    import tttrlib

    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import (
        BurstJob,
        _missing_rows,
        _record,
        colour_of,
    )
    from chisurf.plugins.burst.burst_mle_analysis.engine import numeric_column

    if session.split_by_state:
        return None
    from pathlib import Path

    from chisurf.core.datastore import column_names

    identity = "_measurement_path" if "_measurement_path" in column_names(session.df_bursts) else "First File"
    first_file = np.array([str(v) for v in session.df_bursts[identity]], dtype=object)
    fp = numeric_column(session.df_bursts, "First Photon").astype(np.int64)
    lp = numeric_column(session.df_bursts, "Last Photon").astype(np.int64)
    shift = int(session.settings.shift or 0)
    out: list[dict] = []
    total = int(fp.size)
    done = 0
    stats = {"calls": 0, "bytes_in": 0, "bursts": total, "native_s": 0.0, "rows_s": 0.0}
    import time
    for fname in dict.fromkeys(first_file.tolist()):
        mask = first_file == fname
        first, last = np.ascontiguousarray(fp[mask]), np.ascontiguousarray(lp[mask])
        tttr = session.tttrs.get(fname if identity == "_measurement_path" else Path(fname).stem)
        if tttr is None:
            out.extend(_missing_rows(BurstJob(fname, list(zip(first.tolist(), last.tolist())),
                                              None, None, det_order, configs, shift)))
            done += int(first.size)
            continue
        timing = session.timing_ns(tttr, binning)
        detectors = {d: session.detectors[d] for d in det_order}
        n_bins = {d: int(configs[d]["half_len"]) for d in det_order}
        # one decays call per distinct histogram length (normally one)
        by_len: dict[int, list[str]] = {}
        for d in det_order:
            by_len.setdefault(n_bins[d], []).append(d)
        cols: dict[str, dict] = {}
        n_threads = threads if callable(threads) else (lambda: threads)
        # one chunk of every burst, unless the thread count may change while the fit runs
        size = max(1, -(-int(first.size) // FIT_CHUNKS)) if callable(threads) else max(1, int(first.size))
        chunks = [(a, min(int(first.size), a + size)) for a in range(0, int(first.size), size)] or [(0, 0)]
        for n, dets in by_len.items():
            pipe_cfg = json.dumps({
                "detectors": [{"name": d, "chs": [int(c) for c in detectors[d].get("chs", [])], "gates": []}
                              for d in dets],
                "windows": [], "search": {"algorithm": "sliding_window"},
                "decays": {"binning": int(binning), "n_bins": int(n)},
                "features": False, "confidence": False,
            })
            entries, fitters = [], {}
            for d in dets:
                cfg = dict(configs[d], mirror=len(detectors[d].get("chs", [])) < 2)
                if timing[0] is not None and timing[1] is not None:
                    cfg["dt"], cfg["period"] = timing
                entry, fitter = _fit_entry(d, cfg, n, shift, (cfg["dt"], cfg["period"]))
                entries.append(entry)
                fitters[d] = (cfg, fitter)
            parts: dict[str, list[dict]] = {d: [] for d in dets}
            for a, b in chunks:
                t_native = time.perf_counter()
                pipe = tttrlib.BurstPipeline(pipe_cfg)
                result = pipe.decays(tttr, first[a:b], last[a:b], int(binning), int(n))
                fit_text = json.dumps({"fits": entries, "n_threads": int(n_threads() or 0)})
                _poll(lambda: pipe.fit(result, fit_text), pipe, should_stop,
                      None if progress is None else (lambda k, _d=done + a: progress(min(total, _d + k), total)))
                stats["native_s"] += time.perf_counter() - t_native
                stats["calls"] += 4 + 2 * len(dets)
                stats["bytes_in"] += len(pipe_cfg) + len(fit_text) + int(first[a:b].nbytes + last[a:b].nbytes)
                for d in dets:
                    cfg, fitter = fitters[d]
                    p = f"fit|{d}|"
                    n_par = 3 if fitter is None else int(fitter._n_parameters)
                    names = list(tttrlib.result_names(cfg.get("model"))) if fitter is not None else []
                    # one list per column, once: indexing a view per row and value is ~10x slower
                    parts[d].append({
                        "ng_p": result.column_view(p + "ng_p").tolist(),
                        "ng_s": result.column_view(p + "ng_s").tolist(),
                        "reason": result.column_view(p + "reason").tolist(),
                        "objective": result.column_view(p + "objective").tolist(),
                        "x": np.column_stack([result.column_view(f"{p}x|{i}") for i in range(n_par)]),
                        "r": {nm: result.column_view(f"{p}r|{k}").tolist() for k, nm in enumerate(names)},
                    })
            for d in dets:
                got = parts[d]
                cols[d] = {
                    "cfg": fitters[d][0],
                    **{key: [v for c in got for v in c[key]] for key in ("ng_p", "ng_s", "reason", "objective")},
                    "x": got[0]["x"] if len(got) == 1 else np.vstack([c["x"] for c in got]),
                    "r": {nm: [v for c in got for v in c["r"][nm]] for nm in got[0]["r"]},
                }
        t_rows = time.perf_counter()
        nan_column = [float("nan")] * int(first.size)
        for i in range(first.size):
            if should_stop is not None and should_stop():
                raise InterruptedError("The burst fit was stopped.")
            for d in det_order:
                c = cols[d]
                cfg = c["cfg"]
                reason = int(c["reason"][i])
                cp, cs = int(c["ng_p"][i]), int(c["ng_s"][i])
                if reason == 1:  # under the photon floor: never fitted
                    out.append(_record(fname, d, colour_of(d), cfg, None, float("nan"), cp, cs, reason=1))
                    continue
                x = c["x"][i]
                if cfg.get("model") == "tail":
                    out.append(_record(fname, d, colour_of(d), cfg, None if reason else x, float("nan"),
                                       cp, cs, reason=reason))
                    continue
                r = c["r"]
                extras = None if reason else {
                    "r_scatter": float(r.get("r_scatter", nan_column)[i]),
                    "r_experimental": float(r.get("r_experimental", nan_column)[i]),
                    "selected_index": float(r.get("selected_index", nan_column)[i]),
                }
                out.append(_record(fname, d, colour_of(d), cfg, None if reason else x,
                                   float(c["objective"][i]), cp, cs, reason=reason, extras=extras))
        stats["rows_s"] += time.perf_counter() - t_rows
        done += int(first.size)
        if progress is not None:
            progress(done, total)
    last_stats["fit"] = stats
    return out


def session_strict_background(session, tttr) -> StrictBackground:
    """``MleSession.select_background``'s strict selection, natively: the bursts of the current
    file as runs, judged by the session's accept test on histograms."""
    from chisurf.plugins.burst.burst_mle_analysis.engine import MAX_FLUORESCENCE_SHARE

    first, last = _burst_runs(session)
    chs = sorted({int(c) for d in session.detectors.values() for c in d.get("chs", [])})
    binning = max(1, int(session.settings.micro_time_binning))
    dt, _period = session.timing_ns(tttr, binning)
    judged = {d: np.asarray(session.irf_np[d], dtype=float) for d in session.detectors
              if np.asarray(session.irf_np.get(d, [])).size and np.any(session.irf_np[d])}
    accept = (
        accept_from_histograms(judged, session.detectors, binning, dt, session._gate_window,
                               MAX_FLUORESCENCE_SHARE)
        if judged else None
    )
    return strict_background(tttr, first, last, chs, accept_hist=accept, histogram_channels=chs)


def session_background_patterns(session, tttr, strict: StrictBackground, detectors: list) -> dict:
    """The ``bg`` patterns ``select_background`` takes from ``extract_mle_irf_background``."""
    return background_patterns(tttr, strict.histograms, {d: session.detectors[d] for d in detectors},
                               int(session.settings.micro_time_binning))


def _burst_runs(session) -> tuple[np.ndarray, np.ndarray]:
    idx = session.burst_index_array()
    breaks = np.flatnonzero(np.diff(idx) != 1)
    return np.r_[idx[0], idx[breaks + 1]], np.r_[idx[breaks], idx[-1]]


def outside_histograms(tttr, first, last, channels) -> dict:
    """Raw micro-time histogram per routing channel of the photons outside the bursts
    ``[first, last]`` -- one native pass, no photon mask."""
    import tttrlib

    cfg = json.dumps({"detectors": [{"name": "all", "chs": sorted({int(c) for c in channels}), "gates": []}],
                      "windows": [], "search": {"algorithm": "sliding_window"},
                      "decays": {"binning": 1, "n_bins": 1}, "features": False, "confidence": False})
    pipe = tttrlib.BurstPipeline(cfg)
    result = pipe.decays(tttr, np.ascontiguousarray(first, dtype=np.int64),
                         np.ascontiguousarray(last, dtype=np.int64), 1, 1)
    h = result.outside_histogram()
    last_stats["outside"] = {"calls": 3, "bytes_in": int(2 * 8 * len(first) + len(cfg))}
    return {int(c): h[k] for k, c in enumerate(result.histogram_channels())}


def gated_photons(histograms: dict, info: dict) -> int:
    """Photons a histogram set counts on a detector's channels inside its gates (half-open, raw
    channels; no gates: every channel) -- ``MleSession._background_prompt_photons`` of a mask."""
    total = 0
    gates = _gates(info.get("micro_time_ranges"))
    for c in info.get("chs", []):
        h = histograms.get(int(c))
        if h is None:
            continue
        if not gates:
            total += int(np.sum(h))
            continue
        inside = np.zeros(h.size, dtype=bool)
        for lo, hi in gates:
            inside[max(0, lo):max(0, min(hi, h.size))] = True
        total += int(np.sum(h[inside]))
    return total


def session_outside_patterns(session, tttr, detectors: dict, *, irf_model: str,
                             with_histograms: bool = False):
    """``extract_mle_irf_background(tttr, detectors, mask=~in_burst, irf_model=...)`` of the
    session's current file, from native histograms of the photons outside its bursts; with
    *with_histograms* also those histograms (``{channel: counts}``)."""
    from chisurf.core.fluorescence.burst import extract_mle_irf_background

    first, last = _burst_runs(session)
    chs = {int(c) for d in detectors.values() for c in d.get("chs", [])}
    hist = outside_histograms(tttr, first, last, chs)
    patterns = extract_mle_irf_background(tttr, detectors, micro_time_binning=session.settings.micro_time_binning,
                                          histograms=hist, irf_model=irf_model)
    return (patterns, hist) if with_histograms else patterns
