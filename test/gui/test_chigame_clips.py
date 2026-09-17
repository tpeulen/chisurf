"""The shipped CC0 audio: the codec, the archives, and the wiring to games."""

from __future__ import annotations

import wave
import zipfile

import numpy as np
import pytest

from chisurf.gui.chigame import adpcm, audio
from chisurf.gui.chigame.assets import SOUNDS, TRACKS, ProceduralPack


def _tone(seconds: float = 1.0, rate: int = 22050, freq: float = 440.0) -> np.ndarray:
    """A test signal with enough going on to be worth compressing.

    Parameters
    ----------
    seconds : float, optional
        Length.
    rate : int, optional
        Sample rate.
    freq : float, optional
        Fundamental.

    Returns
    -------
    numpy.ndarray
        Signed 16-bit mono.
    """
    time = np.arange(int(rate * seconds)) / rate
    signal = (np.sin(2 * np.pi * freq * time) * 0.6
              + np.sin(2 * np.pi * freq * 2.7 * time) * 0.2)
    return (signal * 32767).astype(np.int16)


# -- the codec ------------------------------------------------------------

def test_the_codec_is_four_to_one_and_sounds_like_the_input():
    """Four bits a sample is the entire reason the soundtrack is committable."""
    pcm = _tone(2.0)
    clip = adpcm.encode(pcm, 22050)
    assert pcm.nbytes / len(clip) > 3.5, "not actually four-to-one"

    back, rate = adpcm.decode(clip)
    assert rate == 22050
    assert back.size == pcm.size, "a clip has to come back the length it went in"
    error = back.astype(float) - pcm.astype(float)
    snr = 10 * np.log10((pcm.astype(float) ** 2).sum() / max((error ** 2).sum(), 1e-9))
    assert snr > 15.0, f"only {snr:.1f} dB"


def test_decoding_is_fast_enough_to_run_at_load():
    """A sequential decoder would be a Python loop over millions of samples.

    Blocks are what make it parallel, so this is the property that matters
    rather than the wall-clock number: a minute of audio in well under a
    second.
    """
    import time

    clip = adpcm.encode(_tone(60.0), 22050)
    start = time.perf_counter()
    adpcm.decode(clip)
    assert time.perf_counter() - start < 1.0


def test_a_block_does_not_depend_on_the_one_before_it():
    """The claim the whole design rests on: corrupt one block, keep the rest."""
    pcm = _tone(3.0)
    clip = bytearray(adpcm.encode(pcm, 22050))
    stride = 4 + (adpcm.BLOCK - 1 + 1) // 2
    # Scribble over the middle of the second block's nibbles.
    at = 20 + stride + 40
    clip[at:at + 60] = b"\xff" * 60
    back, _ = adpcm.decode(bytes(clip))

    per_block = adpcm.BLOCK
    intact = back[3 * per_block:4 * per_block].astype(float)
    original = pcm[3 * per_block:4 * per_block].astype(float)
    error = intact - original
    snr = 10 * np.log10((original ** 2).sum() / max((error ** 2).sum(), 1e-9))
    assert snr > 15.0, "damage in one block leaked into a later one"


def test_a_clip_reports_its_rate_without_being_decoded():
    """The mixer needs it to write a WAV header, and decoding first is waste."""
    for rate in (11025, 22050, 44100):
        clip = adpcm.encode(_tone(0.2, rate), rate)
        assert adpcm.rate_of(clip) == rate


def test_rubbish_is_refused():
    """A codec is a parser pointed at a file somebody else wrote."""
    with pytest.raises(adpcm.ClipError):
        adpcm.decode(b"not a clip at all")
    with pytest.raises(adpcm.ClipError):
        adpcm.rate_of(b"short")
    with pytest.raises(adpcm.ClipError):
        adpcm.decode(adpcm.MAGIC + bytes(12))


def test_an_empty_or_tiny_input_round_trips():
    """Off-by-one at the block boundary is where this class of code breaks."""
    for count in (1, 2, adpcm.BLOCK - 1, adpcm.BLOCK, adpcm.BLOCK + 1):
        pcm = _tone(1.0)[:count]
        back, _ = adpcm.decode(adpcm.encode(pcm, 22050))
        assert back.size == count, count


# -- the two decode routes ------------------------------------------------

def _gpu_or_skip():
    """Skip when this machine has no compute adapter."""
    if adpcm.device() is None:
        pytest.skip("no GPU adapter on this machine")


@pytest.mark.parametrize("seconds", [0.02, 0.05, 1.0, 5.0])
def test_the_gpu_and_numpy_routes_agree_bit_for_bit(seconds):
    """The property the whole two-route design stands on.

    A lossy codec that decoded differently depending on which route ran would
    change the audio behind the caller's back -- a far worse failure than being
    slow, and one no listening test would catch reliably.
    """
    _gpu_or_skip()
    clip = adpcm.encode(_tone(seconds), 22050)
    on_cpu, cpu_rate = adpcm.decode_cpu(clip)
    decoded = adpcm.decode_gpu(clip)
    assert decoded is not None, "the kernel refused to run"
    on_gpu, gpu_rate = decoded
    assert cpu_rate == gpu_rate
    assert on_cpu.dtype == on_gpu.dtype == np.int16
    assert np.array_equal(on_cpu, on_gpu), (
        f"{int(np.count_nonzero(on_cpu != on_gpu))} of {on_cpu.size} samples differ"
    )


