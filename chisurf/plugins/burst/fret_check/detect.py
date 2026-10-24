"""What is in a file: its container, and what experiment recorded it.

The page takes whatever the user drops. tttrlib infers the container from the
file (PTU, HT3, SPC, SM, PTO, ...); this module then reads the photons to guess
the *experiment*:

* **excitation** -- ``"cw"`` (one excitation) or ``"alternating"`` (PIE /
  nsALEX / µsALEX folded into the micro time). Alternation shows up as a
  micro-time window in which some detectors go dark: the acceptor-excitation
  window, where donor detectors see (almost) nothing.
* **detectors** -- which routing channels are donor and which acceptor. With
  alternation the donor channels are the ones that are dark in the acceptor
  window. Without it the data cannot tell, so the lowest channels are donor by
  convention and the user can swap them.
* **polarization** -- four (or more) channels are taken as parallel /
  perpendicular pairs per colour.

Every guess is a starting point shown in the UI and editable there.
"""
from __future__ import annotations

import dataclasses
import pathlib

import numpy as np

__all__ = ["Experiment", "Window", "assign_cw", "detect_experiment", "find_alex_period", "load",
           "open_measurement", "with_phase"]

#: Coarse micro-time bins used for the window search.
_N_BINS = 64
#: A donor detector is "dark" under acceptor excitation: its mean count per
#: bin there is below this fraction of its mean under donor excitation.
_DARK = 0.15


@dataclasses.dataclass
class Window:
    """A micro-time window ``[start, stop)`` in micro-time channels."""

    name: str  # "donor" (donor excitation) or "acceptor"
    start: int
    stop: int


@dataclasses.dataclass
class Experiment:
    container: str
    n_photons: int
    duration_s: float
    macro_time_resolution_s: float
    micro_time_resolution_s: float
    n_micro_channels: int
    channels: list[int]
    channel_counts: dict[int, int]
    excitation: str = "cw"  # "cw" | "alternating"
    windows: list[Window] = dataclasses.field(default_factory=list)
    donor_channels: list[int] = dataclasses.field(default_factory=list)
    acceptor_channels: list[int] = dataclasses.field(default_factory=list)
    polarization: bool = False
    #: µsALEX recorded in the macro time: the alternation period in ticks.
    alex_period: int = 0
    #: Channels that carry photons but no single-molecule signal (dark
    #: counts, scatter, markers, an empty detector): left out of the streams.
    unassigned_channels: list[int] = dataclasses.field(default_factory=list)
    #: Per colour, the ``[parallel, perpendicular]`` routing channels when
    #: polarization resolved (ChiSurf's detector_setups order).
    donor_pol: list[int] = dataclasses.field(default_factory=list)
    acceptor_pol: list[int] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)
    #: What the user must check: guesses the data could not settle.
    warnings: list[str] = dataclasses.field(default_factory=list)

    @property
    def alternation(self) -> str:
        """``""`` (cw), ``"PIE"`` (ns pulses in the micro time) or ``"µsALEX"``."""
        if self.excitation != "alternating":
            return ""
        if self.alex_period or not (0 < self.micro_time_resolution_s < 1e-9):
            return "µsALEX"
        return "PIE"

    @property
    def kind(self) -> str:
        """A short label: ``2c cw``, ``2c ALEX/PIE``, ``MFD (PIE + pol)``..."""
        if not self.acceptor_channels:
            return "1c"
        parts = ["2c", self.alternation or "cw"]
        if self.polarization:
            return "MFD (" + " + ".join(parts[1:]) + " + pol)"
        return " ".join(parts)

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["kind"] = self.kind
        return d


def load(path):
    """Open a TTTR file; the container is inferred by tttrlib."""
    import tttrlib  # noqa: PLC0415

    path = str(pathlib.Path(path))
    data = tttrlib.TTTR(path)
    if len(data) == 0:
        raise ValueError(f"{path}: no photons read (unsupported or empty file)")
    return data


def _micro_histograms(micro, routing, channels, n_micro):
    """Per-channel micro-time histograms in ``_N_BINS`` coarse bins."""
    n_bins = min(_N_BINS, n_micro)
    scale = n_micro / n_bins
    idx = np.minimum((micro / scale).astype(np.int64), n_bins - 1)
    hist = {}
    for c in channels:
        hist[c] = np.bincount(idx[routing == c], minlength=n_bins).astype(float)
    return hist, scale


