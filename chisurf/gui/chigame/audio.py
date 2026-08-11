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

import functools
import hashlib
import json
import math
import pathlib
import tempfile
import wave
import zipfile

import numpy as np

#: Sample rate. 44.1 kHz because the old 22.05 kHz put the third harmonic of a
#: lead note within reach of Nyquist, and a square wave folded back over itself
#: is most of why the music sounded like a modem.
SAMPLE_RATE = 44100

#: Musical contexts a game may be in.
CONTEXTS = ("overworld", "town", "battle", "underworld", "victory")

#: Where the shipped recorded audio lives: two zips of IMA ADPCM clips, one of
#: music and one of sound effects. Archives rather than 517 loose files, which
#: would be 517 git objects for no gain; `zipfile` reads a named entry out of
#: one in microseconds.
ASSET_DIR = pathlib.Path(__file__).resolve().parent / "audio_assets"

#: Where module files live, if any are installed. A tracker module is the one
#: audio format small enough to sit in a source tree -- a few hundred kB for a
#: whole song -- so a pack can be dropped in here and picked up by name.
MUSIC_DIR = pathlib.Path(__file__).resolve().parent / "music"

#: A note may be a bare semitone, a ``[semitone, eighths]`` pair, or ``None``
#: for a rest. Held notes and rests are the whole difference between a phrase
#: and a metronome playing scales.
REST = None

#: Fraction of each note left silent at its end, so consecutive notes at the
#: same pitch articulate instead of merging into one long tone.
DETACHE = 0.10


@functools.lru_cache(maxsize=4)
def archive(name: str):
    """Open one of the shipped clip archives.

    Parameters
    ----------
    name : str
        ``music`` or ``sfx``.

    Returns
    -------
    zipfile.ZipFile or None
        ``None`` when the archive is not installed, which is not an error: the
        synthesiser covers everything the archives would have.
    """
    path = ASSET_DIR / f"{name}.zip"
    if not path.is_file():
        return None
    try:
        return zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return None


def clip_names(name: str) -> tuple[str, ...]:
    """Everything in one archive.

    Parameters
    ----------
    name : str
        ``music`` or ``sfx``.

    Returns
    -------
    tuple of str
        Clip names without their extension, sorted. Empty when absent.
    """
    handle = archive(name)
    if handle is None:
        return ()
    return tuple(sorted(
        entry[:-4] for entry in handle.namelist() if entry.endswith(".snd")
    ))


@functools.lru_cache(maxsize=64)
def clip(name: str, which: str = "sfx"):
    """Decode one shipped clip.

    Parameters
    ----------
    name : str
        Clip name, without extension.
    which : str, optional
        ``music`` or ``sfx``.

    Returns
    -------
    tuple or None
        ``(pcm, rate)``, or ``None`` when there is no such clip.
    """
    handle = archive(which)
    if handle is None:
        return None
    from . import adpcm

    try:
        raw = handle.read(f"{name}.snd")
    except KeyError:
        return None
    try:
        return adpcm.to_pcm(raw), adpcm.rate_of(raw)
    except adpcm.ClipError:
        return None


def _harmonics(shape: str, freq: float) -> list[tuple[int, float]]:
    """Which partials make up a waveform, band-limited to this pitch.

    Additive synthesis rather than a naive edge: a hard square or saw has
    energy far above Nyquist, and at 44.1 kHz that folds back down into the
    audible band as a metallic buzz that no amount of composing fixes.

    Parameters
    ----------
    shape : {'sine', 'triangle', 'square', 'saw', 'pulse'}
        Waveform name. An unknown name falls back to a sine, because silence
        would be a harder bug to notice than a wrong timbre.
    freq : float
        Fundamental in Hz, which decides how many partials fit.

    Returns
    -------
    list of tuple
        ``(harmonic number, amplitude)``, fundamental first.
    """
    limit = 0.45 * SAMPLE_RATE
    parts: list[tuple[int, float]] = []
    if shape == "sine":
        return [(1, 1.0)]
    if shape == "triangle":
        for index in range(0, 7):
            k = 2 * index + 1
            if k * freq >= limit:
                break
            parts.append((k, (-1.0) ** index * 8.0 / (math.pi ** 2) / (k * k)))
        return parts
    if shape in ("square", "pulse"):
        span = 9 if shape == "square" else 7
        for index in range(0, span):
            k = 2 * index + 1
            if k * freq >= limit:
                break
            parts.append((k, 4.0 / math.pi / k))
        return parts
    if shape == "saw":
        for k in range(1, 13):
            if k * freq >= limit:
                break
            parts.append((k, 2.0 / math.pi / k * (-1.0) ** (k + 1)))
        return parts
    return [(1, 1.0)]


