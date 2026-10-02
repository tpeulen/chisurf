"""Helpers for driving an imaging emtk app with simulated pointer and keyboard events.

``Driver`` presses, drags, types and drops at the rectangles the controls were drawn in -- nothing calls a model
method to "click". The painter measures text as the screenshot painter does (so a hit lands where the screenshot
shows the control) without rasterising, which would cost seconds a frame.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from emtk import keys
from emtk.testing import PixelPainter, RecordingPainter

_METRICS = None


def _metrics() -> PixelPainter:
    global _METRICS
    if _METRICS is None:
        _METRICS = PixelPainter(8, 8)
    return _METRICS


class MetricPainter(RecordingPainter):
    """Records like :class:`RecordingPainter`, measures like :class:`PixelPainter`."""

    def text_width(self, string) -> float:
        return _metrics().text_width(string)

    def line_height(self) -> float:
        return _metrics().line_height()

    def set_font_scale(self, scale: float) -> None:
        super().set_font_scale(scale)
        _metrics().set_font_scale(scale)


class Driver:
    """Operate *app* the way a person does, one event at a time."""

    def __init__(self, app: Any, size: tuple[int, int] = (1000, 700)) -> None:
        self.app = app
        self.size = size
        self.painter: MetricPainter | None = None

    # -- frames --------------------------------------------------------------- #
    def draw(self, frames: int = 2, size: tuple[int, int] | None = None) -> MetricPainter:
        w, h = size or self.size
        for _ in range(frames):
            self.painter = MetricPainter()
            self.app.draw(self.painter, 0, 0, w, h)
        return self.painter

    def settle(self, timeout: float = 120.0, extra: int = 2) -> MetricPainter:
        """Draw until the worker has finished and its result is shown."""
        end = time.monotonic() + timeout
        self.draw(1)
        while (self.app.job.busy or self.app.model.busy) and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        assert not self.app.job.busy, "the worker did not finish"
        return self.draw(extra)

    def strings(self) -> list[str]:
        return list(self.draw(1).strings)

    # -- locating -------------------------------------------------------------- #
    def rect(self, name: str) -> tuple:
        """The rectangle a control was drawn in: a form field/action, a stepper (``attr.stepper``) or a view."""
        self.draw(1)
        found = self.app.form.rects.get(name) or self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.form.rects)[:40]} {sorted(self.app.item_rects)[:40]}"
        return tuple(found)

    def text_rect(self, label: str, last: bool = False) -> tuple:
        """The rectangle of the drawn text *label* (a button caption, a list entry, a header)."""
        hits = [t[:4] for t in self.draw(1).texts if t[5] == label]
        assert hits, f"{label!r} is not drawn: {[t[5] for t in self.painter.texts][:60]}"
        return hits[-1] if last else hits[0]

    # -- pointer ---------------------------------------------------------------- #
    def click_at(self, x: float, y: float, frames: int = 1) -> None:
        self.app.press(x, y)
        self.draw(frames)
        self.app.release()
        self.draw(frames)

    def reveal(self, name: str) -> tuple:
        """The rectangle of *name*, scrolling its window with the wheel until the control is on screen."""
        for _ in range(12):
            x, y, w, h = self.rect(name)
            if y < 0 or y + h > self.size[1] - 4:
                self.wheel(x + w / 2, min(max(y, 40), self.size[1] - 40), -3 if y > 0 else 3)
            else:
                break
        return self.rect(name)

    def click(self, target: Any, fx: float = 0.5, fy: float = 0.5) -> None:
        """Press and release at a point of the control's rectangle (a name, scrolled to if need be, or a rectangle)."""
        x, y, w, h = self.reveal(target) if isinstance(target, str) else target
        self.click_at(x + w * fx, y + h * fy)

    def click_text(self, label: str, last: bool = False) -> None:
        self.click(self.text_rect(label, last))

    def drag(self, start: tuple[float, float], end: tuple[float, float], steps: int = 6) -> None:
        """Press at *start*, move to *end* in *steps* moves (a frame each), release."""
        self.app.pointer_move(*start)
        self.draw(1)
        self.app.press(*start)
        self.draw(1)
        for i in range(1, steps + 1):
            f = i / steps
            self.app.pointer_move(start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f, 1)
            self.draw(1)
        self.app.release()
        self.draw(1)

    def wheel(self, x: float, y: float, notches: float) -> None:
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.wheel(x, y, notches)
        self.draw(1)

    def hover(self, x: float, y: float, frames: int = 3) -> None:
        self.app.pointer_move(x, y)
        self.draw(frames)

    # -- keyboard ---------------------------------------------------------------- #
    def key(self, code: int, text: str = "", modifiers: int = 0) -> None:
        self.app.key(code, text, modifiers)
        self.draw(1)

    def type_text(self, text: str) -> None:
        for ch in text:
            self.key(ord(ch), ch)

    def enter(self) -> None:
        self.key(keys.KEY_RETURN, "\r")

    def escape(self) -> None:
        self.key(keys.KEY_ESCAPE, "")

    def select_all(self) -> None:
        self.key(0x41, "a", 0x04000000)

    def type_into(self, name: str, text: str, enter: bool = True) -> None:
        """Click the field, replace its content with *text*, press Enter."""
        self.click(name, fx=0.3)
        assert self.app.io.want_capture_keyboard, f"{name} did not take the keyboard"
        self.select_all()
        self.type_text(text)
        if enter:
            self.enter()

    # -- files ---------------------------------------------------------------------- #
    def drop(self, *paths: str) -> bool:
        """Files dropped on the window, delivered as a host delivers them."""
        from emtk.app import ControlSurface

        result = ControlSurface(self.app).on_files_dropped([str(p) for p in paths])
        self.draw(2)
        return bool(result)


def walk(sections):
    """Every section of a spec, depth first."""
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def dialog_open(drv: Driver) -> bool:
    """Whether a file dialog is on screen (its caption is the window title, which the painter does not draw)."""
    return "Cancel" in drv.draw(1).strings and drv.app.dialog is not None


def numeric_ticks(painter) -> list[str]:
    """The numeric axis labels a frame drew (they change when a plot is panned or zoomed)."""
    return [t for t in painter.strings if t.lstrip("-\u2212").replace(".", "").isdigit()]


def hermetic_env(tmp_path, monkeypatch) -> None:
    """Settings, MMFDB and its database into a temporary folder; the user's own are never touched."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
