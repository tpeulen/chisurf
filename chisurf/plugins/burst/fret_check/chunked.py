"""Large files, analysed in chunks: memory stays flat whatever the file size.

A page's worker is a 32-bit WebAssembly process (4 GB at most), and a 1 GB
PTU decodes to about 3 GB of arrays. So a file above :data:`LARGE_BYTES` is
never decoded whole:

* :func:`iter_chunks` reads the records in ranges and decodes each range into
  a fresh, small TTTR, carrying the decoder's overflow state -- the times stay
  absolute, and the photons equal a full read event for event (tested against
  tttrlib's own reader). Containers that cannot be read in ranges (``.sm``)
  are read whole; they are small.
* :func:`analyse_chunked` detects the experiment on the first chunk, then
  runs the ordinary burst analysis (:func:`chisurf.plugins.burst.fret_check.pipeline.analyse`) chunk
  by chunk. A burst that might continue past a chunk's end is not taken: its
  photons, and :data:`GUARD` more, are carried into the next chunk, so no
  burst is cut and every photon is searched once. Kept per chunk: the burst
  table rows, the out-of-burst counts and time (background), the 1 ms trace
  and the micro-time histograms -- never the photons.
"""
from __future__ import annotations

import os

import numpy as np

from .detect import Experiment, detect_experiment
from .pipeline import STREAMS, BurstSettings, Bursts, analyse as analyse_bursts, photon_streams

__all__ = ["LARGE_BYTES", "CHUNK_RECORDS", "GUARD", "is_large", "iter_chunks", "analyse_chunked"]

#: Files above this many bytes are analysed in chunks (shared with the page build).
from .limits import LARGE_BYTES  # noqa: E402
#: Records decoded per chunk (~120 MB of arrays).
CHUNK_RECORDS = 10_000_000
#: Photons before a chunk's end within which a burst counts as unfinished.
GUARD = 2000
#: More unfinished photons than this are not carried: the "burst" never ends
#: (bulk data, a sample far too concentrated) and is closed at the chunk's
#: end. No single molecule gives a million photons in one transit.
MAX_CARRY = 1_000_000


def is_large(path: str) -> bool:
    try:
        return os.path.getsize(path) > LARGE_BYTES
    except OSError:
        return False


def _ranged(path):
    import tttrlib  # noqa: PLC0415

    try:
        info = tttrlib.container_records(str(path))
    except Exception:  # noqa: BLE001 - an unknown container: read it whole
        return None
    return info if info.ranged else None


def iter_chunks(path: str, records: int | None = None):
    """``(tttr, records_done, records_total)`` per range of *path*'s records."""
    import tttrlib  # noqa: PLC0415

    records = records or CHUNK_RECORDS
    info = _ranged(path)
    if info is None:
        data = tttrlib.TTTR(str(path))
        yield data, len(data), len(data)
        return
    header = tttrlib.TTTRHeader(str(path), info.container_type)
    state = tttrlib.TTTRDecodeState()
    at = 0
    while at < info.n_records:
        raw = tttrlib.container_read_records(str(path), at, records, info.container_type)
        if not len(raw):
            break
        chunk = tttrlib.TTTR()
        tttrlib.decode_records(np.frombuffer(raw, dtype=np.uint8), info.record_type, state, chunk)
        chunk.set_header(header)
        chunk.apply_container_channels(info.container_type)
        at += len(raw) // info.bytes_per_record
        if len(chunk):
            yield chunk, at, info.n_records


def _tttr(macro, micro, routing, events, like):
    import tttrlib  # noqa: PLC0415

    out = tttrlib.TTTR(np.ascontiguousarray(macro, np.uint64), np.ascontiguousarray(micro, np.uint16),
                       np.ascontiguousarray(routing, np.int8), np.ascontiguousarray(events, np.int8))
    out.header.set_macro_time_resolution(float(like.header.macro_time_resolution))
    out.header.set_micro_time_resolution(float(like.header.micro_time_resolution))
    return out


def _arrays(d):
    return (np.asarray(d.macro_times), np.asarray(d.micro_times), np.asarray(d.routing_channels),
            np.asarray(d.event_types))