def _tone(shape: str, freq: float, count: int, vibrato: float = 0.0,
          detune: float = 0.0) -> np.ndarray:
    """One note's raw waveform.

    Parameters
    ----------
    shape : str
        Waveform name.
    freq : float
        Pitch in Hz.
    count : int
        Length in samples.
    vibrato : float, optional
        Depth as a fraction of the pitch. A lead with no vibrato at all is the
        other half of why a synthesised tune sounds mechanical.
    detune : float, optional
        A second oscillator this many cents away, mixed in. Two oscillators
        beating slowly against each other is what makes a pad sound wide.

    Returns
    -------
    numpy.ndarray
        Samples in roughly -1..1.
    """
    if count <= 0:
        return np.zeros(0, dtype=np.float32)
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    sweep = freq * np.ones(count)
    if vibrato:
        # Rising in slowly, the way a player leans on a held note rather than
        # wobbling from the attack.
        depth = vibrato * np.minimum(time / 0.25, 1.0)
        sweep = sweep * (1.0 + depth * np.sin(2.0 * math.pi * 5.2 * time))
    phase = np.cumsum(sweep) / SAMPLE_RATE

    out = np.zeros(count)
    for number, amplitude in _harmonics(shape, freq):
        out += amplitude * np.sin(2.0 * math.pi * number * phase)
    if detune:
        second = np.zeros(count)
        ratio = 2.0 ** (detune / 1200.0)
        for number, amplitude in _harmonics(shape, freq * ratio):
            second += amplitude * np.sin(2.0 * math.pi * number * phase * ratio)
        out = 0.6 * out + 0.4 * second
    return out


def _adsr(count: int, attack: float = 0.010, decay: float = 0.10,
          sustain: float = 0.70, release: float = 0.14) -> np.ndarray:
    """Amplitude envelope for one note.

    Parameters
    ----------
    count : int
        Length in samples.
    attack, decay, release : float, optional
        Seconds.
    sustain : float, optional
        Level held after the decay, in 0..1.

    Returns
    -------
    numpy.ndarray
        Gain in 0..1, always starting and ending at zero so nothing clicks.
    """
    if count <= 0:
        return np.zeros(0)
    env = np.full(count, sustain)
    rise = min(int(attack * SAMPLE_RATE), count)
    if rise:
        env[:rise] = np.linspace(0.0, 1.0, rise)
    fall = min(int(decay * SAMPLE_RATE), count - rise)
    if fall > 0:
        env[rise:rise + fall] = np.linspace(1.0, sustain, fall)
    tail = min(int(release * SAMPLE_RATE), count)
    if tail > 0:
        env[count - tail:] *= np.linspace(1.0, 0.0, tail) ** 1.5
    return env


def _drum(kind: str) -> np.ndarray:
    """One percussion hit.

    Parameters
    ----------
    kind : {'k', 's', 'h', 'o'}
        Kick, snare, closed hat, open hat.

    Returns
    -------
    numpy.ndarray
        Samples. Empty for anything else, so a pattern may use ``-`` freely.
    """
    rng = np.random.default_rng(abs(hash(kind)) % (2 ** 31))
    if kind == "k":
        count = int(0.16 * SAMPLE_RATE)
        time = np.arange(count) / SAMPLE_RATE
        # A pitch that falls fast is what a kick drum *is*.
        sweep = 118.0 * np.exp(-time * 34.0) + 44.0
        phase = np.cumsum(sweep) / SAMPLE_RATE
        return np.sin(2.0 * math.pi * phase) * np.exp(-time * 17.0)
    if kind == "s":
        count = int(0.14 * SAMPLE_RATE)
        time = np.arange(count) / SAMPLE_RATE
        noise = rng.standard_normal(count)
        noise -= np.convolve(noise, np.ones(9) / 9.0, mode="same")
        body = np.sin(2.0 * math.pi * 195.0 * time) * 0.35
        return (noise * 0.8 + body) * np.exp(-time * 26.0)
    if kind in ("h", "o"):
        length = 0.035 if kind == "h" else 0.16
        count = int(length * SAMPLE_RATE)
        time = np.arange(count) / SAMPLE_RATE
        noise = rng.standard_normal(count)
        noise -= np.convolve(noise, np.ones(5) / 5.0, mode="same")
        return noise * np.exp(-time * (95.0 if kind == "h" else 22.0)) * 0.5
    return np.zeros(0)


