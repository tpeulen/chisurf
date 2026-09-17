"""The in-tree ProTracker player: small files in, the right audio out."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from chisurf.gui.chigame import audio, tracker

#: Output rate the mixer plays at.
RATE = audio.SAMPLE_RATE

#: A ProTracker period. 428 is middle C on the Amiga tables.
C2 = 428


def build(
    rows: dict,
    *,
    samples: int = 64,
    loop: bool = True,
    order: tuple[int, ...] = (0,),
    volume: int = 64,
    finetune: int = 0,
) -> bytes:
    """Write a minimal but real 4-channel MOD.

    Building one here rather than committing a binary keeps the test honest
    about *what* it is asserting -- every number in the file is visible in this
    function -- and means the player is covered with no third-party asset in
    the tree at all.

    Parameters
    ----------
    rows : dict
        ``(pattern, row, channel) -> (period, instrument, effect, param)``.
    samples : int, optional
        Length of the one instrument, a square wave.
    loop : bool, optional
        Whether that instrument sustains.
    order : tuple of int, optional
        The order table.
    volume : int, optional
        Instrument volume, 0..64.
    finetune : int, optional
        Instrument finetune, -8..7.

    Returns
    -------
    bytes
        A parseable module.
    """
    out = bytearray()
    out += b"TEST SONG".ljust(20, b"\0")
    for index in range(31):
        if index == 0:
            out += b"square".ljust(22, b"\0")
            out += struct.pack(">H", samples // 2)
            out += bytes([finetune & 0x0F, volume])
            out += struct.pack(">H", 0)
            out += struct.pack(">H", samples // 2 if loop else 1)
        else:
            out += b"".ljust(22, b"\0") + struct.pack(">H", 0) + bytes([0, 0])
            out += struct.pack(">H", 0) + struct.pack(">H", 1)
    out += bytes([len(order), 0])
    table = bytearray(128)
    for index, pattern in enumerate(order):
        table[index] = pattern
    out += table + b"M.K."

    for pattern in range(max(order) + 1):
        for row in range(tracker.ROWS):
            for channel in range(4):
                period, instrument, effect, param = rows.get((pattern, row, channel), (0, 0, 0, 0))
                out += bytes(
                    [
                        (instrument & 0xF0) | ((period >> 8) & 0x0F),
                        period & 0xFF,
                        ((instrument & 0x0F) << 4) | (effect & 0x0F),
                        param & 0xFF,
                    ]
                )
    wave = np.where(np.arange(samples) < samples // 2, 100, -100).astype(np.int8)
    return bytes(out) + wave.tobytes()


def _pitch(signal: np.ndarray) -> float:
    """Strongest frequency in a stretch of audio.

    Parameters
    ----------
    signal : numpy.ndarray
        Samples.

    Returns
    -------
    float
        Hz.
    """
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(signal.size)))
    return float(np.fft.rfftfreq(signal.size, 1.0 / RATE)[spectrum.argmax()])


def test_a_whole_song_is_smaller_than_a_screenshot():
    """The entire reason to have a tracker player at all."""
    raw = build({(0, row, 0): (C2, 1, 0, 0) for row in range(0, 64, 4)})
    assert len(raw) < 8_000, len(raw)
    seconds = tracker.render(tracker.parse(raw), RATE).size / RATE
    assert seconds > 5.0
    # The same audio as OGG would be hundreds of kB; as WAV, over a megabyte.
    assert len(raw) < seconds * 2_000


def test_the_header_is_read_the_way_the_format_defines_it():
    """Every field here is a place a MOD parser classically goes wrong."""
    module = tracker.parse(build({}, samples=128, volume=40, finetune=3))
    assert module.title == "TEST SONG"
    assert module.channels == 4
    assert module.order == [0]
    assert module.patterns.shape == (1, tracker.ROWS, 4, 4)

    instrument = module.instruments[1]
    assert instrument.name == "square"
    assert instrument.data.size == 128, "length is stored in *words*"
    assert instrument.volume == 40
    assert instrument.finetune == 3
    assert instrument.loops
    assert -1.0 <= instrument.data.min() and instrument.data.max() <= 1.0


def test_a_negative_finetune_is_read_as_negative():
    """It is a signed nibble, which is easy to read as 9..15."""
    module = tracker.parse(build({}, finetune=-3 & 0x0F))
    assert module.instruments[1].finetune == -3


def test_a_note_plays_at_the_pitch_its_period_says():
    """Amiga periods against the PAL clock, and nothing else."""
    for period in (C2, C2 // 2):
        raw = build({(0, 0, 0): (period, 1, 0, 0)})
        audio_ = tracker.render(tracker.parse(raw), RATE)
        expected = tracker.PAL_CLOCK / (period * 2) / 64.0
        assert abs(_pitch(audio_[: RATE // 2]) - expected) < expected * 0.05


def test_the_song_lasts_as_long_as_its_speed_and_tempo_say():
    """Six ticks a row at 125 BPM is the format's default, and it is exact."""
    raw = build({(0, 0, 0): (C2, 1, 0, 0)})
    seconds = tracker.render(tracker.parse(raw), RATE).size / RATE
    expected = tracker.ROWS * tracker.DEFAULT_SPEED * 2.5 / tracker.DEFAULT_TEMPO
    assert abs(seconds - expected) < 0.05, (seconds, expected)

    # F sets speed below 0x20 and tempo above it.
    faster = build({(0, 0, 0): (C2, 1, 0x0F, 3)})
    assert tracker.render(tracker.parse(faster), RATE).size < 0.6 * seconds * RATE


