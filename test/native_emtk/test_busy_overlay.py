"""Every tool in the shell waits behind a blur with a progress bar: the overlay reads the tools' own conventions."""

from __future__ import annotations

from types import SimpleNamespace

from emtk.testing import RecordingPainter

from chisurf.emtk.busy_overlay import BusyOverlay, busy_state


def test_idle_tools_and_live_views_have_no_overlay():
    assert busy_state(SimpleNamespace(running=False)) is None
    assert busy_state(SimpleNamespace(running=True, busy_overlay=False)) is None


def test_progress_message_and_stop_are_read_from_the_tool():
    stopped = []
    app = SimpleNamespace(
        controller=SimpleNamespace(running=True, progress=(3, 4), stop=lambda: stopped.append(1)),
        job=SimpleNamespace(busy=False, progress="Fitting bursts…"),
    )
    state = busy_state(app)
    assert state.fraction == 0.75 and state.message == "Fitting bursts…"
    state.stop()
    assert stopped == [1]


def test_a_hub_is_busy_when_its_current_step_is():
    step = SimpleNamespace(job=SimpleNamespace(busy=True, progress="Searching 1 file(s) ..."))
    state = busy_state(SimpleNamespace(child=step))
    assert state is not None and state.message.startswith("Searching")


def test_the_overlay_shows_after_the_delay_swallows_presses_and_stops():
    stopped = []
    app = SimpleNamespace(running=True, stop=lambda: stopped.append(1))
    overlay = BusyOverlay(delay_s=0.5)
    assert not overlay.update(app, now=10.0)  # a short job never flickers a card
    assert not overlay.press(5, 5)
    assert overlay.update(app, now=10.6)
    painter = RecordingPainter()
    overlay.draw(painter, (0, 0, 800, 600), now=10.6)
    assert "Stop" in painter.strings and overlay.stop_rect is not None
    assert overlay.press(1, 1) and not stopped  # beside Stop: swallowed, nothing stopped
    x, y, w, h = overlay.stop_rect
    assert overlay.press(x + w / 2, y + h / 2) and stopped == [1]
    app.running = False
    assert not overlay.update(app, now=11.0) and not overlay.press(5, 5)


def test_a_long_message_wraps_inside_the_card_and_the_bar_moves_down(tmp_path):
    """A slow step's long status (Burst Analysis says which file, detector and stage) is
    folded to the card's width, at most MAX_LINES lines ending in "…", never cut at 60
    characters and never drawn past the card."""
    from emtk.testing import PixelPainter, png_encode

    from chisurf.emtk.busy_overlay import MAX_LINES, message_lines

    message = (
        "Burst MLE: fitting 15693 bursts of m000.spc … m010.spc, detector G|G and R|R, "
        "IRF from the scatter measurement, background from the photons outside the bursts; "
        "the decays are binned by the setup's micro-time binning."
    )
    tool = SimpleNamespace(running=True, progress_fraction=0.4, job=SimpleNamespace(progress=message),
                           stop=lambda: None)
    overlay = BusyOverlay(delay_s=0.0)
    assert overlay.update(tool, now=1.0)
    painter = PixelPainter(800, 500)
    overlay.draw(painter, (0, 0, 800, 500), now=2.0)
    lines = message_lines(painter, message, 380 - 28)
    assert 2 < len(lines) <= MAX_LINES
    assert all(painter.text_width(line) <= 380 - 28 + 0.5 for line in lines)
    assert " ".join(lines).replace("  ", " ").startswith("Burst MLE: fitting 15693 bursts")
    sx, sy, sw, sh = overlay.stop_rect
    assert sy > 250 - 62 + 18 * (len(lines) - 1)  # under the text, inside the card
    (tmp_path / "busy_long.png").write_bytes(png_encode(painter.width, painter.height, painter.px))
    short = message_lines(painter, "x " * 400, 352)
    assert len(short) == MAX_LINES and short[-1].endswith("…")
