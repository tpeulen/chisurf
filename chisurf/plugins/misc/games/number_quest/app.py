"""Standalone EMTK lifetime estimation game, with the unchanged pure rules."""
from __future__ import annotations

import math
import time

from emtk import i18n, im
from emtk.app import ImApp
from emtk.keys import KEY_ENTER, KEY_LEFT, KEY_RETURN, KEY_RIGHT

from .core.game import GuessStatus, NumberQuestGame
from .drawing import pixel_text, text_width

NS_PER_UNIT = .1
VIEW_W, VIEW_H = 420, 340
PLOT_X, PLOT_Y, PLOT_W, PLOT_H = 40, 96, 340, 120
CURVE_POINTS = 70
REPEAT_DELAY, REPEAT_RATE = .28, .045
STEPS = {"left": -1, "right": 1, "coarse_left": -10, "coarse_right": 10}


def tr(source):
    return i18n.tr(source, context="NumberQuest")


class NumberQuestApp(ImApp):
    window_size = (560, 420)

    def __init__(self, audio=None, clock=time.monotonic):
        self.game = NumberQuestGame()
        self.estimate = 50
        self.history = []
        self.hint = "initial"
        self.held = set()
        self.repeat = {}
        self.closed = False
        self.audio = audio
        self.sound_enabled = False
        self.clock, self.last_frame = clock, None
        self.board = (0, 34, 1)
        super().__init__(self.render)

    @property
    def window_title(self):
        return tr("Number Quest")

    @property
    def tau(self):
        return self.estimate * NS_PER_UNIT

    @property
    def message(self):
        source = {"initial": "Dial an estimate, then confirm.", "higher": "Longer lifetime.", "lower": "Shorter lifetime.", "won": "You found it! The number was {target}.", "lost": "Out of turns — the number was {target}."}[self.hint]
        return tr(source).format(target=self.game.target)

    def new_round(self):
        self.game.reset()
        self.estimate, self.history, self.hint = 50, [], "initial"
        self.repeat.clear()
        self.request_frame()

    def _nudge(self, step):
        self.estimate = min(max(self.estimate + step, self.game.minimum), self.game.maximum)
        self.request_frame()

    def submit(self):
        if self.closed:
            return
        if self.game.status is not GuessStatus.ACTIVE:
            self.new_round()
            return
        self.history.append(self.estimate)
        self.game.guess(self.estimate)
        self.hint = self.game.status.value if self.game.status is not GuessStatus.ACTIVE else "higher" if self.estimate < self.game.target else "lower"
        if self.audio is not None and self.sound_enabled:
            self.audio.sfx("guess", 880 if self.game.status is GuessStatus.WON else 520)
        self.request_frame()

    @staticmethod
    def binding(key, text):
        letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        if key == KEY_LEFT:
            return "left"
        if key == KEY_RIGHT:
            return "right"
        if key in {KEY_ENTER, KEY_RETURN}:
            return "confirm"
        return {"a": "left", "d": "right", "q": "coarse_left", "e": "coarse_right", "r": "restart", " ": "confirm"}.get(letter)

    def key(self, key, text="", modifiers=0):
        if modifiers or self.closed:
            return False
        action = self.binding(key, text)
        if action is None:
            return False
        if action not in self.held:
            self.held.add(action)
            if action in STEPS:
                self._nudge(STEPS[action])
                self.repeat[action] = -REPEAT_DELAY
            elif action == "confirm":
                self.submit()
            else:
                self.new_round()
        self.request_frame()
        return True

    def key_release(self, key, text="", modifiers=0):
        action = self.binding(key, text)
        self.held.discard(action)
        self.repeat.pop(action, None)
        return action is not None

    def advance(self, dt):
        if self.closed:
            return
        dt = min(max(float(dt), 0), .1)
        for action in self.held & STEPS.keys():
            self.repeat[action] = self.repeat.get(action, -REPEAT_DELAY) + dt
            while self.repeat[action] >= REPEAT_RATE:
                self.repeat[action] -= REPEAT_RATE
                self._nudge(STEPS[action])

    def animating(self):
        return not self.closed and bool(self.held & STEPS.keys())

    def focus_lost(self):
        self.held.clear()
        self.repeat.clear()
        self.last_frame = None
        if self.audio is not None:
            self.audio.set_enabled(False)

    def close(self):
        self.focus_lost()
        self.closed = True
        if self.audio is not None:
            self.audio.close()

    def set_sound(self):
        if self.audio is None:
            return
        self.sound_enabled = not self.sound_enabled
        if self.audio is not None:
            self.audio.set_enabled(self.sound_enabled)

    def _decay_point(self, index, tau):
        t = self.game.maximum * NS_PER_UNIT * index / (CURVE_POINTS - 1)
        return (PLOT_X + PLOT_W * index / (CURVE_POINTS - 1), PLOT_Y + PLOT_H * (1 - math.exp(-t / max(tau, 1e-3))))

    def export_settings(self):
        return {"target": self.game.target, "history": self.history[:], "estimate": self.estimate, "sound_enabled": self.sound_enabled}

    def restore_settings(self, state):
        target, estimate, history = state["target"], state["estimate"], state["history"]
        if not isinstance(history, list):
            raise ValueError("invalid number quest history")
        if any(type(value) is not int or not 1 <= value <= 100 for value in [target, estimate, *history]):
            raise ValueError("invalid number quest values")
        if len(history) > NumberQuestGame.max_attempts or type(state.get("sound_enabled", False)) is not bool:
            raise ValueError("invalid number quest state")
        candidate = NumberQuestGame(target)
        hint = "initial"
        for value in history:
            if candidate.status is not GuessStatus.ACTIVE:
                raise ValueError("history continues after round end")
            candidate.guess(value)
            hint = candidate.status.value if candidate.status is not GuessStatus.ACTIVE else "higher" if value < target else "lower"
        self.game, self.estimate, self.history, self.hint = candidate, estimate, history[:], hint
        self.sound_enabled = state.get("sound_enabled", False)
        self.focus_lost()
        self.request_frame()

    def render(self):
        now = self.clock()
        if self.last_frame is not None:
            self.advance(now - self.last_frame)
        self.last_frame = now
        viewport = im.get_main_viewport()
        x, y = viewport.pos
        w, h = viewport.size
        im.begin("##number-quest", (x, y, w, h))
        draw = im.get_window_draw_list()
        draw.add_rect_filled((x, y), (x+w, y+h), (8, 9, 11, 255))
        draw.add_rect_filled((x, y), (x+w, y+34), (239,239,239,255))
        draw.add_rect_filled((x+4, y+2), (x+82, y+31), (173,173,173,255), rounding=2)
        draw.add_rect_filled((x+5, y+3), (x+81, y+30), (248,248,248,255), rounding=2)
        im.push_font_scale(1.4)
        label = tr("Sound")
        label_w, label_h = draw.calc_text_size(label)
        # Greyed without an audio backend: emtk plays no sound (the Qt game's
        # chigame audio is QtMultimedia), and a switch that changes nothing
        # must not look like one that works.
        ink = (0, 0, 0, 255) if self.audio is not None else (150, 150, 150, 255)
        draw.add_text((x+43-label_w/2, y+16.5-label_h/2), ink, label)
        im.pop_font_scale()
        im.set_cursor_screen_pos((x+4, y+2))
        if im.invisible_button("##sound", (78,29)) and self.audio is not None:
            self.set_sound()
        im.set_item_tooltip(tr("Music and sound effects (off by default).") if self.audio is not None
                            else tr("No sound here: this window has no audio output."))
        scale = min(w / VIEW_W, max(h-34, 1) / VIEW_H)
        ox, oy = x+(w-VIEW_W*scale)/2, y+34+(h-34-VIEW_H*scale)/2
        self.board = (ox, oy, scale)
        def at(xx, yy):
            return ox+xx*scale, oy+yy*scale
        def text(label, yy, height, color=(199,209,224,255)):
            height *= scale
            width = text_width(draw, label, height)
            if width > w-20:
                height *= max(w-20, 1)/width
            pixel_text(draw, label, at(VIEW_W/2, yy), height, color, "center")
        text(tr("LIFETIME ESTIMATION"), 30, 15)
        text(tr("Turns left: {turns}    Score: {score}").format(turns=self.game.attempts_remaining, score=self.game.score), 52, 11, (112,122,140,255))
        draw.add_rect_filled(at(PLOT_X-.75, PLOT_Y), at(PLOT_X+.75, PLOT_Y+PLOT_H), (77,84,97,150))
        draw.add_rect_filled(at(PLOT_X, PLOT_Y+PLOT_H-.75), at(PLOT_X+PLOT_W, PLOT_Y+PLOT_H+.75), (77,84,97,150))
        for past in self.history[:-1]:
            for index in range(CURVE_POINTS):
                xx, yy = self._decay_point(index, past * NS_PER_UNIT)
                draw.add_rect_filled(at(xx-.8, yy-.8), at(xx+.8, yy+.8), (77,87,102,135))
        for index in range(CURVE_POINTS):
            xx, yy = self._decay_point(index, self.tau)
            # Original chigame photon: 2.6-unit sample, enlarged 2.6x,
            # with radial coverage (1-r)^1.68. Concentric coverage layers
            # reproduce its soft optical halo on the EMTK draw list.
            previous = 0
            for ring in range(12, 0, -1):
                fraction = (ring-.5)/12
                coverage = (1-fraction)**1.68
                alpha = (coverage-previous)/(1-previous)
                draw.add_circle_filled(at(xx, yy), 3.38*fraction*scale, (0,255,255,round(alpha*255)))
                previous = coverage
        text(f"{self.tau:.1f} ns", 242, 26, (89,217,204,255))
        text(self.message, 272, 12)
        controls = ((306, "Left/Right  dial      L/R  coarse", "Hold Left/Right or A/D for fine steps; Q/E for steps of ten.", None), (324, "Confirm  submit      Cancel  new round", "Submit with Enter/Space. Start a new round with R.", "submit"))
        for yy, label, tip, action in controls:
            text(tr(label), yy, 11, (112,122,140,255))
            im.set_cursor_screen_pos(at(10, yy-9))
            if im.invisible_button("##"+str(yy), (400*scale, 18*scale)) and action:
                # Left half submits; right half restarts, matching the captions.
                if self.io.mouse_pos[0] < ox+VIEW_W/2*scale:
                    self.submit()
                else:
                    self.new_round()
            im.set_item_tooltip(tr(tip))
        # The plot is a mouse dial without covering or changing its visual geometry.
        im.set_cursor_screen_pos(at(PLOT_X, PLOT_Y))
        if im.invisible_button("##dial", (PLOT_W*scale, PLOT_H*scale)):
            ratio = (self.io.mouse_pos[0] - ox-PLOT_X*scale)/(PLOT_W*scale)
            self.estimate = min(max(round(1+99*ratio), 1), 100)
        im.set_item_tooltip(tr("Click the plot to dial a lifetime between 0.1 and 10.0 ns."))
        im.end()


def make_app(audio=None):
    """The game; *audio* is an object with ``sfx``/``set_enabled``/``close`` (none in emtk yet)."""
    from chisurf.emtk.i18n import install

    from .translations import install_translations
    install()
    install_translations()
    return NumberQuestApp(audio=audio)
