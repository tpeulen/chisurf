"""Qt player for the synthesised music and effects (the samples come from :mod:`chisurf.core.audio.synth`)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile

from chisurf.core.audio.synth import (  # noqa: F401  (re-exported)
    CONTEXTS,
    SAMPLE_RATE,
    archive,
    clip,
    clip_names,
    render_blip,
    render_track,
    write_wav,
)


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
        #: Independent channel levels, 0.0 (silent) to 1.0 (full) -- a game's
        #: options screen sets these; nothing here reads them from disk, so
        #: persisting a player's choice between sessions is the game's job.
        self.music_volume = 1.0
        self.sfx_volume = 1.0
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
        effect.setVolume(self.music_volume if key.startswith("music-") else self.sfx_volume)
        if loop:
            effect.setLoopCount(self._sound_cls.Infinite)
        self._effects[key] = effect
        return effect

    def set_music_volume(self, volume: float) -> None:
        """Set the music channel's level.

        Parameters
        ----------
        volume : float
            0.0 (silent) to 1.0 (full); out-of-range values are clamped.
        """
        self.music_volume = max(0.0, min(1.0, float(volume)))
        if self._music is not None:
            self._music.setVolume(self.music_volume)

    def set_sfx_volume(self, volume: float) -> None:
        """Set the sound-effect channel's level.

        Parameters
        ----------
        volume : float
            0.0 (silent) to 1.0 (full); out-of-range values are clamped.
        """
        self.sfx_volume = max(0.0, min(1.0, float(volume)))
        for key, effect in self._effects.items():
            if not key.startswith("music-"):
                effect.setVolume(self.sfx_volume)

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
        key = (
            "music-"
            + hashlib.sha256(json.dumps(track, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        )
        # A track that names a shipped clip is stored at the clip's own rate,
        # not the synthesiser's; a WAV that lies about its rate plays at the
        # wrong pitch and at the wrong speed.
        rate = SAMPLE_RATE
        recorded = track.get("clip")
        if recorded:
            found = clip(str(recorded), "music")
            if found is not None:
                rate = found[1]
        effect = self._load(key, render_track(track), bool(track.get("loop", True)), rate)
        if effect is not None:
            effect.play()
            self._music = effect

    def sfx(
        self, name: str, frequency: float = 660.0, duration: float = 0.08, bend: float = 0.0
    ) -> None:
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
            effect = self._load(
                f"sfx-{name}", render_blip(frequency, duration, bend=bend), loop=False
            )
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
