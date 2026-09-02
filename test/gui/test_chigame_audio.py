"""Synthesised music: it has to be music, and it has to stop when you leave."""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.gui.chigame import audio
from chisurf.gui.chigame.assets import TRACKS


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
        pcm = _samples({"root": 440.0, "tempo": 60,
                        "melody": {"wave": "sine", "notes": [[semitone, 4]]}})
        spectrum = np.abs(np.fft.rfft(pcm * np.hanning(pcm.size)))
        freqs = np.fft.rfftfreq(pcm.size, 1.0 / audio.SAMPLE_RATE)
        peak = freqs[spectrum.argmax()]
        assert abs(peak - expected) < 4.0, (semitone, peak, expected)


def test_a_rest_is_silent_and_a_held_note_is_held():
    """Without either, a track is a metronome playing a scale."""
    eighth = int(audio.SAMPLE_RATE * 30.0 / 120.0)
    pcm = _samples({"root": 440.0, "tempo": 120,
                    "melody": [[0, 2], None, None, [0, 2]]})
    assert pcm.size == pytest.approx(6 * eighth, rel=0.02)
    held = np.abs(pcm[:2 * eighth]).mean()
    rest = np.abs(pcm[int(2.2 * eighth):int(3.8 * eighth)]).mean()
    assert held > 0.02
    assert rest < held / 50.0, "a rest has to actually be a rest"


def test_the_waveforms_are_band_limited():
    """A hard square at 44.1 kHz folds back over itself as a metallic buzz.

    This is the difference between the old synthesiser and this one, and it is
    measurable: a naive square built from a sign flip puts a large fraction of
    its energy above Nyquist, where it aliases down into the audible band.
    """
    for shape in ("square", "saw", "triangle"):
        pcm = _samples({"root": 880.0, "tempo": 60,
                        "melody": {"wave": shape, "notes": [[0, 4]]},
                        "tone": 1.0})
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
        assert any(entry is None or isinstance(entry, (list, tuple))
                   for entry in notes), name


def test_every_context_has_a_track_and_they_are_not_the_same_piece():
    """Where you are should be audible."""
    from chisurf.gui.chigame.assets import ProceduralPack

    pack = ProceduralPack()
    roots = set()
    for context in audio.CONTEXTS:
        track = pack.music_track(context)
        assert track is not None, context
        roots.add((track["root"], track["tempo"]))
    assert len(roots) == len(audio.CONTEXTS), "two contexts share a piece"


def test_a_suspended_mixer_remembers_where_the_game_got_to():
    """Coming back to the window starts the right piece, not the last one."""
    from chisurf.gui.chigame.assets import ProceduralPack

    mixer = audio.Audio(ProceduralPack(), enabled=False)
    mixer.set_context("overworld")
    mixer.suspend()
    assert mixer.suspended
    # The game keeps playing while nobody is listening; the context still moves.
    mixer.set_context("battle")
    assert mixer.context is None, "nothing plays while suspended"
    mixer.resume()
    assert not mixer.suspended
    assert mixer.context == "battle"


def test_suspending_twice_and_resuming_unsuspended_are_both_harmless():
    """The window manager will send whatever it likes, twice."""
    from chisurf.gui.chigame.assets import ProceduralPack

    mixer = audio.Audio(ProceduralPack(), enabled=False)
    mixer.resume()
    mixer.set_context("town")
    mixer.suspend()
    mixer.suspend()
    mixer.resume()
    mixer.resume()
    assert mixer.context == "town" and not mixer.suspended


def test_a_blip_bends_and_fades_to_nothing():
    """A flat tone with hard edges is a beep; an effect is an event."""
    pcm = np.frombuffer(audio.render_blip(440.0, 0.12, bend=12.0),
                        dtype="<i2").astype(float) / 32768.0
    assert pcm.size == pytest.approx(int(0.12 * audio.SAMPLE_RATE), rel=0.02)
    assert abs(pcm[0]) < 0.02 and abs(pcm[-1]) < 0.02
    half = pcm.size // 2
    first = np.fft.rfftfreq(half, 1.0 / audio.SAMPLE_RATE)[
        np.abs(np.fft.rfft(pcm[:half] * np.hanning(half))).argmax()]
    second = np.fft.rfftfreq(half, 1.0 / audio.SAMPLE_RATE)[
        np.abs(np.fft.rfft(pcm[half:half * 2] * np.hanning(half))).argmax()]
    assert second > first * 1.2, "the bend has to be audible"


def test_a_game_in_a_window_nobody_is_looking_at_goes_quiet(qapp):
    """The single most annoying thing a background process can do."""
    pytest.importorskip("wgpu")
    from chisurf.gui import chigame

    class _Quiet(chigame.Game):
        """A game that does nothing but exist."""

        music_context = "overworld"

        def draw(self, scene) -> None:
            """Draw nothing at all."""

    game = _Quiet()
    context = chigame.create_offscreen(size=(64, 64))
    host = chigame.GameHost(game, context, with_audio=False)
    # An offscreen canvas is nobody's foreground, and must not be treated as
    # backgrounded either -- a headless capture has to keep running.
    assert host.attend() is True

    host.audio.enabled = True          # pretend Qt multimedia is present
    host.audio._sound_cls = None       # ...but never actually load a sample
    host.sync_audio()
    assert not host.audio.suspended

    host.attend = lambda: False
    host.sync_audio()
    assert host.audio.suspended, "a window out of scope has to silence the game"
    host.attend = lambda: True
    host.sync_audio()
    assert not host.audio.suspended
    host.close()


def test_music_follows_where_the_player_is(qapp, tmp_path):
    """One context everywhere is one loop everywhere, which is the whole bug."""
    pytest.importorskip("wgpu")
    from chisurf.plugins.misc.games.lumis_quest.api.world import build_world
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    root = tmp_path / "docs" / "guides"
    root.mkdir(parents=True)
    for index in range(6):
        (root / f"p{index}.md").write_text(f"# P{index}\n\nProse.\n", encoding="utf-8")
    (root / "index.md").write_text(
        "# Guides\n\n```{toctree}\n\n" + "\n".join(f"p{i}" for i in range(6)) + "\n```\n",
        encoding="utf-8",
    )
    world = build_world(tmp_path / "docs")
    game = OverworldGame(world=world, save_path=tmp_path / "run.json")
    from chisurf.gui import chigame

    chigame.capture(game, size=(64, 64), frames=1,
                    script=lambda index, host: game.finish_loading(skip_prologue=True))

    village = world.villages[0]
    col, row, width, height = village.rect
    game.player_pos = [(col + width / 2) * 18.0, (row + height * 0.6) * 18.0]
    assert game.music_context == "town"
    game.dark = True
    assert game.music_context == "underworld"
    game.dark = False
    game.battle = object()
    assert game.music_context == "battle"
    game.battle = None
    game.player_pos = [4.0, 4.0]
    assert game.music_context == "overworld"
    assert set(audio.CONTEXTS) >= {"town", "underworld", "battle", "overworld"}


def test_the_synthesiser_is_fast_enough_to_run_at_load_time():
    """A track that takes a second to build is a second of frozen window."""
    import time

    start = time.perf_counter()
    for track in TRACKS.values():
        audio.render_track(track)
    spent = time.perf_counter() - start
    assert spent < 2.0, spent
    assert math.isfinite(spent)
