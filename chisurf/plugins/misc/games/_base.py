"""Shared lifecycle for native games; rules, input mappings and drawing stay local."""

from typing import Any

from emtk.app import ImApp


class GameApp(ImApp):
    """Keep frame demand and optional object-audio cleanup consistent."""

    BINDINGS: tuple[tuple[int | str, Any], ...] = ()
    UNBOUND: Any = None
    FIELDS: tuple[str, ...]

    @classmethod
    def binding(cls, key, text):
        """Resolve physical keys and normalized text in the declared precedence."""
        letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        for token, action in cls.BINDINGS:
            if token == (key if isinstance(token, int) else letter):
                return action
        return cls.UNBOUND

    def export_fields(self) -> dict[str, Any]:
        """Copy the explicitly declared scalar fields of this game's model."""
        return {name: getattr(self.game, name) for name in self.FIELDS}

    closed: bool
    sound_enabled: bool
    last_frame: float | None

    def game_running(self) -> bool:
        """Return whether the game's current state requires another frame."""
        raise NotImplementedError

    def _clear_inputs(self) -> None:
        """Clear the game's held controls and repeat state on focus loss."""
        raise NotImplementedError

    def animating(self) -> bool:
        """Service requested frames and active gameplay until the app closes."""
        return not self.closed and (self.wants_frame or self.game_running())

    def focus_lost(self) -> None:
        """Release transient input and mute audio without changing its preference."""
        self._clear_inputs()
        self.last_frame = None
        audio = getattr(self, "audio", None)
        if audio is not None:
            audio.set_enabled(False)

    def close(self) -> None:
        """Release the supplied audio resource once and stop further animation."""
        if self.closed:
            return
        self.focus_lost()
        self.closed = True
        audio = getattr(self, "audio", None)
        if audio is not None:
            audio.close()

    def sfx(self, name, frequency) -> None:
        """Forward an effect only when an optional backend is enabled and open."""
        audio = getattr(self, "audio", None)
        if not self.closed and audio is not None and self.sound_enabled:
            audio.sfx(name, frequency)

    def set_sound(self) -> None:
        """Toggle the preference only when an open app has an object backend."""
        audio = getattr(self, "audio", None)
        if self.closed or audio is None:
            return
        self.sound_enabled = not self.sound_enabled
        audio.set_enabled(self.sound_enabled)
