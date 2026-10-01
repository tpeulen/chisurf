"""Standalone EMTK Number Quest surface."""
from __future__ import annotations

import math

from emtk import i18n, im
from emtk.app import ImApp
from emtk.keys import KEY_ENTER, KEY_LEFT, KEY_RETURN, KEY_RIGHT

from ..core.game import GuessStatus, NumberQuestGame
from .translations import install_translations

install_translations()

NS_PER_UNIT = 0.1


def tr(text: str) -> str:
    return i18n.tr(text, context="Number Quest")


class NumberQuestApp(ImApp):
    """Keyboard-driven lifetime estimate game using the shared pure rules."""

    def __init__(self, target: int | None = None) -> None:
        self.game = NumberQuestGame(target=target)
        self.estimate = 50
        self.history: list[int] = []
        self.message = tr("Dial an estimate, then confirm.")
        self.closed = False
        super().__init__(self.render)

    @property
    def tau(self) -> float:
        return self.estimate * NS_PER_UNIT

    def new_round(self) -> None:
        self.game.reset()
        self.estimate = 50
        self.history.clear()
        self.message = tr("Dial an estimate, then confirm.")
        self.request_frame()

    def _nudge(self, amount: int) -> None:
        self.estimate = min(max(self.estimate + amount, 1), 100)
        self.request_frame()

    def key(self, key, text="", modifiers=0) -> bool:
        if modifiers or self.closed:
            return False
        value = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        if key == KEY_LEFT or value == "a":
            self._nudge(-1)
        elif key == KEY_RIGHT or value == "d":
            self._nudge(1)
        elif value == "q":
            self._nudge(-10)
        elif value == "e":
            self._nudge(10)
        elif key in (KEY_ENTER, KEY_RETURN) or value == " ":
            self.submit()
        elif value == "r":
            self.new_round()
        else:
            return False
        return True

    def key_release(self, key, text="", modifiers=0) -> bool:
        return False

    def submit(self) -> None:
        if self.game.status is not GuessStatus.ACTIVE:
            self.new_round()
            return
        self.history.append(self.estimate)
        result = self.game.guess(self.estimate)
        self.message = tr(result.message.replace("Higher", "Longer lifetime").replace("Lower", "Shorter lifetime"))
        self.request_frame()

    def close(self) -> None:
        self.closed = True

    def _curve(self, x: float, y: float, width: float, height: float) -> None:
        im.get_current_context().draw.add_rect_filled((x, y), (x + width, y + height), (25, 30, 38, 255), 2)
        points = []
        for index in range(70):
            t = 10.0 * index / 69.0
            intensity = math.exp(-t / max(self.tau, 0.1))
            points.append((x + width * index / 69.0, y + height * (1.0 - intensity)))
        for a, b in zip(points, points[1:]):
            im.get_current_context().draw.add_line(a, b, (70, 220, 205, 255), 2)

    def render(self) -> None:
        available = im.get_content_region_avail()
        width = max(300.0, min(520.0, float(available[0])))
        plot_width = max(240.0, width - 48.0)
        im.begin(tr("Number Quest"), (0, 0, width, 620))
        im.heading(tr("LIFETIME ESTIMATION"), level=2)
        im.text_disabled(f"{tr('Turns left')}: {self.game.attempts_remaining}    {tr('Score')}: {self.game.score}")
        self._curve(24, 86, plot_width, 190)
        im.text_colored((80, 220, 205, 255), f"{self.tau:.1f} ns")
        im.text_wrapped(self.message)
        im.separator()
        im.text(tr("Estimate"))
        im.same_line()
        im.text_colored((230, 230, 240, 255), str(self.estimate))
        for label, amount, tip in (("−10", -10, "Decrease the estimate by ten units"), ("−1", -1, "Decrease the estimate by one unit"), ("+1", 1, "Increase the estimate by one unit"), ("+10", 10, "Increase the estimate by ten units")):
            im.same_line()
            if im.button(label):
                self._nudge(amount)
            im.set_item_tooltip(tr(tip))
        if im.button(tr("Confirm")):
            self.submit()
        im.set_item_tooltip(tr("Submit the current lifetime estimate"))
        im.same_line()
        if im.button(tr("New round")):
            self.new_round()
        im.set_item_tooltip(tr("Start a fresh round"))
        help_text = tr("Left/Right dial · Q/E coarse · Enter confirm · R reset")
        im.text_wrapped(help_text)
        im.end()


def make_app() -> NumberQuestApp:
    return NumberQuestApp()
