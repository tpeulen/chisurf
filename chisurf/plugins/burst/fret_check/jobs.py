"""The analysis as a job: it runs off the page's thread (:mod:`emtk.jobs`).

In a page the job runs in a Web Worker -- a second Pyodide with the same
packages -- so the window keeps drawing and shows progress; on a desktop it
runs in a thread. Either way it is :func:`analyse`, called with JSON
parameters, returning JSON: arrays travel packed (:func:`pack`), bit for bit.

The measurement stays in the worker (:data:`_CACHE`, keyed by the file path or
the simulated example): changing a setting and pressing *Apply* re-analyses it
without sending the file again. One measurement is kept at a time.
"""
from __future__ import annotations

import base64
import dataclasses

import numpy as np

from .detect import Experiment, Window, detect_experiment, load, with_phase
from .pipeline import STREAMS, BurstSettings, Bursts, analyse as analyse_bursts, photon_streams
from .qc import Check, QCReport, run_qc

__all__ = ["analyse", "pack", "unpack", "experiment_from_dict", "bursts_from_dict", "qc_from_dict"]

#: ``key -> {"raw", "data", "exp", "micro"}``: the measurement this process holds.
_CACHE: dict = {}


# --------------------------------------------------------------------------- #
# JSON packing
# --------------------------------------------------------------------------- #
def pack(a) -> dict:
    a = np.ascontiguousarray(a)
    return {"dtype": str(a.dtype), "shape": list(a.shape), "b64": base64.b64encode(a.tobytes()).decode()}


def unpack(d):
    if d is None:
        return None
    return np.frombuffer(base64.b64decode(d["b64"]), dtype=d["dtype"]).reshape(d["shape"]).copy()


def experiment_to_dict(e: Experiment) -> dict:
    d = dataclasses.asdict(e)
    d["channel_counts"] = {str(k): v for k, v in e.channel_counts.items()}
    return d


def experiment_from_dict(d: dict) -> Experiment:
    d = dict(d)
    d.pop("kind", None)
    d["windows"] = [Window(**w) for w in d.get("windows", [])]
    d["channel_counts"] = {int(k): int(v) for k, v in (d.get("channel_counts") or {}).items()}
    names = {f.name for f in dataclasses.fields(Experiment)}
    return Experiment(**{k: v for k, v in d.items() if k in names})


def bursts_to_dict(b: Bursts) -> dict:
    return {
        "start": pack(b.start), "stop": pack(b.stop), "t_start": pack(b.t_start),
        "duration": pack(b.duration), "counts": {k: pack(v) for k, v in b.counts.items()},
        "background": dict(b.background), "E": pack(b.E),
        "S": None if b.S is None else pack(b.S),
        "fret_2cde": None if b.fret_2cde is None else pack(b.fret_2cde),
        "alex_2cde": None if b.alex_2cde is None else pack(b.alex_2cde),
        "extra": {k: pack(v) for k, v in b.extra.items()},
    }


def bursts_from_dict(d: dict) -> Bursts:
    return Bursts(
        start=unpack(d["start"]), stop=unpack(d["stop"]), t_start=unpack(d["t_start"]),
        duration=unpack(d["duration"]), counts={k: unpack(v) for k, v in d["counts"].items()},
        background=dict(d["background"]), E=unpack(d["E"]), S=unpack(d["S"]),
        fret_2cde=unpack(d["fret_2cde"]), alex_2cde=unpack(d["alex_2cde"]),
        extra={k: unpack(v) for k, v in d["extra"].items()},
    )


def qc_to_dict(q: QCReport) -> dict:
    return {
        "checks": [dataclasses.asdict(c) for c in q.checks], "flags": pack(q.flags),
        "burst_rate": q.burst_rate, "occupancy": q.occupancy, "p_multi": q.p_multi,
        "p_multi_gaps": q.p_multi_gaps, "arrival_rate": q.arrival_rate, "gaps": pack(q.gaps),
        "trace_t": pack(q.trace_t), "trace_rate": pack(q.trace_rate),
        "metrics": _jsonable(q.metrics),
    }


def qc_from_dict(d: dict) -> QCReport:
    return QCReport(
        checks=[Check(**c) for c in d["checks"]], flags=unpack(d["flags"]),
        burst_rate=d["burst_rate"], occupancy=d["occupancy"], p_multi=d["p_multi"],
        p_multi_gaps=d["p_multi_gaps"], arrival_rate=d["arrival_rate"], gaps=unpack(d["gaps"]),
        trace_t=unpack(d["trace_t"]), trace_rate=unpack(d["trace_rate"]), metrics=d["metrics"],
    )


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if np.isfinite(v) else None
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


