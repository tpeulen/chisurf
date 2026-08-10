"""Synthesised music and sound effects.

No audio files ship. The pattern already existed in the tree — the arcade games
each generated their WAV data programmatically and played it through Qt — and
this module is that idea consolidated and extended into a small sequencer, so
five near-identical copies become one.

Music is **context-driven**: a game says where it is (``"overworld"``,
``"battle"``, …) and the mixer crossfades. It never manages playback. The track
data itself comes from the active :class:`~chisurf.gui.chigame.assets.AssetPack`,
so swapping the pack swaps the soundtrack along with the art.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import struct
import tempfile
import wave

#: Sample rate. 22.05 kHz is plenty for square and triangle waves and keeps the
#: synthesis cost low enough to run at load time without a visible pause.
SAMPLE_RATE = 22050

#: Musical contexts a game may be in.
CONTEXTS = ("overworld", "town", "battle", "underworld", "victory")


def _wave_sample(shape: str, phase: float) -> float:
    """One sample of a periodic waveform.

    Parameters
    ----------
    shape : {'sine', 'square', 'triangle', 'saw'}
        Waveform name. An unknown name falls back to a sine, because silence
        would be a harder bug to notice than a wrong timbre.
    phase : float
        Position in the cycle, in turns (0..1).

    Returns
    -------
    float
        Sample in -1..1.
    """
    p = phase % 1.0
    if shape == "square":
        return 1.0 if p < 0.5 else -1.0
    if shape == "triangle":
        return 4.0 * abs(p - 0.5) - 1.0
    if shape == "saw":
        return 2.0 * p - 1.0
    return math.sin(2.0 * math.pi * p)


def _envelope(index: int, total: int, attack: float = 0.02, release: float = 0.25) -> float:
    """Amplitude envelope for one note.

    A bare tone with hard edges clicks; this shapes the attack and release so a
    sequence sounds like music rather than a modem.

    Parameters
    ----------
    index : int
        Sample index within the note.
    total : int
        Length of the note in samples.
    attack : float, optional
        Fraction of the note spent rising.
    release : float, optional
        Fraction of the note spent falling.

    Returns
    -------
    float
        Gain in 0..1.
    """
    t = index / max(total, 1)
    if t < attack:
        return t / attack
    if t > 1.0 - release:
        return max(0.0, (1.0 - t) / release)
    return 1.0


def render_track(track: dict) -> bytes:
    """Synthesise a track's note data into 16-bit mono PCM.

    Parameters
    ----------
    track : dict
        Keys: ``root`` (Hz), ``tempo`` (BPM), ``wave``, ``melody`` and ``bass``
        as lists of semitone offsets from the root.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    root = float(track.get("root", 261.63))
    tempo = float(track.get("tempo", 100))
    shape = str(track.get("wave", "triangle"))
    melody = list(track.get("melody", []))
    bass = list(track.get("bass", []))

    # An eighth note for the melody, a quarter for the bass, so one bass note
    # spans two melody notes and the two lines stay locked without bookkeeping.
    eighth = int(SAMPLE_RATE * 30.0 / max(tempo, 1.0))
    total = eighth * max(len(melody), len(bass) * 2, 1)

    samples = [0.0] * total
    for i, semitone in enumerate(melody):
        freq = root * (2.0 ** (semitone / 12.0))
        start = i * eighth
        for n in range(eighth):
            if start + n >= total:
                break
            samples[start + n] += (
                0.32 * _envelope(n, eighth) * _wave_sample(shape, freq * n / SAMPLE_RATE)
            )
    for i, semitone in enumerate(bass):
        freq = root * (2.0 ** (semitone / 12.0))
        start = i * eighth * 2
        length = eighth * 2
        for n in range(length):
            if start + n >= total:
                break
            samples[start + n] += (
                0.22 * _envelope(n, length, release=0.4) * _wave_sample("sine", freq * n / SAMPLE_RATE)
            )

    return b"".join(
        struct.pack("<h", int(32767 * max(-1.0, min(1.0, s)))) for s in samples
    )


