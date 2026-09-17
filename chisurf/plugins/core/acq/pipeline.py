"""Acquisition is a stream: raw device words in, display state out.

One object owns everything that happens to a photon between the card and the
screen — decode, the live consumers, the stop conditions — and it is Qt-free,
so the GUI thread, a standalone CLI and a test drive the *same* pipeline
instead of three that resemble each other.

What this replaces, and why
---------------------------

The acquisition plugin used to decode a chunk and then throw the streaming
away: every photon was ``np.concatenate``-ed onto three growing arrays, the
*batch* correlator was re-run over the entire history every five chunks, and
the MCS trace binned every photon of the run to display its last second. All
three costs grow with elapsed run time, so a 30-minute measurement updated its
display more slowly than a one-minute one, and memory grew without bound. The
photon library ships streaming twins of exactly those consumers, each verified
against its batch counterpart, and they cost O(chunk) per update and O(1) in
run length.

Nothing downstream of :meth:`AcquisitionPipeline.push` ever sees "all photons
so far". What stays in memory is display state: histogram accumulators,
correlator cascade levels, a rolling MCS window and two bounded deques.

One decode path
---------------

Every device's raw words go through ``tttrlib.decode_records`` with the
device's record type and a carried :class:`DecodeState` — the overflow counter
is what makes macro times absolute across chunk boundaries, and a fresh state
per chunk restarts the clock at zero on the second chunk, which looks like a
working acquisition right up until it does not. There is no hand-rolled
bit-field decoder here and there must never be one again: a format is the
library's to know.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np
import tttrlib

logger = logging.getLogger(__name__)


#: Record type per device type, for devices whose format is fixed. A device
#: wrapper may override this by exposing a ``record_type`` attribute — which is
#: what PicoQuant does, since its record format follows the measurement mode.
DEVICE_RECORD_TYPES = {
    "BH_SPC": tttrlib.RECORD_SPC130,
    "BRICKMIC": tttrlib.RECORD_SPC130,
    "SIMULATION": tttrlib.RECORD_SPC130,
    "PICOQUANT": tttrlib.RECORD_HHT3v2,
}


def record_type_for_device(device) -> int:
    """Return the photon-library record type a device emits.

    Parameters
    ----------
    device : object
        A device wrapper. ``device.record_type`` wins when present, so a device
        whose format depends on its measurement mode can say so; otherwise the
        device type is looked up in :data:`DEVICE_RECORD_TYPES`.

    Returns
    -------
    int
        A ``tttrlib.RECORD_*`` constant.

    Raises
    ------
    ValueError
        If the device type is unknown. Guessing a record format is how a
        decoder that is "correct by hope" gets written; an unknown device is an
        error, not a reason to fall back to B&H.
    """
    explicit = getattr(device, "record_type", None)
    if explicit is not None:
        return int(explicit)
    device_type = getattr(device, "device_type", None)
    try:
        return DEVICE_RECORD_TYPES[device_type]
    except KeyError:
        raise ValueError(
            f"no record type known for device type {device_type!r}; give the "
            f"device a `record_type` attribute naming a tttrlib RECORD_* constant"
        ) from None


class PhotonDecoder:
    """Decode raw device words into photons, carrying overflow across chunks.

    Parameters
    ----------
    record_type : int
        A ``tttrlib.RECORD_*`` constant naming the device's record format.
    """

    def __init__(self, record_type: int):
        self.record_type = int(record_type)
        self._state = tttrlib.TTTRDecodeState()

    def reset(self) -> None:
        """Start a new acquisition — the macro-time clock returns to zero."""
        self._state = tttrlib.TTTRDecodeState()

    @property
    def overflow_counter(self) -> int:
        """Macro-time wraps seen so far, in units of the record's wrap length."""
        return int(self._state.overflow_counter)

    def decode(self, words):
        """Decode one chunk of raw words.

        Parameters
        ----------
        words : numpy.ndarray
            ``uint32`` records as read from the device FIFO.

        Returns
        -------
        tuple of numpy.ndarray
            ``(macro_times, micro_times, channels)`` — absolute macro times
            (``uint64``), TAC bins (``uint16``) and routing channels
            (``int32``). Empty arrays when the chunk holds no photons.
        """
        if words is None or len(words) == 0:
            return _EMPTY_MACRO, _EMPTY_MICRO, _EMPTY_CHANNEL
        decoded, self._state = tttrlib.decode_records(
            np.ascontiguousarray(words, dtype=np.uint32),
            self.record_type,
            self._state,
        )
        return (
            np.asarray(decoded.macro_times, dtype=np.uint64),
            np.asarray(decoded.micro_times, dtype=np.uint16),
            np.asarray(decoded.routing_channel, dtype=np.int32),
        )


