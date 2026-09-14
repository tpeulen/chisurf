"""Qt-free core logic for the ALEX Creator plugin.

Every ALEX conversion (single-file, batch-convert and merge) plus the micro-time
histogram is implemented here as pure :mod:`tttrlib` functions, with no Qt, RPC
or CLI dependency. The GUI (:mod:`..gui`), CLI (:mod:`..cli`) and RPC backend
(:mod:`..backend`) are thin adapters over this module.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import tttrlib

#: container name → (file-extension stem, record-type id, container id).
CONTAINER_INFO: dict[str, tuple[str, int, int]] = {
    "PTU": ("ptu", 4, 0),
    "HT3": ("ht3", 4, 1),
    "SPC-130": ("spc", 7, 2),
    "SPC-600_256": ("spc", 8, 3),
    "SPC-600_4096": ("spc", 9, 4),
    "PHOTON-HDF5": ("hdf", 4, 5),
    "CZ-RAW": ("raw", 10, 6),
    "SM": ("sm", 11, 7),
}

#: tttrlib tag value-type for the record-type tags (0x10000008 == Int8).
_TAG_INT8 = 268435464


def supported_containers() -> list[str]:
    """Return every tttrlib container name."""
    return list(tttrlib.TTTR.get_supported_container_names())


def input_format_options() -> list[str]:
    """Input container choices: ``Auto`` plus every tttrlib container name."""
    return ["Auto", *supported_containers()]


def resolve_filetype(input_format: str, path: str | None = None) -> str | None:
    """Resolve the tttrlib container name to read *path* with.

    ``input_format`` of ``"Auto"`` returns the inferred container name (or
    ``None`` to let tttrlib auto-detect); any other value is returned verbatim.
    """
    if input_format and input_format != "Auto":
        return input_format
    if path and os.path.exists(path):
        idx = tttrlib.inferTTTRFileType(path)
        names = supported_containers()
        if idx is not None and 0 <= idx < len(names):
            return names[idx]
    return None


def container_ext(output_format: str) -> str:
    """File-extension stem for *output_format* (defaults to ``ptu``)."""
    return CONTAINER_INFO.get(output_format, ("ptu", 0, 0))[0]


def default_output_name(in_path: str, output_format: str, suffix: str = "_alex") -> str:
    """Suggested output filename for *in_path* in *output_format*."""
    base = pathlib.Path(in_path).stem if in_path else "alex"
    return f"{base}{suffix}.{container_ext(output_format)}"


def load(path: str, filetype: str | None = None) -> tttrlib.TTTR:
    """Load a TTTR file (``filetype`` = ``None`` lets tttrlib auto-detect)."""
    return tttrlib.TTTR(path, filetype) if filetype else tttrlib.TTTR(path)


def apply_alex(tttr: tttrlib.TTTR, alex_period: int, period_shift: int) -> tttrlib.TTTR:
    """Map ALEX macro-time alternation into micro-time, in place, and return it."""
    tttr.alex_to_microtime(int(alex_period), int(period_shift))
    return tttr


def alex_histogram(
    path: str, alex_period: int, period_shift: int, filetype: str | None = None
) -> np.ndarray:
    """Return the micro-time histogram after ALEX conversion of *path*."""
    tttr = apply_alex(load(path, filetype), alex_period, period_shift)
    period = int(alex_period)
    return np.bincount(tttr.micro_times, minlength=period)[:period]


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return ``(start, stop_inclusive)`` runs of ``True`` on a circular array.

    The array is treated as periodic, so a run may wrap past the last index back
    to index 0 (returned as ``start > stop``).
    """
    mask = np.asarray(mask, dtype=bool)
    n = len(mask)
    if n == 0 or not mask.any():
        return []
    if mask.all():
        return [(0, n - 1)]
    # Rotate so index 0 is a False bin; this turns wrap-around runs into normal
    # ones, then map indices back.
    offset = int(np.argmin(mask))
    rolled = np.roll(mask, -offset)
    runs = []
    i = 0
    while i < n:
        if rolled[i]:
            j = i
            while j < n and rolled[j]:
                j += 1
            runs.append(((i + offset) % n, (j - 1 + offset) % n))
            i = j
        else:
            i += 1
    return runs