def render_blip(frequency: float, duration: float, shape: str = "square") -> bytes:
    """Synthesise a short sound effect.

    Parameters
    ----------
    frequency : float
        Pitch in Hz.
    duration : float
        Length in seconds.
    shape : str, optional
        Waveform name.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    total = int(SAMPLE_RATE * duration)
    return b"".join(
        struct.pack(
            "<h",
            int(
                32767
                * 0.35
                * _envelope(n, total, attack=0.01, release=0.6)
                * _wave_sample(shape, frequency * n / SAMPLE_RATE)
            ),
        )
        for n in range(total)
    )


def write_wav(path: pathlib.Path, pcm: bytes) -> pathlib.Path:
    """Write PCM samples to a mono 16-bit WAV file.

    Parameters
    ----------
    path : pathlib.Path
        Destination.
    pcm : bytes
        Little-endian signed 16-bit samples.

    Returns
    -------
    pathlib.Path
        The path written.
    """
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    return path


class Audio:
    """Music contexts and sound effects for one game.

    Audio is optional at runtime: if Qt's multimedia module is unavailable the
    mixer degrades to a silent no-op rather than raising, so a headless test or
    a stripped install still runs the game.

    Parameters
    ----------
    pack : chisurf.gui.chigame.assets.AssetPack
        Supplies the track data.
    enabled : bool, optional
        Set ``False`` to synthesise nothing at all.
    """

    def __init__(self, pack, enabled: bool = True) -> None:
        self.pack = pack
        self.context: str | None = None
        self._dir = pathlib.Path(tempfile.mkdtemp(prefix="chigame-audio-"))
        self._effects: dict[str, object] = {}
        self._music: object | None = None
        self._sound_cls = None
        self.enabled = False
        if not enabled:
            return
        try:  # pragma: no cover - depends on the Qt build
            from qtpy.QtMultimedia import QSoundEffect

            self._sound_cls = QSoundEffect
            self.enabled = True
        except Exception:
            self.enabled = False

    def _load(self, key: str, pcm: bytes, loop: bool):
        """Materialise PCM as a playable, cached effect.

        Parameters
        ----------
        key : str
            Cache key.
        pcm : bytes
            Sample data.
        loop : bool
            Whether playback repeats.

        Returns
        -------
        object or None
            A ``QSoundEffect``, or ``None`` when audio is disabled.
        """
        if not self.enabled:
            return None
        if key in self._effects:
            return self._effects[key]
        from qtpy.QtCore import QUrl

        path = write_wav(self._dir / f"{key}.wav", pcm)
        effect = self._sound_cls()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        if loop:
            effect.setLoopCount(self._sound_cls.Infinite)
        self._effects[key] = effect
        return effect

    def set_context(self, context: str) -> None:
        """Switch the music to a context.

        Parameters
        ----------
        context : str
            One of :data:`CONTEXTS`. Setting the context already playing is a
            no-op, so a game may call this every frame.
        """
        if context == self.context:
            return
        self.context = context
        if not self.enabled:
            return
        track = self.pack.music_track(context)
        if self._music is not None:
            self._music.stop()
            self._music = None
        if track is None:
            return
        key = "music-" + hashlib.sha256(
            json.dumps(track, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        effect = self._load(key, render_track(track), bool(track.get("loop", True)))
        if effect is not None:
            effect.play()
            self._music = effect

    def sfx(self, name: str, frequency: float = 660.0, duration: float = 0.08) -> None:
        """Play a short sound effect.

        Parameters
        ----------
        name : str
            Cache key; the same name reuses the same synthesised sample.
        frequency : float, optional
            Pitch in Hz.
        duration : float, optional
            Length in seconds.
        """
        effect = self._load(f"sfx-{name}", render_blip(frequency, duration), loop=False)
        if effect is not None:
            effect.play()

    def stop(self) -> None:
        """Stop music and release the playing effect."""
        if self._music is not None:
            self._music.stop()
            self._music = None
        self.context = None
