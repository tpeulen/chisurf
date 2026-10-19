"""The terminal control: the drawn terminal, driven without a PTY.

The control's engine seam is one object with the screen's read surface
(``screen``, ``write``, ``resize``, ``alive``), so these tests plug in a fake
session over a real
:class:`~chisurf.plugins.core.terminal.screen.TerminalScreen` and drive the
control through emtk's real input path (:class:`emtk.testing.Driver`).
"""

from __future__ import annotations

import pytest
from emtk.events import CONTROL_MODIFIER
from emtk.keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import Driver, RecordingPainter

pytest.importorskip("emtk")

from chisurf.plugins.core.terminal.control import TerminalControl
from chisurf.plugins.core.terminal.screen import TerminalScreen


class FakeSession:
    """A session that only records writes (the engine seam, fake)."""

    def __init__(self, columns=80, rows=24):
        self.screen = TerminalScreen(columns, rows)
        self.written: list[bytes] = []
        self.resized: list[tuple[int, int]] = []
        self.alive = True

    def write(self, data):
        self.written.append(bytes(data))

    def resize(self, columns, rows):
        self.resized.append((int(columns), int(rows)))
        self.screen.resize(columns, rows)

    def close(self):
        self.alive = False


def make(size=(520, 260)):
    session = FakeSession()
    driver = Driver(TerminalControl(session), size)
    return session, driver.app, driver


def typed(session) -> bytes:
    return b"".join(session.written)


# ── drawing ───────────────────────────────────────────────────────────────


def test_draw_renders_the_screen_text():
    session, control, driver = make()
    driver.draw(2)  # the first frame fits the grid to the box
    session.screen.feed("hello\r\nworld")
    driver.draw(1)
    strings = [str(s) for s in driver.painter.strings]
    assert "hello" in strings and "world" in strings


def test_draw_renders_coloured_runs():
    session, control, driver = make()
    driver.draw(2)
    session.screen.feed("\x1b[31mred\x1b[0m plain")
    driver.draw(1)
    assert "red" in [str(s) for s in driver.painter.strings]


def test_dead_session_draws_its_exit():
    session, control, driver = make()
    driver.draw(2)
    session.alive = False
    session.screen.feed("[process exited]")
    driver.draw(1)
    joined = " ".join(str(s) for s in driver.painter.strings)
    assert "[process exited]" in joined
    assert "— process exited —" in joined  # the control's own notice too


def test_new_output_sustains_frames_until_drawn():
    session, control, driver = make()
    driver.draw(2)
    assert control.animating() is False
    session.screen.feed("late output")
    assert control.animating() is True
    driver.draw(1)
    assert control.animating() is False


# ── the grid follows the box ─────────────────────────────────────────────


def test_draw_resizes_the_grid_to_the_box():
    session, control, driver = make()
    driver.draw(2)
    columns, rows = session.resized[-1]
    assert columns > 60 and rows > 12  # 520x260 at the painter's cell metrics
    control.draw(RecordingPainter(), 0, 0, 1000, 640)
    columns, rows = session.resized[-1]
    assert columns > 100 and rows > 30


# ── keys ─────────────────────────────────────────────────────────────────


def test_typing_writes_utf8_to_the_session():
    session, control, driver = make()
    driver.click((10, 10))  # focus the terminal
    driver.type("ls -l\r")
    assert typed(session) == b"ls -l\r"


def test_arrow_keys_encode_vt_sequences():
    session, control, driver = make()
    driver.click((10, 10))
    for key, escape in ((KEY_UP, b"\x1b[A"), (KEY_DOWN, b"\x1b[B"),
                        (KEY_RIGHT, b"\x1b[C"), (KEY_LEFT, b"\x1b[D")):
        driver.press(key)
        assert typed(session).endswith(escape)


def test_ctrl_letters_encode_control_bytes():
    session, control, driver = make()
    driver.click((10, 10))
    driver.press(ord("c"), mods=CONTROL_MODIFIER)
    assert typed(session).endswith(b"\x03")
    driver.press(ord("d"), mods=CONTROL_MODIFIER)
    assert typed(session).endswith(b"\x04")


def test_ctrl_arrows_encode_modified_sequences():
    session, control, driver = make()
    driver.click((10, 10))
    driver.press(KEY_RIGHT, mods=CONTROL_MODIFIER)
    assert typed(session).endswith(b"\x1b[1;5C")


