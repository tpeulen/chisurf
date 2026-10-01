"""Qt-free tests for the ChiMOL EMTK host adapter.

Imported by absolute path: chimol's conftest loads this suite's modules
outside the chisurf package, so relative imports cannot resolve here.
"""

from __future__ import annotations

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.chimol.app import ChimolHostApp, make_app


@pytest.fixture
def app():
    app = make_app()
    app.draw(RecordingPainter(), 0, 0, 900, 620)
    if app._chimol_error:
        pytest.skip(f"chimol unavailable: {app._chimol_error}")
    return app


def test_native_embeds_chimol_offscreen_renderer(app):
    assert app._chimol is not None
    assert app._frame is not None
    assert app._frame.ndim == 3 and app._frame.shape[2] == 4


def test_native_renders_frame_into_surface(app):
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 900, 620)
    # The adapter blits the chimol frame through im.image (recorded as an
    # operation, not text); the surface itself draws without error.
    assert any(call[0] in ("image", "fill_rect", "text") for call in painter.calls)


def test_native_input_forwarding(app):
    renderer = app._chimol.renderer
    # The forwarded handlers exist and accept the emtk event shapes.
    app.pointer_press(100, 100, 0)
    app.pointer_move(110, 105, 1)
    app.pointer_release(110, 105, 0)
    app.wheel(100, 100, 1)
    app.key(0, "r")
    assert callable(renderer.on_pointer_press)


def test_native_close_shuts_chimol_down(app):
    app.close()
    assert app._chimol is None


def test_native_resize_rerenders_at_the_window_size(app):
    """Growing the hosted window re-renders chimol at the new size.

    The failing sequence this replays: the window opens (900x620), the user
    drags its edge wider. `renderer.on_resize` alone resized nothing -- its
    offscreen canvas kept answering 900x620 and every later frame was the
    old picture stretched by the blit, so orbiting drew a squashed molecule.
    The canvas must grow (`set_logical_size`) for the renderer's viewport to
    mean anything.
    """
    canvas = app._chimol.renderer._canvas
    app.draw(RecordingPainter(), 0, 0, 1400, 900)
    logical = canvas.get_logical_size()
    assert (int(logical[0]), int(logical[1])) == (1400, 900 - ChimolHostApp.STATUS_H)
    assert app._frame.shape == (900 - ChimolHostApp.STATUS_H, 1400, 4)
    # and back down again, the direction the 760 px clamp exercises
    app.draw(RecordingPainter(), 0, 0, 700, 500)
    logical = canvas.get_logical_size()
    assert (int(logical[0]), int(logical[1])) == (760, 500 - ChimolHostApp.STATUS_H)


def test_native_playback_advances_without_input(app):
    """A playing movie advances while the host draws, no pointer events.

    chimol's clock runs inside its frame draw (`Playback.pump`), so an
    embedded host only advances the movie if the host keeps asking for
    frames. `animating()` is the emtk contract `ControlHost.paintEvent` uses
    to do exactly that; it never reflected chimol's playing state, so the
    movie moved only while the pointer kept producing events.
    """
    viewer = app._chimol.viewer
    viewer.set_total_frames(100)
    try:
        viewer.playback.play(1)  # 1 ms: every draw is due
        assert app.animating(), "a playing movie must read as animating"
        positions = [viewer.get_frame_position()]
        for _ in range(10):
            app.draw(RecordingPainter(), 0, 0, 1200, 800)
            positions.append(viewer.get_frame_position())
        assert positions[-1] > positions[0], f"never advanced: {positions}"
        # and the host goes back to sleep when the movie pauses
        viewer.playback.pause()
        assert not app.animating()
    finally:
        viewer.playback.pause()


def test_native_mplay_from_a_command_wakes_the_host(app):
    """`mplay` typed at the console (or the ▶ button) starts the movie.

    Replays the reported failure: the play command runs no input event, and
    chimol's own wake (`update()` -> `request_draw`) knocks on the
    rendercanvas loop, which is not running inside this embed -- so nothing
    ever drew, the animating() chain never started, and the movie sat at
    frame 0 until the user wiggled the mouse. The host now subscribes to
    `command.executed` and asks for a frame; that frame's animating() check
    takes over.
    """
    viewer = app._chimol.viewer
    viewer.set_total_frames(100)
    try:
        app._chimol.cmd.do("mplay")
        assert app.wants_frame, "a command that starts a movie must wake the host"
        assert app.animating()
    finally:
        viewer.playback.pause()


def test_native_qt_blocked_factory():
    """The factory import path never needs a QApplication."""
    import subprocess
    import sys

    code = (
        "import sys;"
        "from chisurf.plugins.chimol.app import make_app;"
        "app = make_app();"
        "app._ensure_chimol();"
        "print('OK' if app._chimol is not None or app._chimol_error else 'FAIL')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env={"CHIMOL_TOOLKIT": "none", "PATH": "/usr/bin:/bin"},
    )
    # A clean headless machine may lack wgpu/rendercanvas; both a built viewer
    # and a recorded load error are acceptable, a Qt abort is not.
    assert "Must construct a QApplication" not in proc.stderr
