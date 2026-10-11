"""The one audio backend of the emtk games: chigame's synthesis played through ``emtk.audio``.

The Qt games played through ``QtMultimedia``; the emtk games take an object with ``sfx``,
``set_enabled`` and ``close`` and run without Qt.  :class:`GameAudio` is that object.  Samples come from
:mod:`chisurf.core.audio` (band-limited oscillators, eight-bar pieces, the shipped CC0 clips), output
from :class:`emtk.audio.AudioOutput`.  It starts silent: music and effects begin when ``set_enabled(True)``
arrives from the shared Sound toggle, and stop on ``set_enabled(False)``, which is also what a game does
when its window loses focus.
"""

from __future__ import annotations

import threading

from chisurf.core.audio import synth
from chisurf.core.audio.tracks import SOUNDS, TRACKS

#: Music sits under the effects.
MUSIC_VOLUME = 0.5
SFX_VOLUME = 1.0


class GameAudio:
    """Sound effects and a looping piece of music for one game window.

    Parameters
    ----------
    context : str, optional
        Musical context (``overworld``, ``town``, ``battle``, ``underworld``, ``victory``); ``None`` means
        effects only.
    output : emtk.audio.AudioOutput, optional
        Where the samples go; default is a fresh output on the system player.
    """

    def __init__(self, context: str | None = None, output=None):
        if output is None:
            from emtk.audio import AudioOutput

            output = AudioOutput()
        self.output = output
        self.context = context
        self.enabled = False
        self.closed = False
        self._generation = 0
        self._blips: dict[tuple[str, float], tuple[bytes, int]] = {}
        self._music: dict[str, tuple[bytes, int]] = {}

    @property
    def available(self) -> bool:
        """Whether anything can be heard (a system player exists and the output is open)."""
        return not self.closed and self.output.available

    def sfx(
        self, name: str, frequency: float = 660.0, duration: float = 0.08, bend: float = 0.0
    ) -> None:
        """Play the effect for game event *name* (a shipped clip, else a synthesised blip)."""
        if not self.enabled or self.closed:
            return
        key = (name, float(frequency))
        if key not in self._blips:
            found = synth.clip(SOUNDS.get(name, name), "sfx")
            if found is None:
                found = (synth.render_blip(frequency, duration, bend=bend), synth.SAMPLE_RATE)
            self._blips[key] = found
        pcm, rate = self._blips[key]
        self.output.play(f"sfx-{name}", pcm, rate, volume=SFX_VOLUME)

    def set_context(self, context: str | None) -> None:
        """Switch the music; the same context again is a no-op."""
        if context == self.context and self._music_running():
            return
        self.context = context
        self._start_music()

    def _music_running(self) -> bool:
        return self.output.playing("music")

    def _start_music(self) -> None:
        """(Re)start the music for the current context without blocking the frame that asked."""
        self._generation += 1
        self.output.stop("music")
        track = TRACKS.get(self.context) if (self.enabled and self.context) else None
        if track is None or self.closed:
            return
        generation, context = self._generation, self.context
        if context in self._music:
            self._play_music(context, generation)
            return

        def render():
            try:
                self._music[context] = (synth.render_track(track), self._track_rate(track))
            except Exception:
                return
            self._play_music(context, generation)

        threading.Thread(target=render, name="game-audio-render", daemon=True).start()

    @staticmethod
    def _track_rate(track: dict) -> int:
        recorded = track.get("clip")
        if recorded:
            found = synth.clip(str(recorded), "music")
            if found is not None:
                return found[1]
        return synth.SAMPLE_RATE

    def _play_music(self, context: str, generation: int) -> None:
        # A toggle, focus change or context switch since the render started makes this one stale.
        if generation != self._generation or self.closed or not self.enabled:
            return
        pcm, rate = self._music[context]
        self.output.play("music", pcm, rate, loop=True, volume=MUSIC_VOLUME)

    def set_enabled(self, enabled: bool) -> None:
        """Give the game a voice, or silence everything (the preference lives with the game)."""
        enabled = bool(enabled) and not self.closed
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self._start_music()
        else:
            self._generation += 1
            self.output.stop()

    def close(self) -> None:
        """Stop for good and release the output."""
        self.enabled = False
        self._generation += 1
        self.closed = True
        self.output.close()


def default_audio(context: str | None = None):
    """A :class:`GameAudio` when this machine can play sound, else ``None`` (the Sound switch greys out).

    An emtk older than ``emtk.audio`` (the pinned build before the lock is bumped) also gives ``None``.
    """
    try:
        audio = GameAudio(context)
    except ImportError:
        return None
    return audio if audio.available else None


#: Default of a game factory's ``audio`` argument: "use this machine's sound if it has any".  Pass
#: ``None`` for no audio (a greyed Sound switch) or your own object with ``sfx``/``set_enabled``/``close``.
AUTO = object()


def resolve_audio(audio, context: str | None):
    """Return *audio* itself, or the default backend for *context* when it is :data:`AUTO`."""
    return default_audio(context) if audio is AUTO else audio