def _run_length(run: tuple[int, int], n: int) -> int:
    """Length of a (possibly wrapping) run of bins."""
    start, stop = run
    return (stop - start + 1) if start <= stop else (n - start + stop + 1)


def auto_alex_windows(
    micro_times,
    routing_channels,
    *,
    donor_channels,
    acceptor_channels,
    alex_period: int,
    n_bins: int = 200,
    guard: float = 0.06,
    occupancy: float = 0.35,
) -> dict:
    """Detect the green/red ALEX excitation windows from the folded phase.

    Micro-second ALEX encodes the laser alternation in the macro-time; after
    :func:`apply_alex` the micro-time is the phase within ``alex_period``. The
    two laser-on periods show up as two occupied plateaus in the phase histogram,
    separated by the rise/fall gaps where no laser is fully on. This locates the
    two largest plateaus, trims a ``guard`` fraction off each edge to discard the
    laser rise/fall transition photons (some photon loss is expected and
    intended), and labels the donor-brighter window ``"green"`` (donor
    excitation) and the other ``"red"`` (acceptor excitation).

    Parameters
    ----------
    micro_times : array_like
        Folded ALEX phase per photon (``tttr.micro_times`` after
        :func:`apply_alex`).
    routing_channels : array_like
        Detector routing channel per photon.
    donor_channels, acceptor_channels : sequence of int
        Routing channels of the donor ("green") and acceptor ("red") detectors.
    alex_period : int
        Alternation period in macro-time units (the folding period).
    n_bins : int
        Number of phase bins used to build the occupancy histogram.
    guard : float
        Fraction of each detected window width trimmed from *both* edges to skip
        the laser rise/fall. ``0`` keeps the raw plateau edges.
    occupancy : float
        A bin counts as "laser on" when it holds more than ``occupancy`` times
        the 75th-percentile of the non-empty bins.

    Returns
    -------
    dict
        ``{"green": (lo, hi), "red": (lo, hi), "phase_hist": counts,
        "phase_edges": edges}`` with window bounds in macro-time units.

    Raises
    ------
    ValueError
        If two laser plateaus cannot be found (e.g. continuous-wave data with a
        single, fully-occupied period).
    """
    phase = np.asarray(micro_times)
    rc = np.asarray(routing_channels)
    period = int(alex_period)
    edges = np.linspace(0, period, n_bins + 1)
    counts, _ = np.histogram(phase, bins=edges)
    donor_counts, _ = np.histogram(
        phase[np.isin(rc, list(donor_channels))], bins=edges)
    acceptor_counts, _ = np.histogram(
        phase[np.isin(rc, list(acceptor_channels))], bins=edges)

    nonzero = counts[counts > 0]
    if nonzero.size == 0:
        raise ValueError("no photons to detect ALEX windows from")

    # Dark bins first: on synthetic or heavily gated data the laser-off phase
    # holds no photons at all, and such a bin belongs to neither window. On real
    # data there are none -- which is the whole reason the split below is made
    # on the detector ratio and not on occupancy.
    lit = counts > occupancy * np.percentile(nonzero, 75)
    if lit.sum() < 4:
        raise ValueError(
            "too few occupied phase bins to detect ALEX windows from; "
            "the period or the binning is wrong"
        )

    # The split is a *ratio*, not a plateau. Real µs-ALEX has no laser-off gap
    # to find: both lasers keep the sample emitting, so the total phase
    # histogram is nearly flat and an occupancy threshold sees one window
    # covering the whole period. What does alternate, sharply, is which detector
    # the photons land on -- so the acceptor's share of each phase bin is a
    # square wave even when the intensity is not.
    with np.errstate(divide="ignore", invalid="ignore"):
        share = acceptor_counts / np.maximum(donor_counts + acceptor_counts, 1)
    lit_share = share[lit]
    low, high = np.percentile(lit_share, 10), np.percentile(lit_share, 90)
    # An alternation has to stand out of the counting noise, not out of a
    # fixed number. A bin's share is binomial, so with n photons per bin its
    # 10-90 spread is about 2.6 standard deviations of sqrt(p(1-p)/n) with no
    # alternation at all -- 0.13 at 100 photons, which a fixed 0.05 read as
    # alternating, so continuous-wave data passed as ALEX. Six standard
    # deviations keeps the genuine square wave (spread 0.3 and up) and refuses
    # noise; the 0.05 floor still refuses a flat share measured very precisely.
    mean_share = float(np.clip(np.mean(lit_share), 0.0, 1.0))
    photons_per_bin = float(np.median((donor_counts + acceptor_counts)[lit]))
    noise = np.sqrt(mean_share * (1.0 - mean_share) / max(photons_per_bin, 1.0))
    if high - low < max(0.05, 6.0 * noise):
        raise ValueError(
            "the acceptor's share of the phase bins does not alternate "
            f"(spread {high - low:.3f}); the data may be continuous-wave, the "
            "period wrong, or both detectors assigned to the same colour"
        )
    # Hysteresis, not a midpoint. Between the two laser windows is a phase where
    # neither laser is fully on and the ratio sits *between* the two levels; a
    # midpoint threshold assigns that band to whichever side it happens to fall,
    # which merges it into one window and can wrap that window past phase zero.
    # Requiring a bin to be clearly on one side leaves the transition in neither,
    # which is what it is.
    span = high - low
    donor_lit = lit & (share <= low + 0.25 * span)
    acceptor_lit = lit & (share >= high - 0.25 * span)

    runs = []
    for name, mask in (("donor", donor_lit), ("acceptor", acceptor_lit)):
        candidates = _contiguous_runs(mask)
        if not candidates:
            raise ValueError(
                f"the {name}-excitation window is empty; check the "
                "donor/acceptor channel assignment"
            )
        runs.append(max(candidates, key=lambda r: _run_length(r, n_bins)))

    windows = []
    for start, stop in runs:
        if start > stop:
            # A window that straddles phase zero cannot be written as one
            # micro-time range, and every consumer downstream takes [lo, hi].
            # The remedy is a period shift, which is what `apply_alex` takes.
            raise ValueError(
                f"an excitation window wraps past phase 0 "
                f"(bins {start}..{stop} of {n_bins}); fold with a period shift "
                f"of about {int(edges[start])} so both windows are contiguous"
            )
        lo = float(edges[start])
        hi = float(edges[stop + 1]) if stop + 1 < len(edges) else float(period)
        margin = guard * (hi - lo)
        windows.append((lo + margin, hi - margin))

    def donor_density(win: tuple[float, float]) -> float:
        lo, hi = win
        sel = (phase >= lo) & (phase < hi) & np.isin(rc, list(donor_channels))
        return sel.sum() / max(hi - lo, 1.0)

    windows.sort(key=donor_density, reverse=True)
    return {
        "green": windows[0],
        "red": windows[1],
        "phase_hist": counts,
        "phase_edges": edges,
    }


