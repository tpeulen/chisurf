"""Shared lifecycle for native games; rules, input mappings and drawing stay local."""

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.keys import KEY_ESCAPE
from emtk.view_form import FormState, draw_sections, icon_caption

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from ._translations import install_translations


class GameApp(ImApp):
    """Keep frame demand and optional object-audio cleanup consistent."""

    def __init__(self, gui, *args, **kwargs):
        """Bind declared header controls without changing the game's own canvas."""
        install_translations()
        self._game_gui = gui
        self.header_spec = json.loads(Path(__file__).with_name("game_header.view.json").read_text())
        self.header_form = FormState()
        self.help_window = EmTkHelpWindow(
            title=tr(self.header_spec["title"]),
            resource=self.HELP_DIR / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
        )
        self.tour = EmTkGuidedTour(
            self.HELP_DIR / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda name: self.header_form.rects.get(name),
        )
        self.header_form.on_used = self.tour.notify_used
        super().__init__(self._render_game, *args, **kwargs)

    @property
    def overlay_active(self) -> bool:
        """Whether shared help or a tour currently owns game input."""
        return self.help_window.open or self.tour.active

    def overlay_key(self, key, text="", modifiers=0) -> bool:
        """Route modal keys to the overlay and consume game shortcuts."""
        if key == KEY_ESCAPE:
            if self.help_window.open:
                self.help_window.hide()
            else:
                self.tour.stop()
            self.request_frame()
        else:
            super().key(key, text, modifiers)
        return True

    def enabled(self, action: str) -> bool:
        """Expose only the awaited header target while a guide owns input."""
        if self.closed or self.help_window.open:
            return False
        if self.tour.active:
            step = self.tour.steps[self.tour.step_idx]
            return self.tour.awaiting and action == self.tour._target_key(step.get("target"))
        return True

    def open_help(self) -> None:
        """Open authored help without leaving held gameplay controls active."""
        if self.closed:
            return
        self.focus_lost()
        self.help_window.show()
        self.request_frame()

    def start_guide(self) -> None:
        """Start a tour that waits for real user actions rather than resetting."""
        if self.closed:
            return
        self.focus_lost()
        self.help_window.hide()
        self.tour.start()
        self.request_frame()

    def restart_game(self) -> None:
        """Restart through the existing game reset and release transient input."""
        if self.closed:
            return
        self.focus_lost()
        self._restart_round()
        self.request_frame()

    def _restart_round(self) -> None:
        """Use the existing model restart; apps with UI state override this hook."""
        self.game.restart()

    def _render_game(self) -> None:
        """Keep original drawing intact, then draw the header and owned overlays."""
        blocked = self.overlay_active
        if blocked:
            self.last_frame = None
        im.begin_disabled(blocked)
        try:
            self._game_gui()
        finally:
            im.end_disabled()
        viewport = im.get_main_viewport()
        x, y = viewport.pos
        width, height = viewport.size
        self.header_form.rects.clear()
        box = (x + 90, y + 2, min(300, max(width - 94, 1)), 30)
        im.begin("##game_header", box, flags=im.WindowFlags.NO_BACKGROUND)
        im.begin_disabled(self.closed or self.help_window.open)
        try:
            section = self.header_spec["sections"][0]
            buttons = [
                {**button, "label": tr(button["label"]), "description": tr(button["description"])}
                for button in section["buttons"]
            ]
            # Fit this row only; the existing Sound and canvas geometry never move.
            pad = im.get_style().frame_padding[0] * 2
            spacing = im.get_style().item_inner_spacing[0] * (len(buttons) - 1)
            text_width = sum(
                im.calc_text_size(icon_caption(button.get("icon", ""), button["label"]))[0]
                for button in buttons
            )
            available = box[2] - spacing - pad * len(buttons)
            scale = min(1.0, max(0.1, available / max(text_width, 1)))
            im.push_font_scale(scale)
            try:
                draw_sections(
                    [{**section, "buttons": buttons}], self, self.header_form, titles=False
                )
            finally:
                im.pop_font_scale()
        finally:
            im.end_disabled()
            im.end()
        self.help_window.draw((x, y, width, height))
        if not self.help_window.open:
            self.tour.draw(width, height)

    HELP_DIR: Path

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
        return not self.closed and (
            self.wants_frame or (not self.overlay_active and self.game_running())
        )

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
        self.help_window.hide()
        self.tour.stop()
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