_EMPTY_MACRO = np.array([], dtype=np.uint64)
_EMPTY_MICRO = np.array([], dtype=np.uint16)
_EMPTY_CHANNEL = np.array([], dtype=np.int32)


@dataclass
class PipelineConfig:
    """Everything the pipeline needs to know before the first photon.

    Attributes
    ----------
    record_type : int
        Device record format (``tttrlib.RECORD_*``).
    macrotime_clock : float
        Seconds per macro-time tick.
    channels : tuple of int
        The routing channels of the four decay/count-rate windows, in window
        order. These are *device* channel numbers and need not be 0-3.
    n_microtime_bins : int
        TAC bins of the live decay histogram.
    correlation_pairs : tuple
        ``(curve_index, channel_a, channel_b)`` per live correlation curve.
        ``-1`` on a side means every photon, and ``a == b`` is the
        autocorrelation.
    mcs_bin_width_ms, mcs_rollaround_ms : float
        Bin width and the length of the displayed window of the MCS trace. The
        window is what bounds its memory.
    time_limit_s, photon_limit : float, int
        Stop conditions; 0 disables.
    max_countrate_points, max_macrotime_points : int
        Rolling display buffers. Unbounded lists here were a second way the
        plugin's memory grew with run length, less obvious than the photon
        arrays because a "point" sounds small.
    burst_window_photons, burst_window_time_s : int, float
        Live burst-search criterion — m photons within T seconds.
    phasor_frequency_mhz : float
        Repetition rate for the live phasor.
    """

    record_type: int = tttrlib.RECORD_SPC130
    macrotime_clock: float = 50e-9
    channels: tuple = (0, 1, 2, 3)
    n_microtime_bins: int = 4096
    correlation_pairs: tuple = ((0, 0, 0),)
    correlator_n_bins: int = 9
    correlator_n_casc: int = 15
    mcs_bin_width_ms: float = 1.0
    mcs_rollaround_ms: float = 1000.0
    time_limit_s: float = 0.0
    photon_limit: int = 0
    max_countrate_points: int = 3600
    max_macrotime_points: int = 5000
    enable_burst_qc: bool = True
    burst_window_photons: int = 10
    burst_window_time_s: float = 5e-4
    enable_phasor: bool = True
    phasor_frequency_mhz: float = 73.5
    microtime_resolution_s: float = 4.069e-12


class PhotonSink:
    """Where the decoded stream is written as it arrives.

    The acquisition writes through a sink so that a run survives a crash rather
    than living in RAM until someone presses stop. The native ``.pto`` sink is
    the intended implementation and is tracked in the acquisition PRD against
    the photon library's container work; until it lands the raw vendor-word
    drip some devices offer remains the stopgap and :class:`NullSink` is used.
    """

    def write(self, macro_times, micro_times, channels) -> None:
        """Append one chunk of decoded photons."""
        raise NotImplementedError

    def checkpoint(self) -> None:
        """Make everything written so far readable by another process."""

    def close(self) -> None:
        """Finish the file."""