def test_a_non_looping_sample_stops_and_a_looping_one_does_not():
    """A one-shot that keeps sounding is the classic module-player artefact."""
    short = build({(0, 0, 0): (C2, 1, 0, 0)}, samples=32, loop=False)
    signal = tracker.render(tracker.parse(short), RATE)
    tail = np.abs(signal[int(0.5 * RATE) :]).mean()
    assert tail < 1e-4, "a one-shot has to actually stop"

    held = build({(0, 0, 0): (C2, 1, 0, 0)}, samples=32, loop=True)
    signal = tracker.render(tracker.parse(held), RATE)
    assert np.abs(signal[int(0.5 * RATE) :]).mean() > 0.05


def test_set_volume_and_volume_slide_are_heard():
    """Effect C and effect A, which is most of a module's dynamics."""
    loud = tracker.render(tracker.parse(build({(0, 0, 0): (C2, 1, 0x0C, 64)})), RATE)
    quiet = tracker.render(tracker.parse(build({(0, 0, 0): (C2, 1, 0x0C, 8)})), RATE)
    assert np.abs(quiet[: RATE // 4]).mean() < np.abs(loud[: RATE // 4]).mean() / 3

    faded = tracker.parse(
        build(
            {
                (0, 0, 0): (C2, 1, 0x0C, 64),
                **{(0, row, 0): (0, 0, 0x0A, 0x08) for row in range(1, 16)},
            }
        )
    )
    signal = tracker.render(faded, RATE)
    early = np.abs(signal[: RATE // 8]).mean()
    later = np.abs(signal[RATE // 2 : RATE // 2 + RATE // 8]).mean()
    assert later < early / 2, "a volume slide has to slide"


def test_portamento_bends_the_pitch():
    """Effects 1 and 2, which move the period rather than restart the note."""
    up = tracker.parse(
        build(
            {
                (0, 0, 0): (C2, 1, 0, 0),
                **{(0, row, 0): (0, 0, 0x01, 0x20) for row in range(1, 24)},
            }
        )
    )
    signal = tracker.render(up, RATE)
    first = _pitch(signal[: RATE // 8])
    later = _pitch(signal[RATE // 2 : RATE // 2 + RATE // 8])
    assert later > first * 1.2, (first, later)


def test_a_pattern_break_and_a_position_jump_go_where_they_say():
    """Effect D lands on the *next* position; effect B goes where it is told.

    Conflating the two is the classic way to make a module play its patterns in
    the wrong order, which is why the player keeps them as distinct kinds.
    """
    # Two positions; pattern 0 breaks out on row 0, so almost none of it plays.
    broken = build({(0, 0, 0): (C2, 1, 0x0D, 0)}, order=(0, 1))
    whole = build({(0, 0, 0): (C2, 1, 0, 0)}, order=(0, 1))
    assert (
        tracker.render(tracker.parse(broken), RATE).size
        < tracker.render(tracker.parse(whole), RATE).size / 1.8
    )

    # A jump backwards is a loop, and the player must notice and stop.
    looped = build({(0, 63, 0): (C2, 1, 0x0B, 0)}, order=(0,))
    signal = tracker.render(tracker.parse(looped), RATE, max_seconds=30.0)
    assert signal.size / RATE < 25.0, "a self-jumping song has to terminate"


def test_rubbish_is_refused_rather_than_played():
    """A module player is a parser pointed at somebody else's file."""
    with pytest.raises(tracker.ModuleError):
        tracker.parse(b"not a module")
    with pytest.raises(tracker.ModuleError):
        tracker.parse(bytes(2000))  # right size, no signature
    truncated = build({(0, 0, 0): (C2, 1, 0, 0)})[:1200]
    with pytest.raises(tracker.ModuleError):
        tracker.parse(truncated)


def test_an_unknown_effect_is_ignored_and_not_fatal():
    """Ignoring what we do not implement is the honest behaviour."""
    raw = build({(0, 0, 0): (C2, 1, 0x0E, 0xC3)})  # E-commands are unhandled
    signal = tracker.render(tracker.parse(raw), RATE)
    assert signal.size > 0 and np.abs(signal).max() > 0.05


def test_a_module_plays_through_the_ordinary_track_path(tmp_path):
    """It has to be a track like any other, or every game needs a special case."""
    path = tmp_path / "song.mod"
    path.write_bytes(build({(0, 0, 0): (C2, 1, 0, 0)}))
    pcm = audio.render_track({"module": str(path)})
    assert len(pcm) > 0
    samples = np.frombuffer(pcm, dtype="<i2")
    assert np.abs(samples).max() > 8000, "and it has to be audible"
    assert abs(int(samples[0])) < 800 and abs(int(samples[-1])) < 800, "no click"


def test_a_missing_or_broken_module_falls_back_to_the_synthesiser(tmp_path):
    """A soundtrack that vanishes because one file did is a bad trade."""
    note_data = {"root": 440.0, "tempo": 120, "melody": [[0, 4]]}
    fallback = audio.render_track({"module": str(tmp_path / "absent.mod"), **note_data})
    assert len(fallback) == len(audio.render_track(note_data))

    broken = tmp_path / "broken.mod"
    broken.write_bytes(b"rubbish" * 400)
    assert len(audio.render_track({"module": str(broken), **note_data})) == len(fallback)


def test_a_module_carries_its_own_attribution():
    """Tracker authors sign their work in the sample names, and a CC-BY module
    needs that text to reach a credits screen rather than being thrown away.
    """
    module = tracker.parse(build({}))
    assert "TEST SONG" in module.credits
    assert "square" in module.credits
