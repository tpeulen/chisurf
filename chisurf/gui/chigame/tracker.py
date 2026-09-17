"""A ProTracker module player, in-tree and dependency-free.

A tracker module is the right shape for a soundtrack that has to live in a
source repository. It does not store audio: it stores a handful of short
instrument samples and a grid of *which note plays on which channel on which
row*, and the player builds the audio. A four-minute song is 50--300 kB, which
is the same order as the PNGs already in the tree, against tens of megabytes
for the same song rendered to OGG.

Nothing is added to the environment to read one. `libopenmpt` is the usual
answer and is not on conda-forge at all, so it would mean vendoring a C library
into a scientific package to play a tune -- and the format is old, small and
completely documented. This is a page of parsing and a page of mixing.

**What is supported**: the 31-instrument ProTracker MOD (`M.K.`, `M!K!`,
`4CHN`/`6CHN`/`8CHN`), which is the format the free-culture archives are
overwhelmingly in. Sample data is 8-bit signed PCM; pitch comes from Amiga
periods against the PAL clock; the effect column supports the commands that
change what you *hear* rather than what a tracker author sees:

===========  ==============================================================
Effect       What it does
===========  ==============================================================
``1`` ``2``  Portamento up / down
``3``        Tone portamento -- slide to the note
``4``        Vibrato
``9``        Start the sample partway in
``A``        Volume slide
``B``        Jump to another position in the order
``C``        Set volume
``D``        Break to the next pattern
``F``        Set speed (ticks per row) or tempo (BPM)
===========  ==============================================================

Anything else is parsed and ignored, which is the honest behaviour: an
unrecognised effect must not silence the channel or desynchronise the song.

Rendering is numpy and produces the same mono 16-bit PCM as the synthesiser in
:mod:`.audio`, so a module drops into the existing playback path with nothing
else to change.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numpy as np

#: Rows in every pattern. Fixed by the format.
ROWS = 64

#: Where pattern data starts, and how many instruments a modern MOD carries.
HEADER_BYTES = 1084
INSTRUMENTS = 31

#: The PAL Amiga clock. A period is a divisor of this, which is why tracker
#: pitch is expressed as a number that goes *down* as the note goes up.
PAL_CLOCK = 7093789.2

#: Ticks per row and beats per minute a module starts on, before any ``F``.
DEFAULT_SPEED = 6
DEFAULT_TEMPO = 125

#: Longest song this will render, in seconds. A malformed order table can
#: describe an endless song, and a player that allocates until it dies is worse
#: than one that stops.
MAX_SECONDS = 360.0

#: Signatures we know, and how many channels each means.
SIGNATURES: dict[bytes, int] = {
    b"M.K.": 4,
    b"M!K!": 4,
    b"FLT4": 4,
    b"4CHN": 4,
    b"6CHN": 6,
    b"8CHN": 8,
    b"CD81": 8,
    b"OKTA": 8,
}

#: The vibrato waveform, as ProTracker's own table: a sine over 64 steps.
_VIBRATO = np.sin(np.arange(64) * np.pi / 32.0) * 255.0


class ModuleError(ValueError):
    """The bytes handed over are not a module this player understands."""


@dataclasses.dataclass
class Instrument:
    """One sampled instrument.

    Attributes
    ----------
    name : str
        As stored, for the credits a module usually hides in its sample names.
    data : numpy.ndarray
        Samples in -1..1.
    finetune : int
        -8..7, in eighths of a semitone.
    volume : int
        0..64.
    loop_start, loop_length : int
        In samples. A loop length of 2 or less means the sample does not loop.
    """

    name: str
    data: np.ndarray
    finetune: int
    volume: int
    loop_start: int
    loop_length: int

    @property
    def loops(self) -> bool:
        """Whether this instrument sustains.

        Returns
        -------
        bool
            True when the loop is long enough to be a loop rather than the
            format's way of spelling "no loop".
        """
        return self.loop_length > 2


@dataclasses.dataclass
class Module:
    """A parsed module.

    Attributes
    ----------
    title : str
        The song's name.
    channels : int
        How many voices play at once.
    instruments : list of Instrument
        Index 0 is the "no instrument" slot and is never played.
    order : list of int
        Which pattern plays at each position.
    patterns : numpy.ndarray
        ``(count, ROWS, channels, 4)`` of the raw note words, as
        ``(period, instrument, effect, parameter)``.
    """

    title: str
    channels: int
    instruments: list[Instrument]
    order: list[int]
    patterns: np.ndarray

    @property
    def credits(self) -> str:
        """What the module says about itself.

        Tracker authors traditionally sign their work in the sample names, so
        this is where a module's attribution actually lives.

        Returns
        -------
        str
            Title and any non-empty sample names, newline separated.
        """
        lines = [self.title.strip()]
        lines += [one.name.strip() for one in self.instruments if one.name.strip()]
        return "\n".join(line for line in lines if line)


def _text(raw: bytes) -> str:
    """Decode a fixed-width field the way a tracker wrote it.

    Parameters
    ----------
    raw : bytes
        The field.

    Returns
    -------
    str
        Latin-1 up to the first NUL, stripped.
    """
    return raw.split(b"\0")[0].decode("latin-1", "replace").strip()


def parse(raw: bytes) -> Module:
    """Read a ProTracker module out of bytes.

    Parameters
    ----------
    raw : bytes
        File contents.

    Returns
    -------
    Module
        The parsed song.

    Raises
    ------
    ModuleError
        When the signature is absent or the file is truncated.
    """
    if len(raw) < HEADER_BYTES:
        raise ModuleError("too short to be a module")
    signature = raw[1080:1084]
    channels = SIGNATURES.get(signature)
    if channels is None:
        raise ModuleError(f"unknown module signature {signature!r}")

    instruments: list[Instrument] = [Instrument("", np.zeros(0, np.float32), 0, 0, 0, 0)]
    lengths: list[tuple[int, int, int]] = []
    for index in range(INSTRUMENTS):
        at = 20 + index * 30
        name = _text(raw[at : at + 22])
        length = int.from_bytes(raw[at + 22 : at + 24], "big") * 2
        finetune = raw[at + 24] & 0x0F
        finetune = finetune - 16 if finetune > 7 else finetune
        volume = min(raw[at + 25], 64)
        loop_start = int.from_bytes(raw[at + 26 : at + 28], "big") * 2
        loop_length = int.from_bytes(raw[at + 28 : at + 30], "big") * 2
        instruments.append(
            Instrument(name, np.zeros(0, np.float32), finetune, volume, loop_start, loop_length)
        )
        lengths.append((length, loop_start, loop_length))

    song_length = max(1, min(raw[950], 128))
    order = [raw[952 + index] for index in range(song_length)]
    count = max(order) + 1 if order else 1

    stride = ROWS * channels * 4
    needed = HEADER_BYTES + count * stride
    if len(raw) < needed:
        raise ModuleError("pattern data is truncated")
    block = np.frombuffer(raw[HEADER_BYTES:needed], dtype=np.uint8)
    block = block.reshape(count, ROWS, channels, 4).astype(np.int32)

    patterns = np.zeros((count, ROWS, channels, 4), np.int32)
    patterns[..., 0] = ((block[..., 0] & 0x0F) << 8) | block[..., 1]
    patterns[..., 1] = (block[..., 0] & 0xF0) | (block[..., 2] >> 4)
    patterns[..., 2] = block[..., 2] & 0x0F
    patterns[..., 3] = block[..., 3]

    cursor = needed
    for index, (length, loop_start, loop_length) in enumerate(lengths, start=1):
        chunk = raw[cursor : cursor + length]
        cursor += length
        data = np.frombuffer(chunk, dtype=np.int8).astype(np.float32) / 128.0
        instrument = instruments[index]
        # A loop that runs off the end of the sample is common in the wild and
        # is not an error; it is clamped rather than refused.
        end = min(loop_start + loop_length, data.size)
        instruments[index] = dataclasses.replace(
            instrument,
            data=data,
            loop_start=min(loop_start, data.size),
            loop_length=max(0, end - min(loop_start, data.size)),
        )

    return Module(
        title=_text(raw[:20]),
        channels=channels,
        instruments=instruments,
        order=order,
        patterns=patterns,
    )


def load(path) -> Module:
    """Read a module from disk.

    Parameters
    ----------
    path : path-like
        The file.

    Returns
    -------
    Module
        The parsed song.
    """
    return parse(pathlib.Path(path).read_bytes())


@dataclasses.dataclass
class _Voice:
    """One channel's running state while the song plays."""

    instrument: int = 0
    position: float = 0.0
    period: float = 0.0
    target: float = 0.0
    volume: int = 0
    slide: int = 0
    vibrato_speed: int = 0
    vibrato_depth: int = 0
    vibrato_phase: int = 0
    playing: bool = False


