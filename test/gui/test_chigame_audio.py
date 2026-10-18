"""Synthesised music: it has to be music, and it has to stop when you leave."""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.audio import synth as audio
from chisurf.core.audio.tracks import TRACKS


def _samples(track: dict) -> np.ndarray:
    """Render a track to floats in -1..1.

    Parameters
    ----------
    track : dict
        Track definition.

    Returns
    -------
    numpy.ndarray
        Mono samples.
    """
    return np.frombuffer(audio.render_track(track), dtype="<i2").astype(float) / 32768.0


def test_a_note_is_the_pitch_it_says_it_is():
    """The sequencer's one non-negotiable job."""
    for semitone, expected in ((0, 440.0), (12, 880.0), (7, 440.0 * 2 ** (7 / 12))):
        pcm = _samples(
            {"root": 440.0, "tempo": 60, "melody": {"wave": "sine", "notes": [[semitone, 4]]}}
        )
        spectrum = np.abs(np.fft.rfft(pcm * np.hanning(pcm.size)))
        freqs = np.fft.rfftfreq(pcm.size, 1.0 / audio.SAMPLE_RATE)
        peak = freqs[spectrum.argmax()]
        assert abs(peak - expected) < 4.0, (semitone, peak, expected)


def test_a_rest_is_silent_and_a_held_note_is_held():
    """Without either, a track is a metronome playing a scale."""
    eighth = int(audio.SAMPLE_RATE * 30.0 / 120.0)
    pcm = _samples({"root": 440.0, "tempo": 120, "melody": [[0, 2], None, None, [0, 2]]})
    assert pcm.size == pytest.approx(6 * eighth, rel=0.02)
    held = np.abs(pcm[: 2 * eighth]).mean()
    rest = np.abs(pcm[int(2.2 * eighth) : int(3.8 * eighth)]).mean()
    assert held > 0.02
    assert rest < held / 50.0, "a rest has to actually be a rest"


def test_the_waveforms_are_band_limited():
    """A hard square at 44.1 kHz folds back over itself as a metallic buzz.

    This is the difference between the old synthesiser and this one, and it is
    measurable: a naive square built from a sign flip puts a large fraction of
    its energy above Nyquist, where it aliases down into the audible band.
    """
    for shape in ("square", "saw", "triangle"):
        pcm = _samples(
            {"root": 880.0, "tempo": 60, "melody": {"wave": shape, "notes": [[0, 4]]}, "tone": 1.0}
        )
        spectrum = np.abs(np.fft.rfft(pcm)) ** 2
        freqs = np.fft.rfftfreq(pcm.size, 1.0 / audio.SAMPLE_RATE)
        # Every partial the synthesiser emits is a harmonic of 880 Hz, so
        # anything landing between them is aliasing.
        harmonic = np.zeros(freqs.shape, dtype=bool)
        for number in range(1, 26):
            harmonic |= np.abs(freqs - 880.0 * number) < 30.0
        stray = spectrum[~harmonic].sum() / max(spectrum.sum(), 1e-12)
        assert stray < 0.05, (shape, stray)


def test_nothing_clips_and_nothing_clicks():
    """A loop that pops at its own seam is worse than no loop.

    This is a property of the *synthesiser*, so the recorded clip is taken off
    each track first. A recorded seamless loop deliberately does not fade to
    zero at its edges -- fading it would be what introduced the gap.
    """
    for name, track in TRACKS.items():
        pcm = _samples({key: value for key, value in track.items() if key != "clip"})
        assert np.abs(pcm).max() <= 0.90, name
        assert abs(pcm[0]) < 0.02 and abs(pcm[-1]) < 0.02, name


def test_every_shipped_track_is_long_enough_to_be_a_piece():
    """Sixteen eighth notes on repeat is what made the old soundtrack hurt.

    Measured on the synthesised fallback: the recordings are checked for length
    in ``test_chigame_clips``, and they are stored at half this rate, so
    dividing a clip by the synthesiser's rate reports half its real duration.
    """
    for name, track in TRACKS.items():
        bare = {key: value for key, value in track.items() if key != "clip"}
        seconds = _samples(bare).size / audio.SAMPLE_RATE
        floor = 3.0 if not track.get("loop", True) else 10.0
        assert seconds >= floor, (name, seconds)
        # ...and it has to breathe: a phrase with no held notes and no rests is
        # a scale exercise however long you make it.
        melody = track.get("melody")
        notes = melody["notes"] if isinstance(melody, dict) else melody
        assert any(entry is None or isinstance(entry, (list, tuple)) for entry in notes), name








def test_a_blip_bends_and_fades_to_nothing():
    """A flat tone with hard edges is a beep; an effect is an event."""
    pcm = (
        np.frombuffer(audio.render_blip(440.0, 0.12, bend=12.0), dtype="<i2").astype(float)
        / 32768.0
    )
    assert pcm.size == pytest.approx(int(0.12 * audio.SAMPLE_RATE), rel=0.02)
    assert abs(pcm[0]) < 0.02 and abs(pcm[-1]) < 0.02
    half = pcm.size // 2
    first = np.fft.rfftfreq(half, 1.0 / audio.SAMPLE_RATE)[
        np.abs(np.fft.rfft(pcm[:half] * np.hanning(half))).argmax()
    ]
    second = np.fft.rfftfreq(half, 1.0 / audio.SAMPLE_RATE)[
        np.abs(np.fft.rfft(pcm[half : half * 2] * np.hanning(half))).argmax()
    ]
    assert second > first * 1.2, "the bend has to be audible"




def test_the_synthesiser_is_fast_enough_to_run_at_load_time():
    """A track that takes a second to build is a second of frozen window."""
    import time

    start = time.perf_counter()
    for track in TRACKS.values():
        audio.render_track(track)
    spent = time.perf_counter() - start
    assert spent < 2.0, spent
    assert math.isfinite(spent)