def _take(b: Bursts, keep: np.ndarray) -> dict:
    """The rows *keep* of a burst table, as plain arrays."""
    return {
        "start": b.start[keep], "stop": b.stop[keep], "t_start": b.t_start[keep],
        "duration": b.duration[keep], "E": b.E[keep],
        "S": None if b.S is None else b.S[keep],
        "fret_2cde": None if b.fret_2cde is None else b.fret_2cde[keep],
        "alex_2cde": None if b.alex_2cde is None else b.alex_2cde[keep],
        "counts": {k: v[keep] for k, v in b.counts.items()},
        "extra": {k: v[keep] for k, v in b.extra.items()},
    }


def _concat(parts: list) -> dict:
    def cat(key):
        arrays = [p[key] for p in parts]
        return None if arrays[0] is None else np.concatenate(arrays)

    out = {k: cat(k) for k in ("start", "stop", "t_start", "duration", "E", "S", "fret_2cde", "alex_2cde")}
    for group in ("counts", "extra"):
        names = parts[0][group].keys()
        out[group] = {n: np.concatenate([p[group][n] for p in parts]) for n in names}
    return out


class _Acc:
    """What survives a chunk: counts in time bins and histograms."""

    def __init__(self, bin_s: float) -> None:
        self.bin_s = bin_s
        self.trace: dict = {}
        self.bg_counts = {k: 0.0 for k in STREAMS}
        self.bg_time = 0.0

    def add_trace(self, stream, t_abs) -> None:
        idx = (t_abs / self.bin_s).astype(np.int64)
        for i, k in enumerate(STREAMS):
            sel = idx[stream == i]
            if not sel.size:
                continue
            counts = np.bincount(sel, minlength=int(idx.max()) + 1).astype(np.float64)
            have = self.trace.get(k)
            if have is None:
                self.trace[k] = counts
            else:
                if have.size < counts.size:
                    have = np.pad(have, (0, counts.size - have.size))
                have[: counts.size] += counts
                self.trace[k] = have