# --------------------------------------------------------------------------- #
# the pieces
# --------------------------------------------------------------------------- #
def micro_histograms(data, exp: Experiment, n_bins: int = 256) -> dict:
    """Per channel ``{"edges", "counts"}`` of the micro time (or µsALEX phase)."""
    routing = np.asarray(data.routing_channels)
    micro = np.asarray(data.micro_times)
    if micro.size == 0 or int(micro.max()) < 1:
        return {}
    top = max(int(exp.n_micro_channels), int(micro.max()) + 1)
    step = max(1, micro.size // 2_000_000)
    edges = np.linspace(0, top, n_bins + 1)
    out = {}
    for c in sorted(set(exp.channels) | set(exp.unassigned_channels)):
        counts, _ = np.histogram(micro[::step][routing[::step] == c], bins=edges)
        out[str(c)] = {"edges": pack(edges), "counts": pack(counts.astype(float))}
    return out


def trace(data, exp: Experiment, bursts: Bursts, bin_s: float = 1e-3) -> dict:
    """Count rate of each stream in *bin_s* bins (float32), and the burst spans."""
    stream = photon_streams(data, exp)
    t = np.asarray(data.macro_times).astype(np.float64) * exp.macro_time_resolution_s
    t -= t[0] if t.size else 0.0
    n = max(1, int(np.ceil((t[-1] if t.size else 0.0) / bin_s)))
    idx = np.minimum((t / bin_s).astype(np.int64), n - 1)
    rates = {k: pack((np.bincount(idx[stream == i], minlength=n) / bin_s * 1e-3).astype(np.float32))
             for i, k in enumerate(STREAMS) if (stream == i).any()}
    spans = (np.stack([bursts.t_start, bursts.t_start + bursts.duration], axis=1)
             if bursts.n else np.zeros((0, 2)))
    return {"bin_s": bin_s, "rates": rates, "bursts": pack(spans)}


def corrections(b: Bursts, factors: dict, auto: bool):
    """Accurate E/S (tttrlib) and the factors used; auto-calibrated on request.

    ALEX/PIE: every factor from the measurement (``tttrlib.auto_calibrate``).
    cw: only the leakage is in the data -- from the donor-only (low-E) bursts;
    delta needs acceptor excitation, gamma and beta a reference.
    """
    import tttrlib  # noqa: PLC0415

    if b.n == 0:
        return None, factors
    factors = dict(factors)
    factors.update(bg_dd=0.0, bg_da=0.0, bg_aa=0.0)
    cols = {"i_dd": b.counts["DD"], "i_da": b.counts["DA"]}
    if "AA" in b.counts:
        cols["i_aa"] = b.counts["AA"]
    if auto and "i_aa" in cols:
        cal = tttrlib.auto_calibrate(cols)
        got = cal.get("factors", cal) if isinstance(cal, dict) else {}
        for k in ("gamma", "alpha", "delta", "beta"):
            if k in got and np.isfinite(got[k]):
                factors[k] = float(got[k])
    elif auto:
        do = b.E < 0.15
        if do.sum() >= 20:
            mean_dur = float(b.duration[do].mean())
            alpha = float(tttrlib.leakage_from_donor_only(
                cols["i_dd"][do], cols["i_da"][do],
                bg_dd=b.background["DD"] * mean_dur, bg_da=b.background["DA"] * mean_dur))
            if np.isfinite(alpha):
                factors["alpha"] = alpha
    res = tttrlib.accurate_fret(cols["i_dd"], cols["i_da"], cols.get("i_aa"), factors=factors)
    corrected = {"E": pack(np.asarray(res["E"], float)),
                 "S": None if res.get("S") is None else pack(np.asarray(res["S"], float))}
    return corrected, {k: factors[k] for k in ("gamma", "alpha", "delta", "beta")}


def _measurement(report, key, path, scenario, redetect):
    entry = _CACHE.get(key)
    if entry is not None and not redetect:
        return entry
    _CACHE.clear()  # one measurement at a time: the memory is the limit
    from .chunked import is_large  # noqa: PLC0415

    if path and not scenario and is_large(path):
        # Too large to hold decoded: analysed chunk by chunk on every run;
        # only the file name is cached.
        entry = {"large": True}
        _CACHE[key] = entry
        return entry
    if scenario:
        from .sim import SCENARIOS, simulate  # noqa: PLC0415

        report(0.02, "simulating the measurement")
        sc = next((s for s in SCENARIOS if s.name == scenario), SCENARIOS[0])
        raw = simulate(sc)
    else:
        report(0.02, "reading the file")
        raw = load(path)
    report(0.15, "detecting the experiment")
    exp = detect_experiment(raw)
    data = with_phase(raw, exp.alex_period) if exp.alex_period else raw
    entry = {"raw": raw, "data": data, "exp": exp, "micro": micro_histograms(data, exp)}
    _CACHE[key] = entry
    return entry


# --------------------------------------------------------------------------- #
# the job
# --------------------------------------------------------------------------- #
def analyse(report, key: str, path: str = "", scenario: str = "", redetect: bool = False,
            experiment: dict | None = None, settings: dict | None = None, v_eff_fl: float = 1.0,
            correct: bool = False, factors: dict | None = None, auto_calibrate: bool = False) -> dict:
    """Load (once), detect, find the bursts, check, correct: one measurement.

    Parameters
    ----------
    report : callable
        ``report(fraction, message)``, the progress (:mod:`emtk.jobs`).
    key : str
        What identifies the measurement in :data:`_CACHE` (the path, or the
        simulated example's name).
    path, scenario : str
        The file to read, or the :mod:`.sim` example to simulate.
    redetect : bool
        Read and detect again even when the measurement is cached.
    experiment : dict, optional
        The (edited) experiment to analyse with; the detected one otherwise.
    settings : dict, optional
        :class:`~.pipeline.BurstSettings` fields.
    correct, factors, auto_calibrate
        Accurate E/S with these factors (advanced mode), auto-calibrated on
        request.

    Returns
    -------
    dict
        ``detected`` (the experiment as detected), ``experiment`` (as
        analysed), ``bursts``, ``qc``, ``corrected``, ``factors``, ``trace``,
        ``micro`` -- JSON, arrays packed.
    """
    entry = _measurement(report, key, path, scenario, redetect)
    burst_settings = BurstSettings(**(settings or {}))
    import os  # noqa: PLC0415

    # How the file reached this process: a link to the user's File, mounted
    # read-only (a page's worker), or a copy / the file itself.
    mounted = bool(path) and os.path.islink(path)
    if entry.get("large"):
        out = _analyse_large(report, path, burst_settings, experiment, v_eff_fl, correct, factors,
                             auto_calibrate)
        out["file_mounted"] = mounted
        return out
    exp = experiment_from_dict(experiment) if experiment else entry["exp"]
    data = entry["data"]
    bursts = analyse_bursts(data, exp, burst_settings,
                            progress=lambda f, m: report(0.2 + 0.55 * f, m))
    report(0.78, "quality checks")
    qc = run_qc(data, exp, bursts, v_eff_fl=float(v_eff_fl))
    corrected, used = None, dict(factors or {})
    if correct:
        report(0.86, "FRET corrections")
        corrected, used = corrections(bursts, factors or {}, auto_calibrate)
    report(0.93, "time trace")
    tr = trace(data, exp, bursts)
    report(1.0, "done")
    return {
        "detected": experiment_to_dict(entry["exp"]), "experiment": experiment_to_dict(exp),
        "bursts": bursts_to_dict(bursts), "qc": qc_to_dict(qc), "corrected": corrected,
        "factors": used, "trace": tr, "micro": entry["micro"], "file_mounted": mounted,
    }


def _analyse_large(report, path, burst_settings, experiment, v_eff_fl, correct, factors,
                   auto_calibrate) -> dict:
    """:func:`analyse` for a file too large to decode whole (:mod:`.chunked`)."""
    from .chunked import analyse_chunked, one_second_trace  # noqa: PLC0415

    exp_in = experiment_from_dict(experiment) if experiment else None
    detected, exp, bursts, fine, micro = analyse_chunked(report, path, burst_settings, exp_in)
    report(0.92, "quality checks")
    qc = run_qc(None, exp, bursts, v_eff_fl=float(v_eff_fl), trace=one_second_trace(fine))
    corrected, used = None, dict(factors or {})
    if correct:
        report(0.95, "FRET corrections")
        corrected, used = corrections(bursts, factors or {}, auto_calibrate)
    spans = (np.stack([bursts.t_start, bursts.t_start + bursts.duration], axis=1)
             if bursts.n else np.zeros((0, 2)))
    tr = {"bin_s": fine["bin_s"], "bursts": pack(spans),
          "rates": {k: pack(np.asarray(v, np.float32)) for k, v in fine["rates"].items()}}
    report(1.0, "done")
    return {
        "detected": experiment_to_dict(detected), "experiment": experiment_to_dict(exp),
        "bursts": bursts_to_dict(bursts), "qc": qc_to_dict(qc), "corrected": corrected,
        "factors": used, "trace": tr,
        "micro": {str(c): {"edges": pack(e), "counts": pack(h)} for c, (e, h) in micro.items()},
        "chunked": True,
    }