def test_paste_writes_the_text():
    session, control, driver = make()
    driver.click((10, 10))
    control.paste_text("print(1)\r")
    assert typed(session) == b"print(1)\r"


# ── the wheel ────────────────────────────────────────────────────────────


def test_wheel_scrolls_into_history_and_back():
    session, control, driver = make()
    driver.draw(2)
    for n in range(40):
        session.screen.feed(f"line-{n}\r\n")
    assert control.scroll_offset == 0
    notches = control.screen.max_scroll_offset // 3 + 2
    driver.wheel(notches)  # positive dy scrolls up, into the scrollback
    driver.draw(1)
    assert control.scroll_offset == control.screen.max_scroll_offset
    assert "line-0" in [str(s) for s in driver.painter.strings]
    driver.wheel(-notches)  # down: back to the live view
    driver.draw(1)
    assert control.scroll_offset == 0
    assert "line-39" in [str(s) for s in driver.painter.strings]


# ── selection ────────────────────────────────────────────────────────────


def test_selection_copy_takes_the_range():
    session, control, driver = make()
    driver.draw(2)
    session.screen.feed("alpha beta\r\ngamma delta")
    driver.draw(1)
    top = session.screen.scrollback_lines  # selection coordinates are absolute
    control.select((top, 0), (top, 9))
    assert control.copy_selection() == "alpha beta"


def test_selection_drag_takes_the_pointer_path():
    session, control, driver = make()
    driver.draw(2)
    session.screen.feed("alpha beta")
    driver.draw(1)
    from emtk.events import LEFT_BUTTON

    glyph, line, pad = control._glyph_w, control._line_h, control._pad_x
    surface = driver.surface
    surface.on_pointer_press(pad + 0.5 * glyph, control._pad_y + 0.5 * line,
                             LEFT_BUTTON, 0)
    surface.on_pointer_move(pad + 6.5 * glyph, control._pad_y + 0.5 * line,
                            LEFT_BUTTON, 0)  # buttons held: a drag
    surface.on_pointer_release(pad + 6.5 * glyph, control._pad_y + 0.5 * line,
                               LEFT_BUTTON, 0)
    driver.draw(1)
    assert control.copy_selection() == "alpha b"


# ── close, focus, ime ────────────────────────────────────────────────────


def test_close_is_forwarded():
    session, control, driver = make()
    control.close()
    assert not session.alive


def test_click_focuses_and_draws_the_caret():
    session, control, driver = make()
    session.screen.feed("ab")
    driver.draw(2)
    driver.click((10, 10))
    driver.draw(1)
    assert control.has_focus


def test_ime_caret_is_at_the_cursor():
    session, control, driver = make()
    driver.draw(2)
    driver.draw(1)
    session.screen.feed("ab")
    box = control.ime_caret()
    assert box is not None
    x, y, height = box
    assert abs(x - (control._pad_x + 2 * control._glyph_w)) < 0.01
    assert abs(height - control._line_h) < 0.01


# ── the clipboard ────────────────────────────────────────────────────────


@pytest.fixture
def clip(monkeypatch):
    """The system clipboard, faked: a test must never overwrite the user's."""
    from emtk import clipboard

    held = {"text": ""}
    monkeypatch.setattr(clipboard, "copy", lambda text: held.update(text=text) or True)
    monkeypatch.setattr(clipboard, "paste", lambda: held["text"])
    return held


def test_ctrl_c_with_a_selection_copies_instead_of_interrupting(clip):
    session, control, driver = make()
    driver.draw(2)
    session.screen.feed("alpha beta")
    driver.draw(1)
    top = session.screen.scrollback_lines
    control.select((top, 0), (top, 4))
    driver.press(ord("c"), mods=CONTROL_MODIFIER)
    assert clip["text"] == "alpha"
    assert b"\x03" not in typed(session)
    assert control.selection is None
    driver.press(ord("c"), mods=CONTROL_MODIFIER)  # no selection now: ^C again
    assert typed(session).endswith(b"\x03")


def test_ctrl_v_pastes_the_clipboard_into_the_session(clip):
    session, control, driver = make()
    driver.click((10, 10))
    clip["text"] = "echo hi\nls"
    driver.press(ord("v"), mods=CONTROL_MODIFIER)
    assert typed(session).endswith(b"echo hi\rls")