def _onsets(h: np.ndarray, frac: float = 0.15) -> list[int]:
    """Bins where *h* rises steeply -- an excitation pulse (circular).

    A rise counts when it is a sizeable fraction of the channel's maximum and
    well above Poisson noise; the bins of one rise are merged into its first.
    A decay never rises, so a single-pulse measurement has one onset per
    channel however fast its fluorescence decays.
    """
    n = h.size
    prev = np.roll(h, 1)
    step = h - prev
    rise = (step > frac * h.max()) & (step > 5.0 * np.sqrt(np.maximum(prev, 1.0)))
    idx = list(np.flatnonzero(rise))
    groups: list[list[int]] = []
    for i in idx:
        if groups and i - groups[-1][-1] <= 2:
            groups[-1].append(i)
        else:
            groups.append([i])
    if len(groups) > 1 and groups[0][0] + n - groups[-1][-1] <= 2:
        groups[0] = groups.pop() + groups[0]
    return [int(g[0]) for g in groups]


def _find_alternation(hist, n_bins):
    """Two excitations: ``(donor_bins, acceptor_bins, donor_channels)`` or ``None``.

    Alternation (PIE, nsALEX, µsALEX folded into the micro time) shows as two
    separate onsets. The donor-excitation onset is the one every channel shares
    (DD and DA both light up); in the window from the other onset the donor
    detectors are dark.
    """
    channels = [c for c in hist if hist[c].sum() > 0]
    if len(channels) < 2:
        return None
    onsets = {c: _onsets(hist[c]) for c in channels}
    distinct: list[int] = []
    for o in sorted(o for os_ in onsets.values() for o in os_):
        if not distinct or o - distinct[-1] > 2:
            distinct.append(o)
    if len(distinct) > 1 and distinct[0] + n_bins - distinct[-1] <= 2:
        distinct.pop()
    if len(distinct) < 2:
        return None

    def near(o, os_):
        return any(min(abs(o - x), n_bins - abs(o - x)) <= 2 for x in os_)

    # Prefer a donor onset every channel shares (DD and DA both light up);
    # without a gap between the alternation periods a folded µsALEX
    # histogram has no rise of the acceptor channel there, so every onset is
    # tried, and the pair whose acceptor window darkens some -- not all --
    # channels wins.
    shared = [o for o in distinct if all(near(o, onsets[c]) for c in channels)]
    bins = np.arange(n_bins)
    for d_on in shared + [o for o in distinct if o not in shared]:
        others = [o for o in distinct if o != d_on]
        a_on = max(others, key=lambda o: max(hist[c][o] - hist[c][o - 1] for c in channels))
        if d_on < a_on:
            donor_bins, acceptor_bins = (bins >= d_on) & (bins < a_on), bins >= a_on
        else:
            acceptor_bins, donor_bins = (bins >= a_on) & (bins < d_on), bins >= d_on
        donor_channels = [
            c for c in channels
            if hist[c][acceptor_bins].mean() < _DARK * hist[c][donor_bins].mean()
        ]
        if donor_channels and len(donor_channels) < len(channels):
            break
    else:
        return None
    return donor_bins, acceptor_bins, donor_channels