#: Phase bins used to score a trial period. Enough to resolve the alternation's
#: square wave, few enough that the histogram is cheap.
_PHASE_BINS = 32


def detect_alex_period(
    macro_times,
    routing_channels,
    *,
    donor_channels,
    acceptor_channels,
    min_period: int = 64,
    max_period: int | None = None,
    n_photons: int = 2_000_000,
    max_bins: int = 1 << 22,
    scan_photons: int = 150_000,
) -> dict:
    """Find the µs-ALEX alternation period from the photon stream itself.

    The period is a hardware setting nobody wants to type in, and typing it
    wrong is silent: the folded phase is then a smear with no plateaus, the
    windows land on nothing, and the analysis proceeds with a stoichiometry
    histogram that has one peak instead of three.

    What makes it findable is that the *donor and acceptor detectors alternate*.
    Assign +1 to every donor photon and −1 to every acceptor photon, bin that
    signed stream in macro time, and the alternation is a single sharp line in
    its power spectrum — much sharper than in either detector's own intensity,
    which is modulated by the sample as well as by the lasers. The peak
    frequency gives the period; a short integer scan around it fixes the exact
    macro-time count, which is what :func:`apply_alex` needs.

    Parameters
    ----------
    macro_times, routing_channels : array_like
        The photon stream (``tttr.macro_times``, ``tttr.routing_channels``).
    donor_channels, acceptor_channels : sequence of int
        Routing channels of the two detection colours.
    min_period : int
        Smallest period to consider, in macro-time units. Also sets the
        binning: the signal is binned at ``min_period / 16``.
    max_period : int, optional
        Largest period to consider. Defaults to a fiftieth of the analysed
        span, so at least 50 alternation cycles are seen.
    n_photons : int
        Photons from the start of the file used for the estimate.
    max_bins : int
        Cap on the FFT length; the bin width is widened if the span needs more.
        Do not lower it without reading the note in the body: it sets how many
        times per period the alternation is sampled.
    scan_photons : int
        Photons used by the *survey* half of the integer scan, thinned by stride
        from the full span. The period's resolution comes from the length of the
        record rather than the number of photons in it, so this only has to be
        enough to rank candidates; the winner is then re-scored on every photon.

    Returns
    -------
    dict
        ``{"period": int, "confidence": float, "power": ndarray,
        "periods": ndarray}`` — ``confidence`` is the peak power divided by the
        median power of the searched band, so ``< 5`` means "no clear
        alternation, this is probably not µs-ALEX".

    Raises
    ------
    ValueError
        If there are too few photons in the two detector groups to look at.
    """
    macro = np.asarray(macro_times)
    rc = np.asarray(routing_channels)
    is_donor = np.isin(rc, list(donor_channels))
    is_acceptor = np.isin(rc, list(acceptor_channels))
    keep = is_donor | is_acceptor
    if keep.sum() < 1000:
        raise ValueError(
            "fewer than 1000 photons in the donor/acceptor channels — check the "
            "channel assignment before detecting the ALEX period"
        )
    idx = np.flatnonzero(keep)[:int(n_photons)]
    t = macro[idx].astype(np.int64)
    t = t - t[0]
    sign = np.where(is_donor[idx], 1.0, -1.0)

    span = int(t[-1]) + 1
    if max_period is None:
        max_period = max(int(span // 50), min_period * 2)

    # NOTE: `bin_width` is set by `max_bins`, so the alternation ends up sampled
    # only ~2.6 times per period on a long file -- just above Nyquist. It works
    # here and it is what makes the spectral line detectable at all (the line's
    # power grows with the number of cycles seen, so the long span is doing the
    # work), but it is close to an edge: see the known-issues entry before
    # changing either constant. Shortening the span to bin more finely was tried
    # and reverted -- 524 cycles is not enough for the line to beat low-frequency
    # drift, and the detector returned 78400 for a period of 8000.
    bin_width = max(1, int(min_period // 16), -(-span // max_bins))
    n_bins = int(span // bin_width) + 1
    signal = np.bincount(t // bin_width, weights=sign, minlength=n_bins)
    signal -= signal.mean()

    spectrum = np.fft.rfft(signal)
    power = np.abs(spectrum) ** 2
    # k = 0 is the (already removed) mean; period = total length / k.
    k = np.arange(power.size)
    with np.errstate(divide="ignore"):
        periods = np.where(k > 0, n_bins * bin_width / np.maximum(k, 1), np.inf)
    band = (periods >= min_period) & (periods <= max_period)
    if not band.any():
        raise ValueError(
            f"no candidate period between {min_period} and {max_period} "
            f"macro-time units in a {span}-unit span"
        )
    band_power = np.where(band, power, 0.0)
    peak = int(np.argmax(band_power))
    coarse = float(periods[peak])
    median = float(np.median(power[band])) or 1.0

    # The FFT bin is `bin_width` wide in period; `apply_alex` folds on an
    # integer, and being one unit out over 10^5 cycles walks the phase right
    # across a laser window. So finish on the photons: scan the integers around
    # the coarse estimate and keep the one whose folded phase is most modulated.
    #
    # In two passes, because one pass over every photon per candidate was the
    # whole cost of detection -- 322 candidates x a modulo over 2 M photons =
    # 4.3 s of a 4.6 s detection. The period's *resolution* comes from the
    # length of the record, not from how many photons are in it, so the survey
    # pass reads a thinned stream that still spans the whole measurement and the
    # refinement pass reads all of it over the handful of candidates that
    # survive. Same scoring function, same answer, ~20x less arithmetic.
    lo = max(min_period, int(coarse * 0.98))
    hi = min(max_period, int(coarse * 1.02) + 1)

    def _modulation(times, weights, candidate: int) -> float:
        """Total power of the folded phase histogram at one trial period."""
        phase = (times % candidate) * _PHASE_BINS // candidate
        counts = np.bincount(phase, weights=weights, minlength=_PHASE_BINS)
        return float(np.sum(counts[:_PHASE_BINS] ** 2))

    # Thinned by stride, which keeps the full span (and so the full period
    # resolution) while cutting the arithmetic. Photon arrival is Poisson, so a
    # stride in *index* is not periodic in *time* and cannot alias with the
    # alternation the scan is looking for.
    stride = max(1, t.size // int(scan_photons))
    survey_t, survey_sign = t[::stride], sign[::stride]

    step = max(1, (hi - lo) // 400)
    best, best_score = int(round(coarse)), -np.inf
    for candidate in range(lo, hi + 1, step):
        score = _modulation(survey_t, survey_sign, candidate)
        if score > best_score:
            best, best_score = candidate, score

    # Refine on every photon, over the survey's own step either side -- the
    # coarse winner is only known to within `step`, and the thinning makes the
    # scores noisier, so the true integer can sit a unit or two away.
    fine_lo = max(min_period, best - step - 2)
    fine_hi = min(max_period, best + step + 2)
    best_score = -np.inf
    for candidate in range(fine_lo, fine_hi + 1):
        score = _modulation(t, sign, candidate)
        if score > best_score:
            best, best_score = candidate, score

    return {
        "period": int(best),
        "confidence": float(band_power[peak] / median),
        "power": power[band],
        "periods": periods[band],
    }


def detect_alex_channels(
    micro_times,
    routing_channels,
    *,
    alex_period: int,
    channels=None,
    n_bins: int = 200,
) -> dict:
    """Work out which detector is the donor and which the acceptor.

    This is the old "channel flip" checkbox, decided from the data. One physical
    fact settles it: **under acceptor excitation the donor detector sees
    essentially nothing**, because the donor is not excited and does not accept
    energy. Nothing else about the sample matters — not the FRET efficiency, not
    the labelling fractions, not the laser powers.

    So: fold the phase, split the period into its two halves by the detector
    ratio (label-free, so this does not presuppose the answer), and count each
    detector in each half. The half in which one detector is nearly dark is the
    **acceptor-excitation** window, and the detector that is dark there is the
    **donor**.

    Getting this wrong is the error nothing downstream reports: a swapped
    assignment produces a complete, plausible analysis with *E* reflected about
    ½ and no fit statistic that says so.

    Parameters
    ----------
    micro_times, routing_channels : array_like
        The folded stream (after :func:`apply_alex`).
    alex_period : int
        The alternation period the stream was folded on.
    channels : sequence of int, optional
        The two routing channels to consider. Defaults to the two most populated
        channels in the stream.
    n_bins : int
        Phase bins used for the split.

    Returns
    -------
    dict
        ``{"donor": [ch], "acceptor": [ch], "contrast": float}``. ``contrast``
        is how dark the donor is under acceptor excitation, as a ratio of its
        own donor-excitation rate — below ~0.3 the call is clear, near 1 it is
        not a two-colour ALEX measurement.

    Raises
    ------
    ValueError
        If fewer than two channels carry photons, or the phase does not split.
    """
    phase = np.asarray(micro_times)
    rc = np.asarray(routing_channels)
    if channels is None:
        present, counts_per_channel = np.unique(rc, return_counts=True)
        if present.size < 2:
            raise ValueError(
                f"only channel {present.tolist()} carries photons; ALEX needs two"
            )
        order = np.argsort(counts_per_channel)[::-1][:2]
        channels = sorted(int(present[i]) for i in order)
    a, b = (int(c) for c in channels)

    period = int(alex_period)
    edges = np.linspace(0, period, n_bins + 1)
    hist_a, _ = np.histogram(phase[rc == a], bins=edges)
    hist_b, _ = np.histogram(phase[rc == b], bins=edges)
    total = hist_a + hist_b
    lit = total > 0.35 * np.percentile(total[total > 0], 75) if (total > 0).any() else total > 0
    if lit.sum() < 4:
        raise ValueError("too few occupied phase bins to assign the channels")

    with np.errstate(divide="ignore", invalid="ignore"):
        share = hist_a / np.maximum(total, 1)
    low, high = np.percentile(share[lit], 10), np.percentile(share[lit], 90)
    if high - low < 0.05:
        raise ValueError(
            f"the detector ratio does not alternate across the period "
            f"(spread {high - low:.3f}); this is not two-colour ALEX data, or "
            "the period is wrong"
        )
    first = lit & (share > 0.5 * (low + high))
    second = lit & ~first

    # Rates, not counts: the two windows need not be the same width.
    def rate(hist, mask):
        return float(hist[mask].sum()) / max(int(mask.sum()), 1)

    rates = {
        (a, "first"): rate(hist_a, first), (b, "first"): rate(hist_b, first),
        (a, "second"): rate(hist_a, second), (b, "second"): rate(hist_b, second),
    }
    # For each candidate donor, how dark it is in the window where it is darkest,
    # relative to the other window. The real donor is the one that goes dark.
    best, best_contrast = None, np.inf
    for donor, acceptor in ((a, b), (b, a)):
        bright = max(rates[(donor, "first")], rates[(donor, "second")])
        dark = min(rates[(donor, "first")], rates[(donor, "second")])
        contrast = dark / bright if bright > 0 else np.inf
        if contrast < best_contrast:
            best, best_contrast = (donor, acceptor), contrast
    donor, acceptor = best
    return {
        "donor": [donor],
        "acceptor": [acceptor],
        "contrast": float(best_contrast),
    }


def alex_stream_masks(
    micro_times,
    routing_channels,
    windows: dict,
    *,
    donor_channels,
    acceptor_channels,
) -> dict:
    """Boolean per-photon masks for the four ALEX streams.

    ``windows`` is the mapping returned by :func:`auto_alex_windows` (only the
    ``"green"``/``"red"`` bounds are used). Returns ``{"DD", "DA", "AA", "AD"}``
    masks for donor-emission/donor-excitation, acceptor-emission/donor-excitation
    (FRET), acceptor-emission/acceptor-excitation and acceptor-excitation/
    donor-emission respectively. Photons in the guard bands fall in no mask.
    """
    phase = np.asarray(micro_times)
    rc = np.asarray(routing_channels)
    g_lo, g_hi = windows["green"]
    r_lo, r_hi = windows["red"]
    green = (phase >= g_lo) & (phase < g_hi)
    red = (phase >= r_lo) & (phase < r_hi)
    is_donor = np.isin(rc, list(donor_channels))
    is_acceptor = np.isin(rc, list(acceptor_channels))
    return {
        "DD": green & is_donor,
        "DA": green & is_acceptor,
        "AA": red & is_acceptor,
        "AD": red & is_donor,
    }


def _prepare_output_header(tttr: tttrlib.TTTR, output_format: str, input_format: str):
    """Return the header to write *tttr* with, transcoded when the container changes.

    Returns ``None`` when no container change is requested (write with the file's
    own header).
    """
    if output_format == input_format or output_format == "Auto":
        return None
    ext, rec, cont = CONTAINER_INFO.get(output_format, ("ptu", 4, 0))
    header = tttr.header
    header.tttr_container_type = cont
    header.tttr_record_type = rec
    if output_format == "PTU":
        # PTU via HydraHarp wants the special tag group 0x00010304.
        header.set_tag("TTResultFormat_TTTRRecType", 0x00010304, _TAG_INT8)
        header.set_tag("TTResultFormat_BitsPerRecord", 32, _TAG_INT8)
        header.set_tag("MeasDesc_RecordType", rec, _TAG_INT8)
    else:
        header.set_tag("TTResultFormat_TTTRRecType", rec, _TAG_INT8)
        header.set_tag("MeasDesc_RecordType", rec, _TAG_INT8)
    return header


def _ensure_parent(out_path: str) -> None:
    """Create the output file's parent directory (tttrlib segfaults otherwise)."""
    parent = pathlib.Path(out_path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)


def _write(tttr: tttrlib.TTTR, out_path: str, output_format: str, input_format: str) -> None:
    _ensure_parent(out_path)
    header = _prepare_output_header(tttr, output_format, input_format)
    if header is not None:
        tttr.write(out_path, header)
    else:
        tttr.write(out_path)


def convert_file(
    in_path: str,
    out_path: str,
    alex_period: int,
    period_shift: int,
    output_format: str = "PTU",
    input_format: str = "Auto",
) -> str:
    """Convert a single ALEX file: read → ALEX→µtime → write *out_path*.

    Returns the written path.
    """
    filetype = resolve_filetype(input_format, in_path)
    tttr = apply_alex(load(in_path, filetype), alex_period, period_shift)
    _write(tttr, out_path, output_format, input_format)
    return out_path


def merge_files(
    in_paths: list[str],
    out_path: str,
    alex_period: int,
    period_shift: int,
    output_format: str = "PTU",
    input_format: str = "Auto",
) -> str:
    """Merge several ALEX files into one, then ALEX→µtime → write *out_path*.

    Events are concatenated with a running macro-time offset so the merged stream
    is monotonic. Returns the written path.
    """
    if not in_paths:
        raise ValueError("No input files to merge.")
    merged = tttrlib.TTTR()
    running = 0
    first_header_src = None
    for in_path in in_paths:
        filetype = resolve_filetype(input_format, in_path)
        tttr = load(in_path, filetype)
        if first_header_src is None:
            first_header_src = tttr
        mt = tttr.macro_times
        if len(mt) == 0:
            continue
        offset = int(running) - int(mt[0])
        merged.append_events(
            mt, tttr.micro_times, tttr.routing_channels, tttr.event_types, True, offset
        )
        running = int(mt[-1]) + offset + 1
    apply_alex(merged, alex_period, period_shift)
    _ensure_parent(out_path)
    # Carry the first file's header (transcoded if the output container differs).
    header = _prepare_output_header(first_header_src, output_format, input_format)
    if header is not None:
        merged.write(out_path, header)
    else:
        merged.write(out_path, first_header_src.header)
    return out_path


__all__ = [
    "CONTAINER_INFO",
    "supported_containers",
    "input_format_options",
    "resolve_filetype",
    "container_ext",
    "default_output_name",
    "load",
    "apply_alex",
    "alex_histogram",
    "auto_alex_windows",
    "detect_alex_period",
    "detect_alex_channels",
    "alex_stream_masks",
    "convert_file",
    "merge_files",
]