class NullSink(PhotonSink):
    """Drop the stream. Counts what it dropped, so the GUI can say so."""

    def __init__(self):
        self.n_photons = 0

    def write(self, macro_times, micro_times, channels) -> None:
        self.n_photons += len(macro_times)

    def close(self) -> None:
        pass


class AcquisitionPipeline:
    """Device words in, display state out — one push per chunk.

    Parameters
    ----------
    config : PipelineConfig
    sink : PhotonSink, optional
        Where the decoded stream is written. Defaults to :class:`NullSink`.

    Notes
    -----
    Not thread-safe: one thread pushes. :meth:`snapshot` builds a plain-data
    dict and is what crosses to the GUI thread.
    """

    def __init__(self, config: PipelineConfig, sink: PhotonSink | None = None):
        self.config = config
        self.sink = sink if sink is not None else NullSink()
        self.decoder = PhotonDecoder(config.record_type)
        self._build_consumers()
        self.reset()

    # ------------------------------------------------------------------
    # Construction / reset
    # ------------------------------------------------------------------

    def _build_consumers(self) -> None:
        cfg = self.config
        n_windows = len(cfg.channels)

        # Routing channel -> window index, as a lookup rather than four masks.
        # Unmapped channels get -1, which the decay histogram drops.
        self._window_of_channel = np.full(4096, -1, dtype=np.int32)
        for window, channel in enumerate(cfg.channels):
            if 0 <= int(channel) < self._window_of_channel.size:
                self._window_of_channel[int(channel)] = window

        self._decay = tttrlib.StreamingDecayHistogram(cfg.n_microtime_bins, n_windows)
        self._correlators = [
            tttrlib.StreamingCorrelator(
                cfg.correlator_n_bins, cfg.correlator_n_casc, cfg.macrotime_clock
            )
            for _ in cfg.correlation_pairs
        ]
        self._mcs = tttrlib.StreamingIntensityTrace(
            max(cfg.mcs_bin_width_ms, 1e-6) / 1000.0, cfg.macrotime_clock
        )
        self._mcs.set_max_bins(
            max(1, int(round(cfg.mcs_rollaround_ms / max(cfg.mcs_bin_width_ms, 1e-6))))
        )
        self._bursts = (
            tttrlib.StreamingBurstDetector(
                cfg.burst_window_photons,
                cfg.burst_window_time_s,
                cfg.macrotime_clock,
            )
            if cfg.enable_burst_qc
            else None
        )
        self._phasor = (
            tttrlib.StreamingPhasor(
                cfg.phasor_frequency_mhz,
                cfg.n_microtime_bins,
                cfg.microtime_resolution_s,
            )
            if cfg.enable_phasor
            else None
        )

    def reset(self) -> None:
        """Clear every consumer and start a new acquisition."""
        cfg = self.config
        n_windows = len(cfg.channels)

        self.decoder.reset()
        self._decay.clear()
        for c in self._correlators:
            c.clear()
        self._mcs.clear()
        if self._bursts is not None:
            self._bursts.clear()
        if self._phasor is not None:
            self._phasor.clear()

        self.total_photons = 0
        self.last_macro_time = 0
        self._first_macro_time = None
        self._channel_totals = [0] * n_windows

        self._count_rate_times = deque(maxlen=cfg.max_countrate_points)
        self._count_rate_data = [
            deque(maxlen=cfg.max_countrate_points) for _ in range(n_windows + 1)
        ]
        self._macrotime_diffs = deque(maxlen=cfg.max_macrotime_points)
        self._macrotime_stamps = deque(maxlen=cfg.max_macrotime_points)
        self._last_photon_of_chunk = None

        self.stop_reason = None

    # ------------------------------------------------------------------
    # The push
    # ------------------------------------------------------------------

    def push(self, words) -> int:
        """Decode one chunk of raw device words and feed every consumer.

        Parameters
        ----------
        words : numpy.ndarray
            ``uint32`` records from the device FIFO.

        Returns
        -------
        int
            Photons in this chunk.
        """
        macro, micro, channel = self.decoder.decode(words)
        n = len(macro)
        if n == 0:
            return 0

        self.sink.write(macro, micro, channel)

        windows = self._window_of_channel[np.clip(channel, 0, 4095)]
        self._decay.push_np(micro, windows)
        self._mcs.push_np(macro)
        if self._bursts is not None:
            self._bursts.push_np(macro)
        if self._phasor is not None:
            self._phasor.push_np(micro)
        for correlator, pair in zip(self._correlators, self.config.correlation_pairs):
            self._push_pair(correlator, pair, macro, channel)

        self._update_count_rates(macro, windows)
        self._update_macrotime_diffs(macro)

        if self._first_macro_time is None:
            self._first_macro_time = int(macro[0])
        self.last_macro_time = int(macro[-1])
        self.total_photons += n
        self._check_stop()
        return n

    def _push_pair(self, correlator, pair, macro, channel) -> None:
        """Feed one correlation curve, mapping its two channels onto 0 and 1.

        A photon may belong to *both* sides — that is what a pair with ``-1``
        ("every photon") on one side means — and the correlator takes one
        channel per push, so such a photon is pushed twice at the same macro
        time. Pushing it once would silently correlate a different pair of
        streams than the one the operator asked for.
        """
        _idx, ch_a, ch_b = pair
        if ch_a == ch_b:
            selected = macro if ch_a < 0 else macro[channel == ch_a]
            if selected.size:
                correlator.push_np(selected)
            return

        mask_a = np.ones(len(macro), dtype=bool) if ch_a < 0 else channel == ch_a
        mask_b = np.ones(len(macro), dtype=bool) if ch_b < 0 else channel == ch_b
        if not np.any(mask_a & mask_b):
            selected = mask_a | mask_b
            if not np.any(selected):
                return
            labels = np.where(mask_a, 0, 1).astype(np.int32)
            correlator.push_np(macro[selected], None, labels[selected])
            return

        # Overlapping sides: merge the two streams, keeping time order.
        t_a, t_b = macro[mask_a], macro[mask_b]
        times = np.concatenate([t_a, t_b])
        labels = np.concatenate(
            [np.zeros(len(t_a), dtype=np.int32), np.ones(len(t_b), dtype=np.int32)]
        )
        order = np.argsort(times, kind="stable")
        correlator.push_np(times[order], None, labels[order])

    def _update_count_rates(self, macro, windows) -> None:
        """Append one count-rate point per chunk, per window plus the sum."""
        clock = self.config.macrotime_clock
        now = float(macro[-1]) * clock
        previous = self._count_rate_times[-1] if self._count_rate_times else None
        self._count_rate_times.append(now)
        span = (now - previous) if previous is not None else 0.0

        counts = np.bincount(windows[windows >= 0], minlength=len(self.config.channels))
        total = 0.0
        for i in range(len(self.config.channels)):
            self._channel_totals[i] += int(counts[i])
            rate = (counts[i] / span) if span > 0 else 0.0
            self._count_rate_data[i].append(rate)
            total += rate
        self._count_rate_data[-1].append(total)

    def _update_macrotime_diffs(self, macro) -> None:
        """Inter-photon times, bounded — the display shows the recent tail."""
        if self._last_photon_of_chunk is not None:
            macro = np.concatenate([[self._last_photon_of_chunk], macro])
        if len(macro) > 1:
            diffs = np.diff(macro.astype(np.float64)) * self.config.macrotime_clock
            stamp = float(macro[-1]) * self.config.macrotime_clock
            self._macrotime_diffs.extend(diffs.tolist())
            self._macrotime_stamps.extend([stamp] * len(diffs))
        self._last_photon_of_chunk = int(macro[-1])

    def _check_stop(self) -> None:
        cfg = self.config
        if cfg.time_limit_s > 0:
            elapsed = self.elapsed_s
            if elapsed >= cfg.time_limit_s:
                self.stop_reason = f"Time limit reached ({elapsed:.1f} s)"
                return
        if cfg.photon_limit > 0 and self.total_photons >= cfg.photon_limit:
            self.stop_reason = f"Photon limit reached ({self.total_photons:,} photons)"

    # ------------------------------------------------------------------
    # Reading the state
    # ------------------------------------------------------------------

    @property
    def elapsed_s(self) -> float:
        """Acquisition time as the photons report it, not as the wall clock does."""
        if self._first_macro_time is None:
            return 0.0
        return float(self.last_macro_time - self._first_macro_time) * self.config.macrotime_clock

    @property
    def mean_count_rate_khz(self) -> float:
        elapsed = self.elapsed_s
        if elapsed <= 0:
            return 0.0
        return self.total_photons / elapsed / 1000.0

    def decay(self, window: int):
        """The live decay histogram of one window."""
        return np.asarray(self._decay.get_histogram(window), dtype=float)

    def correlation(self, curve: int):
        """``(lag [ms], G)`` of one live correlation curve, or ``None``.

        The correlator publishes bins up to the last *completed* one, so a
        curve that has not yet seen a full coarse bin has nothing to show.
        """
        correlator = self._correlators[curve]
        if correlator.photon_count() < 10:
            return None
        x = np.asarray(correlator.get_x_axis(), dtype=float)
        y = np.asarray(correlator.get_correlation_normalized(), dtype=float)
        if not np.any(np.isfinite(y)) or not len(x):
            return None
        # The correlator was given the macro-time resolution, so its axis is
        # already in seconds -- multiplying by the clock again (as the batch
        # path had to) squares it, and the curve lands 8 decades off the plot.
        return x * 1e3, y

    def mcs_trace(self):
        """``(bin start [ms], counts)`` of the rolling MCS window."""
        y = np.asarray(self._mcs.counts(), dtype=float)
        if not len(y):
            return None
        first = self._mcs.first_bin_index()
        x = (first + np.arange(len(y))) * self.config.mcs_bin_width_ms
        return x, y

    def snapshot(self) -> dict:
        """Plain data for the display — one dict per refresh.

        This is the only thing that crosses to the GUI thread, and it contains
        no photon arrays: every entry is display state whose size is set by the
        configuration, not by how long the acquisition has been running.
        """
        correlations = [self.correlation(i) for i in range(len(self._correlators))]
        n_windows = len(self.config.channels)
        return {
            "decay_data": [self.decay(i) for i in range(n_windows)],
            "correlation_results": correlations,
            "correlation_pairs": list(self.config.correlation_pairs),
            "mcs_trace": self.mcs_trace(),
            "count_rate_times": list(self._count_rate_times),
            "count_rate_data": [list(d) for d in self._count_rate_data],
            "macrotime_data": list(self._macrotime_diffs),
            "macrotime_times": list(self._macrotime_stamps),
            "total_photons": self.total_photons,
            "channel_totals": list(self._channel_totals),
            "mean_count_rate_khz": self.mean_count_rate_khz,
            "elapsed_s": self.elapsed_s,
            "burst_count": (self._bursts.burst_count if self._bursts is not None else None),
            "burst_rate_hz": (
                (self._bursts.burst_count / self.elapsed_s)
                if self._bursts is not None and self.elapsed_s > 0
                else 0.0
            ),
            "phasor": (tuple(self._phasor.get_phasor()) if self._phasor is not None else None),
            "stop_reason": self.stop_reason,
        }

    def flush(self) -> None:
        """Finish the run: emit the correlators' last bin and close the sink."""
        for correlator in self._correlators:
            try:
                correlator.flush()
            except RuntimeError:
                # flush() is idempotent, but a correlator that never saw a
                # photon has nothing to emit and says so.
                pass
        self.sink.close()