def find_alex_period(data, channels, bin_s: float = 5e-6, max_bins: int = 1 << 22):
    """The µsALEX period in macro-time ticks, or ``None``.

    Some files keep the alternation only in the macro time (no micro time, or
    a micro time unrelated to it). The count rate of the detectors then
    oscillates at the alternation frequency: the strongest peak of the binned
    count rate's spectrum between 1 and 50 kHz, at least 30x the median, gives
    the period. It is refined to the integer number of ticks whose fold
    has the deepest contrast.
    """
    res = float(data.header.macro_time_resolution)
    macro = np.asarray(data.macro_times).astype(np.int64)
    routing = np.asarray(data.routing_channels)
    if macro.size < 10_000 or res <= 0:
        return None
    best = None
    for c in channels:
        t = macro[routing == c]
        if t.size < 10_000:
            continue
        idx = ((t - t[0]) * res / bin_s).astype(np.int64)
        idx = idx[idx < max_bins]
        counts = np.bincount(idx).astype(float)
        if counts.size < 1024:
            continue
        spec = np.abs(np.fft.rfft(counts - counts.mean()))
        freq = np.fft.rfftfreq(counts.size, bin_s)
        band = (freq > 1e3) & (freq < min(5e4, 0.4 / bin_s))
        if not band.any():
            continue
        k = np.flatnonzero(band)[np.argmax(spec[band])]
        ratio = spec[k] / max(np.median(spec[band]), 1e-12)
        if ratio > 30 and (best is None or ratio > best[1]):
            best = (freq[k], ratio)
    if best is None:
        return None
    period = 1.0 / (best[0] * res)
    # Refine: the fold contrast, per channel -- the channels' sum can be flat
    # when both excitations give the same total intensity.
    n_sample = min(macro.size, 2_000_000)
    sample, sample_ch = macro[:n_sample], routing[:n_sample]
    lo, hi = int(period * 0.995), int(np.ceil(period * 1.005))
    candidates = range(max(2, lo), hi + 1)

    def contrast(P):
        total = 0.0
        for c in channels:
            h = np.bincount((sample[sample_ch == c] % P) * 64 // P, minlength=64).astype(float)
            total += h.std() / max(h.mean(), 1e-12)
        return total

    return int(max(candidates, key=contrast))


def with_phase(data, period: int):
    """A TTTR whose micro time is the alternation phase ``macro % period``.

    Everything downstream (windows, streams, ALEX-2CDE) then reads µsALEX
    exactly like nsALEX/PIE.
    """
    import tttrlib  # noqa: PLC0415

    macro = np.asarray(data.macro_times).astype(np.uint64)
    phase = (macro % np.uint64(period)).astype(np.uint16) if period < 65536 else None
    if phase is None:
        raise ValueError(f"alternation period {period} ticks too long for a 16 bit micro time")
    out = tttrlib.TTTR(macro, phase, np.asarray(data.routing_channels), np.asarray(data.event_types))
    out.header.set_macro_time_resolution(float(data.header.macro_time_resolution))
    out.header.set_micro_time_resolution(float(data.header.macro_time_resolution))
    return out


def _burst_channel_counts(data, channels):
    """Per-burst photon counts per channel ``(n_bursts, n_channels)``, default search."""
    from .pipeline import BurstSettings, find_bursts  # noqa: PLC0415

    routing = np.asarray(data.routing_channels)
    bursts = find_bursts(data, BurstSettings())
    cols = []
    for c in channels:
        cum = np.concatenate([[0], np.cumsum(routing == c)])
        cols.append(cum[bursts[:, 1] + 1] - cum[bursts[:, 0]])
    return np.stack(cols, axis=1).astype(float) if cols else np.zeros((0, 0))


def assign_cw(data, channels, notes):
    """Donor and acceptor channels of a cw measurement, from its bursts.

    * **Colours.** Channels of one colour (parallel / perpendicular) rise and
      fall together from burst to burst; the two colours trade photons. Each
      channel's share of a burst's photons is correlated with the brightest
      channel's: positive is its colour, negative the other.
    * **Which colour is the donor.** With one excitation the acceptor is only
      excited through FRET, so donor-only molecules give bursts of the donor
      colour alone, while bursts of the acceptor colour alone are rare. The
      colour with more single-colour bursts is the donor.

    Falls back to channel order when there are too few bursts or no
    asymmetry, and says so in *notes*.
    """
    if len(channels) < 2:
        return list(channels), []
    counts = _burst_channel_counts(data, channels)
    if counts.shape[0] < 50:
        half = max(1, len(channels) // 2)
        notes.append("too few bursts to assign colours; donor/acceptor guessed from channel order, check them")
        return channels[:half], channels[half:]
    share = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1.0)
    totals = counts.sum(axis=0)
    ref = int(np.argmax(totals))
    if len(channels) == 2:
        group_a = [channels[ref]]
    else:
        # The colour of the brightest channel: closer (in burst-to-burst
        # correlation) to it than to the channel most opposed to it.
        corr = np.nan_to_num(np.corrcoef(share.T))
        anti = int(np.argmin(corr[ref]))
        group_a = [c for i, c in enumerate(channels) if i == ref or corr[i, ref] > corr[i, anti]]
    group_b = [c for c in channels if c not in group_a]
    if not group_b:
        notes.append("all channels correlate (one colour?); donor/acceptor guessed from order")
        half = max(1, len(channels) // 2)
        return channels[:half], channels[half:]
    ia = [channels.index(c) for c in group_a]
    frac_a = share[:, ia].sum(axis=1)
    alone_a = float(np.mean(frac_a > 0.85))
    alone_b = float(np.mean(frac_a < 0.15))
    photons_b = float(totals[[channels.index(c) for c in group_b]].sum() / max(totals.sum(), 1.0))
    if min(photons_b, 1 - photons_b) < 0.02:
        donor, acceptor = (group_a, group_b) if photons_b < 0.5 else (group_b, group_a)
        notes.append(f"second colour has {100 * min(photons_b, 1 - photons_b):.1f} % of the burst photons: "
                     "one-colour data, or no FRET and no acceptor")
    elif max(alone_a, alone_b) < 0.02 or abs(alone_a - alone_b) < 0.01:
        donor, acceptor = sorted([group_a, group_b], key=min)
        notes.append("no donor-only population to tell donor from acceptor; guessed from channel order, check them")
    else:
        donor, acceptor = (group_a, group_b) if alone_a > alone_b else (group_b, group_a)
        notes.append(f"donor = colour with single-colour (donor-only) bursts "
                     f"({100 * max(alone_a, alone_b):.0f} % vs {100 * min(alone_a, alone_b):.0f} %)")
    return sorted(donor), sorted(acceptor)


def signal_channels(data, channels, exp=None):
    """The channels that carry single-molecule signal, and the rest.

    A detector that sees molecules counts faster inside bursts than outside;
    dark counts, scatter, a marker line or an unconnected detector count the
    same everywhere. The burst search runs on all photons; a channel whose
    in-burst rate is not at least twice its out-of-burst rate is set aside.
    Returns ``(signal, unassigned)``; reasons go to *exp*'s warnings.
    """
    from .pipeline import BurstSettings, find_bursts  # noqa: PLC0415

    routing = np.asarray(data.routing_channels)
    macro = np.asarray(data.macro_times).astype(np.float64)
    if len(channels) < 2 or macro.size < 1000:
        return list(channels), []
    bursts = find_bursts(data, BurstSettings())
    if len(bursts) < 20:
        return list(channels), []
    inside = np.zeros(routing.size + 1, np.int64)
    np.add.at(inside, bursts[:, 0], 1)
    np.add.at(inside, bursts[:, 1] + 1, -1)
    in_burst = np.cumsum(inside)[:-1] > 0
    t_in = float(np.sum(macro[bursts[:, 1]] - macro[bursts[:, 0]]))
    t_out = max(float(macro[-1] - macro[0]) - t_in, 1.0)
    signal, unassigned = [], []
    for c in channels:
        sel = routing == c
        n_in, n_out = float(np.sum(sel & in_burst)), float(np.sum(sel & ~in_burst))
        enrichment = (n_in / max(t_in, 1.0)) / max(n_out / t_out, 1e-12)
        share = n_in / max(float(np.sum(in_burst)), 1.0)
        if enrichment < 2.0 or share < 0.005:
            unassigned.append(c)
            if exp is not None:
                exp.warnings.append(
                    f"channel {c} not assigned: no single-molecule signal "
                    f"({100 * share:.1f} % of burst photons, {enrichment:.1f}x enriched in bursts) -- "
                    "dark counts, scatter, a marker line or an unused detector")
        else:
            signal.append(c)
    if not signal:  # nothing stands out: keep everything rather than nothing
        return list(channels), []
    return signal, unassigned


def _pol_order(data, chans):
    """``[parallel, perpendicular]``: the brighter of a colour's two channels is
    parallel (fluorescence anisotropy is positive)."""
    routing = np.asarray(data.routing_channels)
    return sorted(chans, key=lambda c: -int(np.sum(routing == c)))


def open_measurement(path):
    """Load *path*, detect the experiment, and return ``(data, experiment)``.

    For µsALEX recorded in the macro time the returned data is
    :func:`with_phase`'s, so the caller never needs to know.
    """
    data = load(path)
    exp = detect_experiment(data)
    if exp.alex_period:
        data = with_phase(data, exp.alex_period)
    return data, exp


def detect_experiment(data) -> Experiment:
    """Guess the experiment from the photons (see the module docstring)."""
    header = data.header
    routing = np.asarray(data.routing_channels)
    macro = np.asarray(data.macro_times)
    channels = sorted(int(c) for c in np.unique(routing))
    counts = {c: int((routing == c).sum()) for c in channels}
    # Drop channels with a negligible share (markers, crosstalk lines).
    total = sum(counts.values())
    channels = [c for c in channels if counts[c] > 1e-3 * total]
    mres = float(header.macro_time_resolution)
    ures = float(header.micro_time_resolution)
    n_micro = int(data.get_number_of_micro_time_channels() or 0)
    micro = np.asarray(data.micro_times)
    if micro.size:
        # The header's count can be smaller than the range actually used
        # (tttrlib derives it from macro/micro resolution, which is wrong when
        # the laser period exceeds the macro clock): the data decides.
        n_micro = max(n_micro, int(micro.max()) + 1)
    exp = Experiment(
        container=str(data.get_tttr_container_type()),
        n_photons=int(len(data)),
        duration_s=float((macro[-1] - macro[0]) * mres) if macro.size else 0.0,
        macro_time_resolution_s=mres,
        micro_time_resolution_s=ures if ures > 0 else 0.0,
        n_micro_channels=n_micro,
        channels=channels,
        channel_counts={c: counts[c] for c in channels},
    )

    # 0. Which channels carry single-molecule signal at all.
    all_channels = channels
    channels, exp.unassigned_channels = signal_channels(data, all_channels, exp)
    sel = np.isin(routing, channels)

    # 1. Alternation in the micro time (PIE / nsALEX, or µsALEX already folded).
    alternation, scale = None, 1.0
    if n_micro > 8:
        step = max(1, micro.size // 2_000_000)  # a sample is plenty for the shape
        hist, scale = _micro_histograms(micro[sel][::step], routing[sel][::step], channels, n_micro)
        alternation = _find_alternation(hist, len(next(iter(hist.values()))))
    # 2. Alternation only in the macro time (µsALEX).
    if alternation is None and len(channels) >= 2:
        period = find_alex_period(data, channels)
        if period:
            phase = (macro[sel].astype(np.int64) % period)
            step = max(1, phase.size // 2_000_000)
            hist, scale = _micro_histograms(phase[::step], routing[sel][::step], channels, period)
            alternation = _find_alternation(hist, len(next(iter(hist.values()))))
            if alternation is not None:
                exp.alex_period = int(period)
                exp.n_micro_channels = int(period)
                exp.micro_time_resolution_s = mres
                exp.notes.append(f"µsALEX in the macro time: {1e-3 / (period * mres):.2f} kHz alternation")

    if alternation is not None:
        donor_bins, acceptor_bins, dark_channels = alternation
        exp.excitation = "alternating"
        exp.donor_channels = sorted(dark_channels)
        exp.acceptor_channels = [c for c in channels if c not in dark_channels]
        d = np.flatnonzero(donor_bins)
        a = np.flatnonzero(acceptor_bins)
        exp.windows = [
            Window("donor", int(d[0] * scale), int((d[-1] + 1) * scale)),
            Window("acceptor", int(a[0] * scale), int((a[-1] + 1) * scale)),
        ]
    else:
        # 3. cw: one excitation. Colours and donor from the bursts.
        notes: list[str] = []
        exp.donor_channels, exp.acceptor_channels = assign_cw(data, channels, notes)
        for n in notes:  # guesses are warnings, findings are notes
            (exp.warnings if ("guess" in n or "check" in n or "one-colour" in n) else exp.notes).append(n)
    exp.polarization = len(exp.donor_channels) == 2 and len(exp.acceptor_channels) == 2
    if exp.polarization:
        exp.donor_pol = _pol_order(data, exp.donor_channels)
        exp.acceptor_pol = _pol_order(data, exp.acceptor_channels)
        exp.warnings.append(f"polarization guessed: donor par/perp {exp.donor_pol}, acceptor par/perp "
                            f"{exp.acceptor_pol} (brighter = parallel; a G factor far from 1 can swap them)")
    elif len(exp.donor_channels) > 2 or len(exp.acceptor_channels) > 2:
        exp.warnings.append(f"{len(exp.donor_channels)} donor / {len(exp.acceptor_channels)} acceptor channels: "
                            "more than two per colour, polarization not assigned; check them")
    if not exp.acceptor_channels:
        exp.warnings.append("no acceptor channel: one-colour data, FRET checks are off")
    return exp