def test_the_routes_agree_on_a_shipped_clip():
    """Synthetic signals are gentle; the real pack is what actually plays."""
    _gpu_or_skip()
    handle = audio.archive("music")
    if handle is None:
        pytest.skip("audio assets are not installed in this checkout")
    raw = handle.read("level_1.snd")
    on_cpu, _ = adpcm.decode_cpu(raw)
    on_gpu, _ = adpcm.decode_gpu(raw)
    assert np.array_equal(on_cpu, on_gpu)


def test_a_block_boundary_does_not_shift_between_routes():
    """Off-by-one in the tail block would be inaudible and still wrong."""
    _gpu_or_skip()
    for count in (1, 2, adpcm.BLOCK - 1, adpcm.BLOCK, adpcm.BLOCK + 1,
                  adpcm.BLOCK * 3 + 7):
        clip = adpcm.encode(_tone(2.0)[:count], 22050)
        on_cpu, _ = adpcm.decode_cpu(clip)
        on_gpu, _ = adpcm.decode_gpu(clip)
        assert on_cpu.size == count, count
        assert np.array_equal(on_cpu, on_gpu), count


def test_the_route_can_be_forced_either_way():
    """So a caller can pin it, and so the twin stays reachable in tests."""
    clip = adpcm.encode(_tone(0.5), 22050)
    forced_cpu, _ = adpcm.decode(clip, gpu=False)
    assert np.array_equal(forced_cpu, adpcm.decode_cpu(clip)[0])
    if adpcm.device() is not None:
        forced_gpu, _ = adpcm.decode(clip, gpu=True)
        assert np.array_equal(forced_gpu, forced_cpu)


def test_no_adapter_is_a_fallback_and_not_a_failure(monkeypatch):
    """A headless runner has no GPU, and the game still has audio."""
    clip = adpcm.encode(_tone(0.5), 22050)
    expected, _ = adpcm.decode_cpu(clip)

    monkeypatch.setattr(adpcm, "_pipeline", lambda: None)
    assert adpcm.decode_gpu(clip) is None
    got, _ = adpcm.decode(clip)
    assert np.array_equal(got, expected), "the router has to fall through"


def test_the_threshold_is_the_measured_one():
    """It was guessed at 600 and measured at 0; that inversion is the point.

    The numpy route runs ``BLOCK`` vectorised steps whatever the clip's length,
    so it has a ~10 ms floor even for a three-block clip -- larger than a
    dispatch. Anything that puts this back above zero should have a table
    behind it.
    """
    assert adpcm.MIN_BLOCKS_FOR_GPU == 0


def test_the_host_lends_its_own_device_rather_than_making_a_second(qapp):
    """Two devices to draw and decompress on one machine is pure waste."""
    pytest.importorskip("wgpu")
    from chisurf.gui import chigame

    class _Quiet(chigame.Game):
        """A game that does nothing but exist."""

        def draw(self, scene) -> None:
            """Draw nothing at all."""

    context = chigame.create_offscreen(size=(64, 64))
    host = chigame.GameHost(_Quiet(), context, with_audio=False, with_text=False)
    try:
        assert adpcm.device() is context.device
    finally:
        adpcm.use_device(None)
        adpcm.device.cache_clear()
        host.close()


# -- what is shipped ------------------------------------------------------

def test_the_shipped_archives_hold_what_the_credits_say():
    """Every shipped clip is named in the credits, or the credits file is wrong.

    Four Ninja Adventure tracks went into music.zip without a line in
    CREDITS.md; a count of five kept failing without saying that. Checking
    the names catches the next addition too.
    """
    music = audio.clip_names("music")
    effects = audio.clip_names("sfx")
    if not music and not effects:
        pytest.skip("audio assets are not installed in this checkout")
    assert set(music) == {"level_1", "level_2", "level_3", "title_screen", "ending",
                          "ninja_plain", "ninja_lost_village", "ninja_dream", "ninja_swamp"}
    assert len(effects) == 512, len(effects)

    credits = (audio.ASSET_DIR / "CREDITS.md")
    assert credits.is_file(), "redistributed work has to say whose it is"
    text = credits.read_text(encoding="utf-8")
    assert "Juhani Junkala" in text and "pixel-boy" in text and "CC0" in text
    for name in music:
        if name.startswith("ninja_"):
            assert f"`{name}`" in text, f"{name} is shipped but not credited"