def _frequency(period: float, finetune: int) -> float:
    """Sampling rate an instrument runs at for a period.

    Parameters
    ----------
    period : float
        Amiga period. Larger is lower.
    finetune : int
        -8..7, in eighths of a semitone.

    Returns
    -------
    float
        Instrument samples per second, or 0 for a period of 0.
    """
    if period <= 0:
        return 0.0
    tuned = period * (2.0 ** (-finetune / 96.0))
    return PAL_CLOCK / (tuned * 2.0)


def render(module: Module, rate: int, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Play a module and return the audio.

    Parameters
    ----------
    module : Module
        The song.
    rate : int
        Output sample rate.
    max_seconds : float, optional
        Give up after this much, so a song that jumps to itself forever still
        returns.

    Returns
    -------
    numpy.ndarray
        Mono samples in roughly -1..1.
    """
    voices = [_Voice() for _ in range(module.channels)]
    speed = DEFAULT_SPEED
    tempo = DEFAULT_TEMPO
    blocks: list[np.ndarray] = []
    produced = 0
    limit = int(max_seconds * rate)

    position = 0
    row = 0
    seen: set[tuple[int, int]] = set()
    while position < len(module.order) and produced < limit:
        if (position, row) in seen:
            break  # back where we have been: the song has looped
        seen.add((position, row))
        pattern = module.patterns[module.order[position]]

        jump_to: tuple[str, int] | None = None
        for tick in range(speed):
            if tick == 0:
                jump_to = _start_row(module, pattern[row], voices)
                # Speed and tempo are read off the row, after the notes.
                speed, tempo = _timing(pattern[row], speed, tempo)
            else:
                _tick(pattern[row], voices)
            count = max(1, int(rate * 2.5 / max(tempo, 1)))
            blocks.append(_mix(module, voices, count, rate))
            produced += count
            if produced >= limit:
                break

        if jump_to is not None:
            kind, value = jump_to
            if kind == "jump":
                position, row = value, 0
            else:
                # A break lands on the *next* position, at the given row.
                position, row = position + 1, value
            continue
        row += 1
        if row >= ROWS:
            row = 0
            position += 1

    if not blocks:
        return np.zeros(0, np.float32)
    return np.concatenate(blocks)


def _timing(row: np.ndarray, speed: int, tempo: int) -> tuple[int, int]:
    """Apply any ``F`` on this row.

    Parameters
    ----------
    row : numpy.ndarray
        ``(channels, 4)`` of note words.
    speed, tempo : int
        Current values.

    Returns
    -------
    tuple of int
        ``(speed, tempo)``.
    """
    for _, _, effect, param in row:
        if effect == 0x0F and param:
            if param <= 0x1F:
                speed = int(param)
            else:
                tempo = int(param)
    return speed, tempo


def _start_row(module: Module, row: np.ndarray, voices: list[_Voice]):
    """Take the notes on a row, on tick zero.

    Parameters
    ----------
    module : Module
        For the instrument table.
    row : numpy.ndarray
        ``(channels, 4)``.
    voices : list of _Voice
        Mutated in place.

    Returns
    -------
    tuple or None
        ``("jump", position)`` from a ``B``, ``("break", row)`` from a ``D``,
        else ``None``. Kept as a pair rather than a bare number because the two
        mean different things and conflating them is the classic way to make a
        module play its patterns in the wrong order.
    """
    jump: tuple[str, int] | None = None
    for voice, (period, instrument, effect, param) in zip(voices, row):
        if instrument:
            voice.instrument = int(instrument)
            if int(instrument) < len(module.instruments):
                voice.volume = module.instruments[int(instrument)].volume
        if period:
            if effect == 0x03:
                # Tone portamento does not restart the sample; it aims at the
                # new note and slides there.
                voice.target = float(period)
            else:
                voice.period = float(period)
                voice.target = float(period)
                voice.position = 0.0
                voice.playing = True
                voice.vibrato_phase = 0
        voice.slide = 0
        if effect == 0x0C:
            voice.volume = min(int(param), 64)
        elif effect == 0x09 and voice.instrument:
            voice.position = float(int(param) * 256)
        elif effect == 0x04:
            if param >> 4:
                voice.vibrato_speed = int(param) >> 4
            if param & 0x0F:
                voice.vibrato_depth = int(param) & 0x0F
        elif effect == 0x0B:
            jump = ("jump", int(param))
        elif effect == 0x0D:
            # The parameter is decimal-coded, which catches everybody once.
            target = (int(param) >> 4) * 10 + (int(param) & 0x0F)
            jump = ("break", min(target, ROWS - 1))
    return jump


def _tick(row: np.ndarray, voices: list[_Voice]) -> None:
    """Apply the per-tick half of the effects.

    Parameters
    ----------
    row : numpy.ndarray
        ``(channels, 4)``.
    voices : list of _Voice
        Mutated in place.
    """
    for voice, (_, _, effect, param) in zip(voices, row):
        param = int(param)
        if effect == 0x01:
            voice.period = max(113.0, voice.period - param)
        elif effect == 0x02:
            voice.period = min(856.0, voice.period + param)
        elif effect == 0x03 and voice.target:
            step = param or 1
            if voice.period < voice.target:
                voice.period = min(voice.period + step, voice.target)
            elif voice.period > voice.target:
                voice.period = max(voice.period - step, voice.target)
        elif effect == 0x04:
            voice.vibrato_phase = (voice.vibrato_phase + voice.vibrato_speed) % 64
        elif effect == 0x0A:
            if param >> 4:
                voice.volume = min(64, voice.volume + (param >> 4))
            else:
                voice.volume = max(0, voice.volume - (param & 0x0F))


def _mix(module: Module, voices: list[_Voice], count: int, rate: int) -> np.ndarray:
    """Render one tick of audio from the running voices.

    Parameters
    ----------
    module : Module
        For the instrument data.
    voices : list of _Voice
        Advanced in place.
    count : int
        Samples to produce.
    rate : int
        Output sample rate.

    Returns
    -------
    numpy.ndarray
        ``count`` mono samples.
    """
    out = np.zeros(count, np.float32)
    for voice in voices:
        if not voice.playing or not voice.instrument:
            continue
        if voice.instrument >= len(module.instruments):
            continue
        instrument = module.instruments[voice.instrument]
        if instrument.data.size == 0 or voice.volume <= 0:
            continue

        period = voice.period
        if voice.vibrato_depth:
            period += (_VIBRATO[voice.vibrato_phase] * voice.vibrato_depth) / 128.0
        frequency = _frequency(period, instrument.finetune)
        if frequency <= 0:
            continue

        step = frequency / rate
        index = voice.position + np.arange(count, dtype=np.float64) * step
        size = instrument.data.size
        if instrument.loops:
            start, length = instrument.loop_start, instrument.loop_length
            over = index >= start + length
            index[over] = start + np.mod(index[over] - start, length)
            voice.position = float(index[-1] + step)
            if voice.position >= start + length:
                voice.position = start + ((voice.position - start) % length)
        else:
            done = index >= size - 1
            index = np.clip(index, 0, max(size - 2, 0))
            voice.position = float(voice.position + count * step)
            if voice.position >= size - 1:
                voice.playing = False

        # Linear interpolation: point sampling a 8 kHz instrument up to 44.1
        # is where a module player starts sounding like a broken radio.
        low = index.astype(np.int64)
        frac = (index - low).astype(np.float32)
        low = np.clip(low, 0, max(size - 2, 0))
        sample = instrument.data[low] * (1.0 - frac) + instrument.data[low + 1] * frac
        if not instrument.loops:
            sample = np.where(done, 0.0, sample)
        out += sample * (voice.volume / 64.0)
    return out


def render_to_pcm(path, rate: int, gain: float = 0.62) -> bytes:
    """Render a module file to the 16-bit mono PCM the mixer plays.

    Parameters
    ----------
    path : path-like
        The module.
    rate : int
        Output sample rate.
    gain : float, optional
        Headroom. Four channels summed reach well past full scale on their own.

    Returns
    -------
    bytes
        Little-endian signed 16-bit samples.
    """
    audio = render(load(path), rate)
    if audio.size:
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio = audio * (gain / peak)
        edge = min(int(0.006 * rate), audio.size // 2)
        if edge > 0:
            audio[:edge] *= np.linspace(0.0, 1.0, edge)
            audio[-edge:] *= np.linspace(1.0, 0.0, edge)
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
