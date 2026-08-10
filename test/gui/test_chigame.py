"""The chigame engine renders, and its seams hold.

These run headlessly through ``rendercanvas.offscreen``, so they need no window
server -- but they do need a GPU adapter, and they skip rather than fail where
there is none.

The point of the render assertions is not that pixels changed: it is that the
*specific* things drawn are where and what they should be. A test that only
checks "the frame is not empty" passes a game drawing one white rectangle.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402


@pytest.fixture(scope="module")
def gpu():
    """Skip the module when no graphics adapter is available.

    Returns
    -------
    object
        The shared device.
    """
    try:
        return chigame.get_device()
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")


class _Solid(chigame.Game):
    """Fills a known rectangle with a known colour."""

    background = (0.0, 0.0, 0.0, 1.0)

    def update(self, dt, keys):
        """Do nothing; this game is static.

        Parameters
        ----------
        dt : float
            Ignored.
        keys : chisurf.gui.chigame.input.InputMap
            Ignored.
        """

    def draw(self, scene):
        """Draw one red square covering the middle of the view.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        """
        scene.camera.height = 100.0
        scene.draw("ui", "block", at=(0.0, 0.0), size=(50.0, 50.0), color=(1.0, 0.0, 0.0, 1.0))


def test_capture_returns_an_rgba_frame(gpu, qapp):
    """A headless capture yields pixels of the requested size."""
    frame = chigame.capture(_Solid(), size=(120, 80), with_text=False)
    assert frame.shape == (80, 120, 4)
    assert frame.dtype == np.uint8


def test_the_drawn_square_lands_where_it_was_asked_to(gpu, qapp):
    """The centre is red and the corners are background."""
    frame = chigame.capture(_Solid(), size=(200, 200), with_text=False)
    centre = frame[100, 100, :3].astype(int)
    corner = frame[4, 4, :3].astype(int)
    assert centre[0] > 180 and centre[1] < 60 and centre[2] < 60, centre
    assert corner.sum() < 30, corner


def test_background_clear_colour_is_not_washed_out(gpu, qapp):
    """An sRGB clear colour survives the sRGB target without brightening.

    The colour attachment is an sRGB format. Handing it an sRGB value directly
    renders the background visibly too bright, which is easy to miss by eye and
    trivial to pin here.
    """

    class Grey(_Solid):
        background = (0.5, 0.5, 0.5, 1.0)

        def draw(self, scene):
            """Draw nothing, so only the clear colour is visible.

            Parameters
            ----------
            scene : chisurf.gui.chigame.scene.Scene
                Frame under construction.
            """

    frame = chigame.capture(Grey(), size=(32, 32), with_text=False)
    assert 118 <= int(frame[16, 16, 0]) <= 138, frame[16, 16]


def test_wavelength_colour_follows_the_spectrum():
    """Emission wavelength maps to a plausible sRGB colour.

    This is the default pack's whole art direction, so it is worth pinning that
    blue is blue and red is red rather than trusting the piecewise ramp.
    """
    blue = chigame.wavelength_to_srgb(450.0)
    green = chigame.wavelength_to_srgb(520.0)
    red = chigame.wavelength_to_srgb(660.0)
    assert blue[2] > blue[0] and blue[2] > blue[1]
    assert green[1] > green[0] and green[1] > green[2]
    assert red[0] > red[1] and red[0] > red[2]


def test_wavelengths_outside_vision_stay_visible():
    """Out-of-range wavelengths clamp rather than fading to black.

    An invisible creature is a bug, not a feature.
    """
    for nm in (200.0, 900.0):
        assert sum(chigame.wavelength_to_srgb(nm)) > 0.2


def test_an_explicit_colour_overrides_the_palette():
    """A ``color`` hint wins for every kind.

    Regression: the ``ui`` branch silently dropped it, which turned every pong
    paddle and spark white while the game code looked correct.
    """
    pack = chigame.ProceduralPack()
    for kind, name in (("ui", "panel"), ("ui", "spark"), ("ui", "unknown"), ("tile", "grass")):
        look = pack.resolve(kind, name, color=(0.25, 0.5, 0.75, 1.0))
        assert look.color == (0.25, 0.5, 0.75, 1.0), (kind, name, look.color)


def test_input_reports_press_release_and_axis():
    """The abstract controller distinguishes held from just-pressed."""
    keys = chigame.InputMap()
    keys.press(Action.RIGHT)
    assert keys.just_pressed(Action.RIGHT) and keys.is_held(Action.RIGHT)
    assert keys.axis() == (1.0, 0.0)

    keys.press(Action.RIGHT)
    assert keys.just_pressed(Action.RIGHT), "auto-repeat must not re-fire a press"

    keys.end_frame()
    assert not keys.just_pressed(Action.RIGHT)
    assert keys.is_held(Action.RIGHT)

    keys.release(Action.RIGHT)
    assert keys.just_released(Action.RIGHT)
    assert keys.axis() == (0.0, 0.0)


def test_down_is_positive_y():
    """The pad's Y matches the camera's world convention.

    Getting this backwards flips every game vertically, which no assertion
    about pixel counts would catch.
    """
    keys = chigame.InputMap()
    keys.press(Action.DOWN)
    assert keys.axis()[1] == 1.0


def test_camera_round_trips_screen_and_world():
    """Picking depends on these being exact inverses."""
    camera = chigame.Camera(center=(10.0, -4.0), height=80.0)
    size = (640, 480)
    for point in ((10.0, -4.0), (30.0, 12.0), (-25.0, -30.0)):
        back = camera.screen_to_world(camera.world_to_screen(point, size), size)
        assert back == pytest.approx(point, abs=1e-3)


def test_audio_degrades_silently_without_multimedia():
    """A missing Qt multimedia module must not stop a game running."""
    audio = chigame.Audio(chigame.ProceduralPack(), enabled=False)
    audio.set_context("battle")
    audio.sfx("ping")
    audio.stop()
    assert audio.enabled is False


def test_every_music_context_has_a_track():
    """The default pack answers for each context a game may set."""
    pack = chigame.ProceduralPack()
    from chisurf.gui.chigame.audio import CONTEXTS

    for context in CONTEXTS:
        assert pack.music_track(context) is not None, context


def test_a_track_synthesises_to_audible_samples():
    """Note data becomes non-silent PCM of a sane length."""
    from chisurf.gui.chigame.audio import SAMPLE_RATE, render_track

    pcm = render_track(chigame.ProceduralPack().music_track("overworld"))
    samples = np.frombuffer(pcm, dtype="<i2")
    assert len(samples) > SAMPLE_RATE // 2
    assert int(np.abs(samples).max()) > 3000
