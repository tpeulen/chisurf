"""Standalone EMTK Breakout with the original spectral wall and physics."""
from __future__ import annotations

import math
import time
from types import SimpleNamespace

from emtk import i18n, im
from emtk.app import ImApp
from emtk.keys import KEY_ENTER, KEY_LEFT, KEY_RETURN, KEY_RIGHT

from .drawing import pixel_text, text_width
from .model import (
    BALL_SIZE,
    BRICK_COLS,
    BRICK_ROWS,
    EXCITATION_NM,
    PADDLE_H,
    PADDLE_W,
    PADDLE_Y,
    BreakoutModel,
    H,
    Particle,
    W,
    photon_energy_rank,
    wavelength_to_srgb,
)


def tr(text):
    return i18n.tr(text, context="Breakout")


class Inputs:
    def __init__(self):
        # Track physical keys so releasing Left does not cancel a held A.
        self.held = {}
        self.pressed = set()

    def just_pressed(self, action):
        return action in self.pressed

    def axis(self):
        held = self.held.values()
        return int("right" in held) - int("left" in held), 0

    def end_frame(self):
        self.pressed.clear()


class BreakoutApp(ImApp):
    window_size = (820, 690)

    def __init__(self, clock=time.monotonic):
        self.keys = Inputs()
        self.clock = clock
        self.last_frame = None
        self.closed = False
        self.sound_enabled = False
        self.game = BreakoutModel(SimpleNamespace(audio=self))
        self.board = (0, 36, 1)
        super().__init__(self.render)

    @property
    def window_title(self):
        return tr("Breakout")

    def sfx(self, name, frequency):
        """EMTK has no audio backend; preserve mute state without pretending playback."""

    def animating(self):
        return not self.closed and (self.wants_frame or (not self.game.paused and self.game.message is None and (not self.game.stuck or bool(self.keys.held) or bool(self.game.particles))))

    def advance(self, dt):
        remaining = min(max(float(dt), 0), .1)
        # A zero timestep still applies queued controls while paused/idle.
        if not remaining:
            self.game.update(0, self.keys)
        while remaining > 0:
            step = min(remaining, 1 / 120)
            self.game.update(step, self.keys)
            self.keys.end_frame()
            remaining -= step
        self.keys.end_frame()

    @staticmethod
    def binding(key, text):
        letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        if key == KEY_LEFT:
            return "left"
        if key == KEY_RIGHT:
            return "right"
        if key in {KEY_ENTER, KEY_RETURN}:
            return "confirm"
        # Arrows only for movement, per the owner's direction-key rule (no WASD).
        return {" ": "confirm", "p": "menu", "r": "cancel", "m": "shoulder_r"}.get(letter)

    def key(self, key, text="", modifiers=0):
        if modifiers or self.closed:
            return False
        action = self.binding(key, text)
        if action is None:
            return False
        if key not in self.keys.held:
            self.keys.pressed.add(action)
        self.keys.held[key] = action
        if action not in {"left", "right"}:
            self.advance(0)
        self.request_frame()
        return True

    def key_release(self, key, text="", modifiers=0):
        action = self.keys.held.pop(key, None)
        return action is not None or self.binding(key, text) is not None

    def focus_lost(self):
        self.keys.held.clear()
        self.keys.end_frame()
        self.last_frame = None

    def close(self):
        self.focus_lost()
        self.closed = True

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        ox, oy, scale = self.board
        if buttons & 1 and not self.closed and not self.game.paused and self.game.message is None and ox <= x <= ox + W * scale and oy <= y <= oy + H * scale:
            self.game.paddle_x = min(max((x - ox) / scale, PADDLE_W / 2), W - PADDLE_W / 2)
            if self.game.stuck:
                self.game.ball_x = self.game.paddle_x
            self.request_frame()

    def control(self, action):
        self.keys.pressed.add(action)
        self.advance(0)
        self.request_frame()

    def export_settings(self):
        fields = ("score", "level", "lives", "paused", "muted", "message", "paddle_x", "stuck", "ball_x", "ball_y", "ball_vx", "ball_vy", "ball_nm")
        return {"game": {name: getattr(self.game, name) for name in fields}, "bricks": [b.hp for b in self.game.bricks], "particles": [vars(p).copy() for p in self.game.particles], "sound_enabled": self.sound_enabled}

    def restore_settings(self, state):
        """Validate the entire saved round before replacing live state."""
        candidate = BreakoutModel(SimpleNamespace(audio=self))
        for name in self.export_settings()["game"]:
            value = state["game"][name]
            if name in {"paused", "muted", "stuck"}:
                if not isinstance(value, bool):
                    raise ValueError("invalid game flag")
            elif name == "message":
                if value not in {None, "Sample bleached"}:
                    raise ValueError("invalid game message")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("invalid numeric game state")
            setattr(candidate, name, value)
        for name, minimum, maximum in (("score", 0, None), ("level", 1, None), ("lives", 0, 3)):
            value = getattr(candidate, name)
            if value != int(value) or value < minimum or (maximum is not None and value > maximum):
                raise ValueError("invalid score/level/lives")
        if not PADDLE_W / 2 <= candidate.paddle_x <= W - PADDLE_W / 2 or not 380 <= candidate.ball_nm <= 780:
            raise ValueError("invalid paddle or spectrum")
        health = state["bricks"]
        if len(health) != BRICK_ROWS * BRICK_COLS:
            raise ValueError("invalid brick grid")
        for brick, hp in zip(candidate.bricks, health):
            if isinstance(hp, bool) or not isinstance(hp, int) or not 0 <= hp <= brick.max_hp:
                raise ValueError("invalid brick health")
            brick.hp = hp
        for saved in state.get("particles", []):
            if set(saved) != {"x", "y", "vx", "vy", "nm", "life", "max_life"} or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in saved.values()):
                raise ValueError("invalid particle")
            if not 0 < saved["life"] <= saved["max_life"] or not 380 <= saved["nm"] <= 780:
                raise ValueError("invalid particle lifetime/spectrum")
            p = Particle(saved["x"], saved["y"], saved["vx"], saved["vy"], saved["nm"], saved["life"])
            p.max_life = saved["max_life"]
            candidate.particles.append(p)
        enabled = state.get("sound_enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("invalid sound flag")
        self.game = candidate
        self.sound_enabled = enabled
        self.focus_lost()
        self.request_frame()

    def render(self):
        now = self.clock()
        if self.last_frame is not None and not self.closed:
            self.advance(now - self.last_frame)
        self.last_frame = now
        viewport = im.get_main_viewport()
        x, y = viewport.pos
        w, h = viewport.size
        im.begin("##breakout", (x, y, w, h))
        draw = im.get_window_draw_list()
        draw.add_rect_filled((x, y), (x+w, y+h), (8, 9, 11, 255))
        im.set_cursor_screen_pos((x+4, y+2))
        if im.button(tr("Sound")+"##sound"):
            self.sound_enabled = not self.sound_enabled
        im.set_item_tooltip(tr("Sound state only: EMTK audio is unavailable. M toggles mute."))
        # Fit the same 800x650 board without clipping at narrow widths.
        scale = min(w/W, max(h-36, 1)/H)
        ox, oy = x+(w-W*scale)/2, y+36+(h-36-H*scale)/2
        self.board = ox, oy, scale
        def at(xx, yy):
            return ox+xx*scale, oy+yy*scale
        def rgb(nm):
            return tuple(round(v*255) for v in wavelength_to_srgb(nm))
        def glow(xx, yy, radius, nm, alpha=255):
            for r in range(20, 0, -1):
                fraction = r/20
                opacity = round(alpha * (1-fraction)**3)
                draw.add_circle_filled(at(xx, yy), radius*fraction*scale, rgb(nm)+(opacity,))
        g = self.game
        for b in g.bricks:
            if not b.alive:
                continue
            # Soft emission spill outside each solid band. Square corners: rounded fills are tessellated
            # into ~25 triangles each and made the frame cost seconds in the software painter (the
            # 'draw never finishes' of the audit); the halo is <=10/255 alpha, so corners are invisible.
            for expand, alpha in ((18, 4), (11, 8), (5, 12)):
                draw.add_rect_filled(at(b.x-b.w/2-expand, b.y-b.h/2-expand), at(b.x+b.w/2+expand, b.y+b.h/2+expand), rgb(b.nm)+(alpha,))
        for b in g.bricks:
            if b.alive:
                gain = .78+.22*photon_energy_rank(b.nm)
                colour = tuple(round(c*gain) for c in rgb(b.nm))+(115 if b.hp < b.max_hp else 255,)
                draw.add_rect_filled(at(b.x-b.w/2+1, b.y-b.h/2+1), at(b.x+b.w/2-1, b.y+b.h/2-1), colour, rounding=2*scale)
        draw.add_rect_filled(at(0, PADDLE_Y+15), at(W, PADDLE_Y+17), (66, 74, 87, 255))
        draw.add_rect_filled(at(g.paddle_x-PADDLE_W/2+1, PADDLE_Y-PADDLE_H/2+1), at(g.paddle_x+PADDLE_W/2-1, PADDLE_Y+PADDLE_H/2-1), (173, 184, 201, 255), rounding=2*scale)
        for p in g.particles:
            fade = max(p.life/p.max_life, 0)
            glow(p.x, p.y, (2.5*fade+1)*1.3, p.nm)
        glow(g.ball_x, g.ball_y, BALL_SIZE*1.3, g.ball_nm)
        dim = (158, 173, 199, 255)
        def text(label, xx, yy, height, colour=dim, align="center"):
            pixel_text(draw, label, at(xx, yy), height*scale, colour, align)
        text(tr("Counts: {score}").format(score=g.score), 14, 20, 17, (255,255,255,255), "left")
        text(tr("Scan: {level}").format(level=g.level), W/2, 20, 17, (255,255,255,255))
        text(tr("Pulses:"), W-76, 20, 17, (255,255,255,255), "right")
        for index in range(g.lives):
            glow(W-56+index*20, 20, 9.1, EXCITATION_NM)
        if g.stuck and g.message is None and not g.paused:
            text(tr("Confirm to fire"), W/2, H*.45, 20)
        if g.paused:
            text(tr("HELD"), W/2, H*.45, 40, (89,217,204,255))
        if g.message is not None:
            draw.add_rect_filled(at(190, H/2-55), at(610, H/2+55), (26,28,33,255))
            text(tr(g.message), W/2, H/2-14, 30, (230,82,77,255))
            text(tr("Confirm for a fresh sample"), W/2, H/2+24, 15)
            im.set_cursor_screen_pos(at(190, H/2-55))
            if im.invisible_button("##gameover", (420*scale,110*scale)):
                self.control("confirm")
            im.set_item_tooltip(tr("Start a fresh sample (Enter/Space or R)."))
        controls = (("Left/Right detector", "Drag the detector or hold Left/Right or A/D.", None),
                    ("Confirm fire", "Launch the photon (Enter/Space).", "confirm"),
                    ("Menu hold", "Pause or resume (P).", "menu"),
                    ("Cancel reset", "Start a fresh sample (Enter/Space or R).", "cancel"),
                    ("R sound", "Toggle mute state (M); EMTK audio is unavailable.", "shoulder_r"))
        labels = [tr(label) for label, tip, action in controls]
        caption = "   ".join(labels)+(tr("   [muted]") if g.muted else "")
        height = 13*scale
        width = text_width(draw, caption, height)
        if width > w-16:
            height *= max(w-16,1)/width
            width = text_width(draw, caption, height)
        yy = at(0,H-12)[1]
        pixel_text(draw, caption, (x+w/2,yy), height, (112,122,140,255), "center")
        cursor = x+(w-width)/2
        for label, (_,tip,action) in zip(labels,controls):
            width = text_width(draw,label,height)
            im.set_cursor_screen_pos((cursor,yy-11))
            if im.invisible_button("##control-"+label, (width,22)) and action:
                self.control(action)
            im.set_item_tooltip(tr(tip))
            cursor += width+text_width(draw,"   ",height)
        # Board drag target is behind the caption controls.
        im.set_cursor_screen_pos(at(0,40))
        im.invisible_button("##field", (W*scale,(H-80)*scale))
        im.set_item_tooltip(tr("Drag the detector or hold Left/Right or A/D."))
        im.end()


def make_app():
    from chisurf.emtk.i18n import install

    from .translations import install_translations
    install()
    install_translations()
    return BreakoutApp()
