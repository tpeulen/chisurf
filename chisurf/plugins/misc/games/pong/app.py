"""Native EMTK Pong, sharing simulation rules with the legacy Qt game."""
from __future__ import annotations

import math
import time
from types import SimpleNamespace

from emtk import i18n, im
from emtk.app import ImApp
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_RETURN, KEY_UP

from .drawing import pixel_text, text_width
from .model import (
    ACCEPTOR_NM,
    DONOR_NM,
    FIELD_H,
    FIELD_W,
    PADDLE_H,
    PADDLE_W,
    PongModel,
    wavelength_to_srgb,
)


def tr(text):
    return i18n.tr(text, context="Pong")


class Inputs:
    def __init__(self):
        self.held = set()
        self.pressed = set()

    def just_pressed(self, action):
        return action in self.pressed

    def axis(self):
        return (0, int("down" in self.held) - int("up" in self.held))

    def end_frame(self):
        self.pressed.clear()


class PongApp(ImApp):
    window_size = (820, 640)

    def __init__(self, audio=None, clock=time.monotonic):
        self.keys, self.p2 = Inputs(), Inputs()
        self.clock = clock
        self.last_frame = None
        self.closed = False
        self.audio = audio
        self.sound_enabled = False
        self.game = PongModel(SimpleNamespace(audio=self))
        self.game.p2 = self.p2
        self.board = (0, 40, 1)
        super().__init__(self.render)

    @property
    def window_title(self):
        return tr("Pong")

    def sfx(self, name, frequency):
        if self.audio is not None and self.sound_enabled:
            self.audio.sfx(name, frequency)

    def set_sound(self):
        if self.audio is None:
            return
        self.sound_enabled = not self.sound_enabled
        if self.audio is not None:
            self.audio.set_enabled(self.sound_enabled)

    def animating(self):
        return not self.closed and not self.game.paused and self.game.winner is None

    def advance(self, dt):
        """Use small simulation steps to prevent tunnelling across paddles."""
        remaining = min(max(float(dt), 0), .1)
        while remaining > 0:
            step = min(remaining, 1 / 120)
            self.game.update(step, self.keys)
            self.keys.end_frame()
            remaining -= step
        self.keys.end_frame()
        self.p2.end_frame()

    @staticmethod
    def binding(key, text):
        letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        if key == KEY_UP:
            return "up", False
        if key == KEY_DOWN:
            return "down", False
        if letter in {"w", "s"}:
            return ("up" if letter == "w" else "down"), True
        return {"p": "menu", "r": "cancel", "m": "shoulder_l", "n": "shoulder_r", " ": "confirm"}.get(letter, "confirm" if key in {KEY_ENTER, KEY_RETURN} else None), False

    def key(self, key, text="", modifiers=0):
        if modifiers or self.closed:
            return False
        action, second = self.binding(key, text)
        if action is None:
            return False
        inputs = self.p2 if second else self.keys
        if action not in inputs.held:
            inputs.pressed.add(action)
        inputs.held.add(action)
        # Toggle immediately even when paused or the winner frame is idle.
        if action not in {"up", "down"}:
            self.game.update(0, self.keys)
            self.keys.end_frame()
        self.request_frame()
        return True

    def key_release(self, key, text="", modifiers=0):
        action, second = self.binding(key, text)
        (self.p2 if second else self.keys).held.discard(action)
        return action is not None

    def focus_lost(self):
        self.keys.held.clear()
        self.p2.held.clear()
        self.keys.end_frame()
        self.last_frame = None
        if self.audio is not None:
            self.audio.set_enabled(False)

    def close(self):
        self.focus_lost()
        self.closed = True
        if self.audio is not None:
            self.audio.close()

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if buttons & 1 and not self.game.paused and self.game.winner is None:
            ox, oy, scale = self.board
            if ox <= x <= ox + FIELD_W * scale and oy <= y <= oy + FIELD_H * scale:
                half = PADDLE_H / 2
                paddle = min(max((y - oy) / scale, half), FIELD_H - half)
                if x < ox + FIELD_W * scale / 2:
                    self.game.paddle_y = paddle
                elif not self.game.vs_computer:
                    self.game.cpu_y = paddle

    def export_settings(self):
        fields = ("player_score", "cpu_score", "rally", "paddle_y", "cpu_y", "ball_nm", "ball_x", "ball_y", "ball_vx", "ball_vy", "serve_timer", "paused", "vs_computer", "muted", "winner")
        return {"game": {name: getattr(self.game, name) for name in fields}, "sound_enabled": self.sound_enabled}

    def restore_settings(self, state):
        saved = state["game"]
        candidate = PongModel(SimpleNamespace(audio=self))
        for name in self.export_settings()["game"]:
            value = saved[name]
            if name == "winner":
                if value not in {None, "Donor", "Acceptor", "Optic 2"}:
                    raise ValueError("invalid winner")
            elif name in {"paused", "vs_computer", "muted"}:
                if not isinstance(value, bool):
                    raise ValueError("invalid game option")
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("invalid numeric game state")
                if name in {"player_score", "cpu_score", "rally"} and (value < 0 or int(value) != value):
                    raise ValueError("invalid score")
            setattr(candidate, name, value)
        if not PADDLE_H / 2 <= candidate.paddle_y <= FIELD_H - PADDLE_H / 2 or not PADDLE_H / 2 <= candidate.cpu_y <= FIELD_H - PADDLE_H / 2:
            raise ValueError("paddle outside the field")
        if candidate.ball_nm not in {DONOR_NM, ACCEPTOR_NM} or candidate.serve_timer < 0:
            raise ValueError("invalid serve state")
        candidate.p2 = self.p2
        self.game = candidate
        self.sound_enabled = bool(state.get("sound_enabled", False))
        self.focus_lost()

    def render(self):
        now = self.clock()
        if self.last_frame is not None and not self.closed:
            self.advance(now - self.last_frame)
        self.last_frame = now
        viewport = im.get_main_viewport()
        x, y = viewport.pos
        w, h = viewport.size
        im.begin("##pong", (x, y, w, h))
        draw = im.get_window_draw_list()
        draw.add_rect_filled((x, y), (x + w, y + h), (8, 9, 11, 255))
        im.set_cursor_screen_pos((x + 4, y + 2))
        # Greyed without an audio backend: emtk plays no sound (the Qt game's
        # chigame audio is QtMultimedia); a switch that changes nothing must not
        # look like one that works.
        im.begin_disabled(self.audio is None)
        if im.button(tr("Sound") + "##sound"):
            self.set_sound()
        im.end_disabled()
        im.set_item_tooltip(tr("Music and sound effects (off by default). N toggles mute.") if self.audio is not None
                            else tr("No sound here: this window has no audio output."))
        scale = min(w / FIELD_W, max(h - 40, 1) / FIELD_H)
        ox, oy = x + (w - FIELD_W * scale) / 2, y + 40 + (h - 40 - FIELD_H * scale) / 2
        self.board = (ox, oy, scale)
        def at(xx, yy):
            return ox + xx * scale, oy + yy * scale

        def rgb(nm):
            return tuple(round(c * 255) for c in wavelength_to_srgb(nm))
        g = self.game
        for index in range(16):
            yy = 20 + index * (FIELD_H - 40) / 15
            draw.add_rect_filled(at(FIELD_W / 2 - 1, yy - 8), at(FIELD_W / 2 + 1, yy + 8), (66, 74, 87, 230))
        for xx, yy, nm in ((26, g.paddle_y, DONOR_NM), (FIELD_W - 26, g.cpu_y, ACCEPTOR_NM)):
            tint = tuple(round((.35 + .65 * c) * 255) for c in wavelength_to_srgb(nm)) + (255,)
            draw.add_rect_filled(at(xx - PADDLE_W / 2 - 1, yy - PADDLE_H / 2 - 1), at(xx + PADDLE_W / 2 + 1, yy + PADDLE_H / 2 + 1), tint[:3] + (60,), rounding=5 * scale)
            draw.add_rect_filled(at(xx - PADDLE_W / 2 + 1, yy - PADDLE_H / 2 + 1), at(xx + PADDLE_W / 2 - 1, yy + PADDLE_H / 2 - 1), tint, rounding=4 * scale)
        for p in g.particles:
            fade = max(p.life / p.max_life, 0)
            r = (2.5 + 3 * fade) * scale / 2
            px, py = at(p.x, p.y)
            draw.add_rect_filled((px-r, py-r), (px+r, py+r), tuple(round(c*255) for c in p.color) + (round(fade*255),))
        if g.winner is None:
            # The legacy quantum has a bright core and a soft spectral halo.
            for radius in range(18, 1, -1):
                alpha = round(255 * max(0, 1 - radius / 19) ** 3)
                draw.add_circle_filled(at(g.ball_x, g.ball_y), radius * scale, rgb(g.ball_nm) + (alpha,))
        dim = (112, 122, 140, 255)
        def text(label, xx, yy, height, colour=dim):
            pixel_text(draw, label, at(xx, yy), height * scale, colour, "center")
        text(tr("Donor: {score}").format(score=g.player_score), FIELD_W*.30, 26, 20, rgb(DONOR_NM)+(255,))
        text(tr("Acceptor: {score}" if g.vs_computer else "Optic 2: {score}").format(score=g.cpu_score), FIELD_W*.70, 26, 20, rgb(ACCEPTOR_NM)+(255,))
        text(tr("Transfers: {count}").format(count=g.rally), FIELD_W/2, 54, 13)
        if g.serve_timer > 0 and g.winner is None:
            text(str(math.ceil(g.serve_timer)), FIELD_W/2, FIELD_H/2, 60, (158, 173, 199, 255))
        if g.paused:
            text(tr("HELD"), FIELD_W/2, FIELD_H/2, 44, (89, 217, 204, 255))
        if g.winner is not None:
            draw.add_rect_filled(at(180, 240), at(620, 360), (26, 28, 33, 255))
            text(tr("{winner} wins").format(winner=tr(g.winner)), FIELD_W/2, FIELD_H/2-16, 34, (89, 217, 204, 255))
            text(tr("Confirm to run again"), FIELD_W/2, FIELD_H/2+26, 16)
            im.set_cursor_screen_pos(at(180, 240))
            if im.invisible_button("##winner", (440*scale, 120*scale)):
                g.restart()
            im.set_item_tooltip(tr("Start a new round (Enter/Space or R)."))
        # Separate clickable captions preserve the legacy footer and remain usable narrow.
        controls = ((100, "Up/Down optic", "Drag the left paddle or hold Up/Down. In two-player mode hold W/S for the right paddle.", None),
                    (280, "Menu hold", "Pause or resume (P).", "menu"),
                    (445, "Cancel reset", "Start a new round (Enter/Space or R).", "cancel"),
                    (595, "L mode", "Switch CPU and two-player mode (M).", "shoulder_l"),
                    (715, "R sound", "Mute or unmute effects (N).", "shoulder_r"))
        labels = [tr(label) for xx, label, tip, action in controls]
        caption = "   ".join(labels)
        height = 15 * scale
        width = text_width(draw, caption, height)
        if width > w - 20:
            height *= (w - 20) / width
            width = text_width(draw, caption, height)
        cursor = x + (w - width) / 2
        yy = at(0, FIELD_H - 18)[1]
        pixel_text(draw, caption, (x + w / 2, yy), height, dim, "center")
        for label, (_, _, tip, action) in zip(labels, controls):
            width = text_width(draw, label, height)
            im.set_cursor_screen_pos((cursor, yy - max(10, height)))
            if im.invisible_button("##control-"+label, (width, max(22, height * 2))) and action:
                self.keys.pressed.add(action)
                g.update(0, self.keys)
                self.keys.end_frame()
            im.set_item_tooltip(tr(tip))
            cursor += width + text_width(draw, "   ", height)
        if g.muted:
            text(tr("[muted]"), FIELD_W/2, FIELD_H-45, 13)
        im.end()


def make_app(audio=None):
    """The game; *audio* is an object with ``sfx``/``set_enabled``/``close`` (none in emtk yet)."""
    from chisurf.emtk.i18n import install

    from .translations import install_translations
    install()
    install_translations()
    return PongApp(audio=audio)