def test_the_whole_soundtrack_is_smaller_than_the_screenshots():
    """The size budget that decided the format.

    9 MB held the first five loops and the effects (6.7 MB). The four Ninja
    Adventure tracks brought it to 9.3 MB; the budget moved to 10 MB with
    them, on purpose, and stays a budget -- another soundtrack needs a reason.
    """
    if not (audio.ASSET_DIR / "music.zip").is_file():
        pytest.skip("audio assets are not installed in this checkout")
    total = sum(path.stat().st_size
                for path in audio.ASSET_DIR.glob("*.zip"))
    assert total < 10_000_000, f"{total / 1e6:.1f} MB"


def test_the_archives_are_stored_not_deflated():
    """The clips are already compressed; deflating them again is CPU for 0%."""
    if not (audio.ASSET_DIR / "sfx.zip").is_file():
        pytest.skip("audio assets are not installed in this checkout")
    with zipfile.ZipFile(audio.ASSET_DIR / "sfx.zip") as handle:
        kinds = {entry.compress_type for entry in handle.infolist()}
    assert kinds == {zipfile.ZIP_STORED}


def test_every_clip_decodes_and_is_audible():
    """A silent clip in the pack is a bug nobody would otherwise notice."""
    names = audio.clip_names("music")
    if not names:
        pytest.skip("audio assets are not installed in this checkout")
    for name in names:
        found = audio.clip(name, "music")
        assert found is not None, name
        pcm, rate = found
        assert rate == 22050, name
        samples = np.frombuffer(pcm, dtype="<i2")
        assert samples.size / rate > 5.0, name
        assert np.abs(samples).max() > 3000, f"{name} is silent"


def test_asking_for_a_clip_that_is_not_there_is_not_an_error():
    """A stripped install has to run, not raise."""
    assert audio.clip("no-such-clip", "music") is None
    assert audio.clip("no-such-clip", "sfx") is None
    assert audio.archive("no-such-archive") is None
    assert audio.clip_names("no-such-archive") == ()


# -- the wiring -----------------------------------------------------------

def test_every_context_plays_a_real_recording():
    """The synthesiser is the fallback now, not the soundtrack.

    ``overworld`` and ``underworld`` are the deliberate exceptions: the
    shipped CC0 pack's "Level 1" and "Level 3" are an upbeat action loop and
    a becalmed dungeon crawl, and open ground plus the dark manifold below
    it need to read as tense, not either of those -- so both always use the
    sequencer.
    """
    if not audio.clip_names("music"):
        pytest.skip("audio assets are not installed in this checkout")
    exempt = {"overworld", "underworld"}
    for context, track in TRACKS.items():
        if context not in exempt:
            assert "clip" in track, context
            assert audio.clip(track["clip"], "music") is not None, context
        # ...and the note data is still there, so a stripped install still
        # has music rather than silence.
        assert "melody" in track, context


def test_every_game_event_maps_onto_a_clip_that_exists():
    """The guard that stops the alias table rotting as the pack changes."""
    names = set(audio.clip_names("sfx"))
    if not names:
        pytest.skip("audio assets are not installed in this checkout")
    missing = {event: name for event, name in SOUNDS.items() if name not in names}
    assert missing == {}, missing


def test_the_events_the_games_actually_raise_are_all_mapped():
    """A game asking for a sound nobody wired up gets a beep, silently."""
    for event in ("paddle", "wall", "launch", "score", "lost", "break", "crack",
                  "settle", "clear", "reveal", "flag", "guess",
                  "emit", "unbind", "seal", "bleach", "talk", "cross"):
        assert ProceduralPack().sound_clip(event), event
    assert ProceduralPack().sound_clip("something nobody defined") is None


def test_a_recorded_track_is_rendered_at_the_clip_rate_not_the_synth_rate():
    """A WAV that lies about its rate plays at the wrong pitch and speed."""
    if not audio.clip_names("music"):
        pytest.skip("audio assets are not installed in this checkout")
    # Not "overworld": that context has no clip -- see
    # test_every_context_plays_a_real_recording.
    track = TRACKS["battle"]
    pcm = audio.render_track(track)
    expected = audio.clip(track["clip"], "music")[0]
    assert pcm == expected, "the recording should be used verbatim"


def test_write_wav_declares_the_rate_it_was_given(tmp_path):
    """Which is what carries the clip rate through to playback."""
    path = audio.write_wav(tmp_path / "clip.wav", _tone(0.1, 22050).tobytes(), 22050)
    with wave.open(str(path)) as handle:
        assert handle.getframerate() == 22050
        assert handle.getnchannels() == 1 and handle.getsampwidth() == 2


def test_a_stripped_install_still_has_a_soundtrack(monkeypatch):
    """Losing the assets must degrade to the synthesiser, not to silence."""
    monkeypatch.setattr(audio, "ASSET_DIR", audio.ASSET_DIR / "absent")
    audio.archive.cache_clear()
    audio.clip.cache_clear()
    try:
        assert audio.clip_names("music") == ()
        pcm = audio.render_track(TRACKS["overworld"])
        assert len(pcm) > 0, "the note data has to still be there"
    finally:
        audio.archive.cache_clear()
        audio.clip.cache_clear()