def _lowpass(signal: np.ndarray, tone: float) -> np.ndarray:
    """Take the edge off the mix.

    Parameters
    ----------
    signal : numpy.ndarray
        The mix.
    tone : float
        0 for dark, 1 for untouched.

    Returns
    -------
    numpy.ndarray
        Filtered, same length.
    """
    if tone >= 0.99 or signal.size == 0:
        return signal
    width = max(2, int(round(2 + (1.0 - tone) * 14)))
    window = np.hanning(width + 2)[1:-1]
    window /= window.sum()
    return np.convolve(signal, window, mode="same")


def _notes(entries) -> list[tuple[float | None, float]]:
    """Normalise a voice's note list.

    Parameters
    ----------
    entries : iterable
        Each entry a semitone offset, a ``[semitone, eighths]`` pair, or
        ``None`` for a rest.

    Returns
    -------
    list of tuple
        ``(semitone or None, length in eighths)``.
    """
    parsed: list[tuple[float | None, float]] = []
    for entry in entries or ():
        if entry is None:
            parsed.append((None, 1.0))
        elif isinstance(entry, (list, tuple)):
            parsed.append((None if entry[0] is None else float(entry[0]),
                           float(entry[1])))
        else:
            parsed.append((float(entry), 1.0))
    return parsed


def _render_voice(voice: dict, root: float, eighth: int, total: int) -> np.ndarray:
    """Lay one line of the track down onto a buffer.

    Parameters
    ----------
    voice : dict
        Keys ``notes``, ``wave``, ``gain``, ``octave``, ``vibrato``,
        ``detune``, ``sustain``.
    root : float
        Root pitch in Hz.
    eighth : int
        Samples per eighth note.
    total : int
        Buffer length.

    Returns
    -------
    numpy.ndarray
        The voice, at its own gain.
    """
    out = np.zeros(total)
    shape = str(voice.get("wave", "triangle"))
    gain = float(voice.get("gain", 0.3))
    octave = float(voice.get("octave", 0)) * 12.0
    vibrato = float(voice.get("vibrato", 0.0))
    detune = float(voice.get("detune", 0.0))
    sustain = float(voice.get("sustain", 0.70))

    cursor = 0
    for semitone, length in _notes(voice.get("notes")):
        span = int(round(length * eighth))
        if semitone is not None and span > 0 and cursor < total:
            sounding = max(1, int(span * (1.0 - DETACHE)))
            count = min(sounding, total - cursor)
            freq = root * (2.0 ** ((semitone + octave) / 12.0))
            wave_ = _tone(shape, freq, count, vibrato=vibrato, detune=detune)
            out[cursor:cursor + count] += gain * wave_ * _adsr(count, sustain=sustain)
        cursor += span
    return out