def analyse_chunked(report, path: str, settings: BurstSettings, experiment: Experiment | None = None,
                    records: int | None = None, bin_s: float = 1e-3):
    """Detect and analyse *path* chunk by chunk.

    Returns ``(experiment_detected, experiment_used, bursts, trace, micro)``:
    the experiment as detected on the first chunk (duration and photon count
    of the whole file), the one analysed with (*experiment*, or the detected
    one), the burst table (photon indices and times absolute), the 1 ms
    ``trace`` (``{"bin_s", "rates"}``, kHz per stream) and the micro-time
    histograms per channel (``{channel: (edges, counts)}``).
    """
    from .detect import with_phase  # noqa: PLC0415

    acc = _Acc(bin_s)
    parts = []
    detected = exp = None
    carry = None             # (macro, micro, routing, events) of photons not yet searched
    first_macro = None
    done_photons = 0         # photons before the current working set, in the file
    n_total = 0
    micro_edges = None
    micro_counts: dict = {}
    total_records = None
    t_end = 0.0
    irf_offsets: dict = {}   # each decay's half-rise, from the first chunk, for all
    split_bursts = 0
    for chunk, at, total_records in iter_chunks(path, records):
        n_total += len(chunk)
        if detected is None:
            report(0.02, "detecting the experiment (first chunk)")
            detected = detect_experiment(chunk)
            exp = experiment or detected
        arrays = _arrays(chunk)
        if carry is not None:
            arrays = tuple(np.concatenate([c, a]) for c, a in zip(carry, arrays))
        work = _tttr(*arrays, like=chunk)
        if exp.alex_period:
            work = with_phase(work, exp.alex_period)
        macro = np.asarray(work.macro_times)
        if first_macro is None:
            first_macro = int(macro[0])
        res = float(chunk.header.macro_time_resolution)
        last = at >= total_records
        frac = at / max(total_records, 1)
        report(0.05 + 0.85 * frac, f"bursts in chunk {at:,} / {total_records:,} records")
        b = analyse_bursts(work, exp, settings, irf_offsets=irf_offsets)
        n = len(work)
        # Bursts that might go on past this chunk wait for the next one.
        cut = n
        if not last:
            unfinished = np.flatnonzero(b.stop >= n - GUARD)
            cut = int(b.start[unfinished].min()) if unfinished.size else n - GUARD
            cut = max(cut, 0)
            if n - cut > MAX_CARRY:
                cut = n          # a burst that does not end: closed here, nothing carried
                split_bursts += 1
        keep = b.stop < cut
        rows = _take(b, keep)
        offset_s = (int(macro[0]) - first_macro) * res
        rows["start"] = rows["start"] + done_photons
        rows["stop"] = rows["stop"] + done_photons
        rows["t_start"] = rows["t_start"] + offset_s
        parts.append(rows)
        # Background and trace over the searched part [0, cut).
        stream = photon_streams(work, exp)[:cut]
        t_abs = (macro[:cut].astype(np.int64) - first_macro) * res
        inside = np.zeros(cut + 1, np.int64)
        np.add.at(inside, b.start[keep], 1)
        np.add.at(inside, b.stop[keep] + 1, -1)
        in_burst = np.cumsum(inside)[:-1] > 0
        for i, k in enumerate(STREAMS):
            acc.bg_counts[k] += float(np.sum((stream == i) & ~in_burst))
        if cut:
            span = float(t_abs[-1] - t_abs[0]) if cut > 1 else 0.0
            acc.bg_time += max(span - float(np.sum(b.duration[keep])), 0.0)
        acc.add_trace(stream, t_abs)
        if cut:
            t_end = max(t_end, float(t_abs[-1]))
        # Micro-time histograms (the phase for µsALEX) of every channel.
        micro = np.asarray(work.micro_times)[:cut]
        routing = np.asarray(work.routing_channels)[:cut]
        if micro.size and int(micro.max()) > 0:
            if micro_edges is None:
                top = max(int(exp.n_micro_channels), int(micro.max()) + 1)
                micro_edges = np.linspace(0, top, 257)
            for c in sorted(set(exp.channels) | set(exp.unassigned_channels)):
                h, _ = np.histogram(micro[routing == c], bins=micro_edges)
                micro_counts[c] = micro_counts.get(c, 0) + h.astype(float)
        # The file's own arrays (with_phase rewrote the micro times of `work`).
        carry = tuple(a[cut:] for a in arrays) if not last else None
        done_photons += cut
        del work, b, chunk
    duration = t_end
    for e in {id(detected): detected, id(exp): exp}.values():
        e.duration_s = duration
        e.n_photons = n_total
        if split_bursts:
            e.warnings.append(
                f"{split_bursts} burst(s) never ended within a chunk and were closed at its end: "
                "the signal hardly drops to background (bulk data, or far too concentrated)")
    rows = _concat(parts)
    bursts = Bursts(
        start=rows["start"], stop=rows["stop"], t_start=rows["t_start"], duration=rows["duration"],
        counts=rows["counts"], background={k: v / max(acc.bg_time, 1e-9) for k, v in acc.bg_counts.items()},
        E=rows["E"], S=rows["S"], fret_2cde=rows["fret_2cde"], alex_2cde=rows["alex_2cde"],
        extra=rows["extra"])
    rates = {k: v / bin_s * 1e-3 for k, v in acc.trace.items()}
    micro = {c: (micro_edges, h) for c, h in micro_counts.items()} if micro_edges is not None else {}
    return detected, exp, bursts, {"bin_s": bin_s, "rates": rates}, micro


def one_second_trace(trace: dict):
    """``(t_s, total_kHz)`` in 1 s bins from a fine per-stream trace."""
    bin_s = trace["bin_s"]
    rates = list(trace["rates"].values())
    n = max(len(r) for r in rates) if rates else 0
    total = np.zeros(n)
    for r in rates:
        total[: len(r)] += r
    per = max(1, int(round(1.0 / bin_s)))
    m = n // per
    if m == 0:
        return np.array([0.5]), np.array([total.mean() if n else 0.0])
    coarse = total[: m * per].reshape(m, per).mean(axis=1)
    return (np.arange(m) + 0.5), coarse


__all__ += ["one_second_trace"]