def _render_drums(pattern: str, eighth: int, total: int, gain: float) -> np.ndarray:
    """Lay a percussion pattern down onto a buffer.

    Parameters
    ----------
    pattern : str
        One character per eighth: ``k`` kick, ``s`` snare, ``h`` hat, ``o``
        open hat, anything else a rest. Repeats to fill the track.
    eighth : int
        Samples per eighth note.
    total : int
        Buffer length.
    gain : float
        Level.

    Returns
    -------
    numpy.ndarray
        The kit.
    """
    out = np.zeros(total)
    if not pattern or eighth <= 0:
        return out
    steps = max(1, total // eighth)
    for step in range(steps):
        hit = _drum(pattern[step % len(pattern)])
        if not hit.size:
            continue
        at = step * eighth
        count = min(hit.size, total - at)
        if count > 0:
            out[at:at + count] += gain * hit[:count]
    return out


def render_track(track: dict) -> bytes:
    """Synthesise a track's note data into 16-bit mono PCM.

    Parameters
    ----------
    track : dict
        ``root`` (Hz) and ``tempo`` (BPM of quarter notes), plus any of
        ``melody``, ``harmony``, ``bass`` and ``pad`` as voice dicts or bare
        note lists, and ``drums`` as a pattern string. ``tone`` darkens the
        mix; ``swing`` is accepted and ignored for now.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    recorded = track.get("clip")
    if recorded:
        found = clip(str(recorded), "music")
        if found is not None:
            return found[0]

    module = track.get("module")
    if module:
        # A track may be a tracker module rather than note data. The player is
        # in-tree (:mod:`.tracker`) and renders to exactly this PCM, so nothing
        # downstream knows the difference.
        from . import tracker

        path = pathlib.Path(module)
        if not path.is_absolute():
            path = MUSIC_DIR / path
        if path.is_file():
            try:
                return tracker.render_to_pcm(path, SAMPLE_RATE)
            except tracker.ModuleError:
                # A module we cannot read falls through to whatever note data
                # the track also carries, which is silence if it carries none.
                pass

    root = float(track.get("root", 261.63))
    tempo = float(track.get("tempo", 100))
    eighth = max(1, int(SAMPLE_RATE * 30.0 / max(tempo, 1.0)))

    voices: list[dict] = []
    for name, default in (("pad", {"wave": "sine", "gain": 0.10, "octave": -1}),
                          ("bass", {"wave": "triangle", "gain": 0.26, "octave": -1}),
                          ("harmony", {"wave": "triangle", "gain": 0.12}),
                          ("melody", {"wave": "triangle", "gain": 0.30})):
        entry = track.get(name)
        if entry is None:
            continue
        voice = dict(default)
        if isinstance(entry, dict):
            voice.update(entry)
        else:
            voice["notes"] = entry
        # A track may still spell a voice's wave at the top level, which is how
        # the older, single-timbre tracks were written.
        voice.setdefault("wave", track.get("wave", "triangle"))
        voices.append(voice)

    length = 0
    for voice in voices:
        length = max(length, sum(span for _, span in _notes(voice.get("notes"))))
    drums = str(track.get("drums", ""))
    if drums:
        length = max(length, len(drums))
    total = int(round(max(length, 1) * eighth))

    mix = np.zeros(total)
    for voice in voices:
        mix += _render_voice(voice, root, eighth, total)
    if drums:
        mix += _render_drums(drums, eighth, total, float(track.get("drum_gain", 0.30)))

    mix = _lowpass(mix, float(track.get("tone", 0.55)))
    # Soft clip rather than hard: a mix that momentarily exceeds full scale
    # should compress, not tear.
    mix = np.tanh(1.5 * mix) / math.tanh(1.5)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0:
        mix *= 0.82 / peak
    # A short fade at both ends, so a looping track does not click on the seam.
    edge = min(int(0.008 * SAMPLE_RATE), total // 2)
    if edge > 0:
        mix[:edge] *= np.linspace(0.0, 1.0, edge)
        mix[-edge:] *= np.linspace(1.0, 0.0, edge)

    return (np.clip(mix, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def render_blip(frequency: float, duration: float, shape: str = "triangle",
                bend: float = 0.0) -> bytes:
    """Synthesise a short sound effect.

    Parameters
    ----------
    frequency : float
        Pitch in Hz.
    duration : float
        Length in seconds.
    shape : str, optional
        Waveform name.
    bend : float, optional
        Semitones to slide over the effect's life. A blip that bends is an
        event; a flat one is a beep.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    count = max(1, int(SAMPLE_RATE * duration))
    time = np.arange(count) / SAMPLE_RATE
    sweep = frequency * (2.0 ** (bend * time / max(duration, 1e-6) / 12.0))
    phase = np.cumsum(sweep) / SAMPLE_RATE
    wave_ = np.zeros(count)
    for number, amplitude in _harmonics(shape, float(np.max(sweep))):
        wave_ += amplitude * np.sin(2.0 * math.pi * number * phase)
    envelope = _adsr(count, attack=0.004, decay=duration * 0.35,
                     sustain=0.35, release=duration * 0.5)
    out = 0.34 * wave_ * envelope
    return (np.clip(out, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def write_wav(path: pathlib.Path, pcm: bytes, rate: int = SAMPLE_RATE) -> pathlib.Path:
    """Write PCM samples to a mono 16-bit WAV file.

    Parameters
    ----------
    path : pathlib.Path
        Destination.
    pcm : bytes
        Little-endian signed 16-bit samples.
    rate : int, optional
        Sample rate. The shipped clips are stored at half the synthesiser's
        rate, and a WAV that lies about its rate plays at the wrong pitch.

    Returns
    -------
    pathlib.Path
        The path written.
    """
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
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
        self._suspended = False
        self._resume_context: str | None = None
        self.enabled = False
        if not enabled:
            return
        try:  # pragma: no cover - depends on the Qt build
            from qtpy.QtMultimedia import QSoundEffect

            self._sound_cls = QSoundEffect
            self.enabled = True
        except Exception:
            self.enabled = False

    def _load(self, key: str, pcm: bytes, loop: bool, rate: int = SAMPLE_RATE):
        """Materialise PCM as a playable, cached effect.

        Parameters
        ----------
        key : str
            Cache key.
        pcm : bytes
            Sample data.
        loop : bool
            Whether playback repeats.
        rate : int, optional
            Sample rate of ``pcm``.

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

        path = write_wav(self._dir / f"{key}.wav", pcm, rate)
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
        if self._suspended:
            # Remember where the game got to, so coming back to the window
            # starts the right piece rather than the one that was playing when
            # it was left.
            self._resume_context = context
            return
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
        # A track that names a shipped clip is stored at the clip's own rate,
        # not the synthesiser's; a WAV that lies about its rate plays at the
        # wrong pitch and at the wrong speed.
        rate = SAMPLE_RATE
        recorded = track.get("clip")
        if recorded:
            found = clip(str(recorded), "music")
            if found is not None:
                rate = found[1]
        effect = self._load(key, render_track(track), bool(track.get("loop", True)),
                            rate)
        if effect is not None:
            effect.play()
            self._music = effect

    def sfx(self, name: str, frequency: float = 660.0, duration: float = 0.08,
            bend: float = 0.0) -> None:
        """Play a short sound effect.

        Parameters
        ----------
        name : str
            A clip in the shipped sound-effect pack -- see
            :func:`clip_names` -- or any other name, which is synthesised from
            the parameters below and cached under it.
        frequency : float, optional
            Pitch in Hz.
        duration : float, optional
            Length in seconds.
        bend : float, optional
            Semitones to slide over the effect's life.
        """
        if self._suspended:
            return
        # The pack maps a game's event name onto a recording; the synthesised
        # blip is what a game gets when it asks for something the pack has no
        # entry for, which is why every call site still passes a frequency.
        chosen = name
        if hasattr(self.pack, "sound_clip"):
            chosen = self.pack.sound_clip(name) or name
        found = clip(chosen, "sfx")
        if found is not None:
            effect = self._load(f"sfx-{name}", found[0], loop=False, rate=found[1])
        else:
            effect = self._load(f"sfx-{name}", render_blip(frequency, duration, bend=bend),
                                loop=False)
        if effect is not None:
            effect.play()

    def suspend(self) -> None:
        """Silence everything, remembering what was playing.

        A game in a window nobody is looking at must not still be audible --
        that is the single most annoying thing a background process can do.
        The context is kept so :meth:`resume` can put it back.
        """
        if self._suspended:
            return
        self._suspended = True
        self._resume_context = self.context
        if self._music is not None:
            self._music.stop()
            self._music = None
        self.context = None

    def resume(self) -> None:
        """Start again on whatever was playing when :meth:`suspend` was called."""
        if not self._suspended:
            return
        self._suspended = False
        context, self._resume_context = self._resume_context, None
        if context is not None:
            self.set_context(context)

    @property
    def suspended(self) -> bool:
        """Whether playback is currently held.

        Returns
        -------
        bool
            True while the window is not the one in front.
        """
        return self._suspended

    def stop(self) -> None:
        """Stop music and release the playing effect."""
        if self._music is not None:
            self._music.stop()
            self._music = None
        self.context = None
        self._resume_context = None
