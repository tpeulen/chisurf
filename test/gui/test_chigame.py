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


def test_adjacent_long_wavelength_bands_are_distinguishable():
    """Two bands ~40 nm apart in the red must not render identically.

    Above ~645 nm the hue is pure red and stops changing, so without a
    brightness gradient every wavelength from there to 780 came out the same
    colour -- which showed up as the bottom two rows of the breakout spectrum
    being indistinguishable. Regression for the steeper rolloff.
    """
    near = chigame.wavelength_to_srgb(640.0)
    far = chigame.wavelength_to_srgb(680.0)
    assert abs(near[0] - far[0]) > 0.08, (near, far)


def test_the_spectrum_runs_violet_to_red():
    """`spectral_band` spans the visible range in the documented direction."""
    from chisurf.gui.chigame.assets import spectral_band

    assert spectral_band(0.0) < spectral_band(0.5) < spectral_band(1.0)
    violet = chigame.wavelength_to_srgb(spectral_band(0.0))
    red = chigame.wavelength_to_srgb(spectral_band(1.0))
    assert violet[2] > violet[1], "the short-wavelength end must be blue-violet"
    assert red[0] > red[1] and red[0] > red[2], "the long end must be red"


def test_photon_energy_ranks_violet_above_red():
    """Energy goes as 1/lambda, so shorter is more energetic -- and non-linear.

    Games rank difficulty by this, so "bluer" and "harder" have to coincide.
    """
    from chisurf.gui.chigame.assets import photon_energy_rank

    assert photon_energy_rank(405.0) > photon_energy_rank(550.0) > photon_energy_rank(680.0)
    # Energy goes as 1/lambda, which compresses the ranks toward the long-
    # wavelength end: the *midpoint wavelength* sits well below the midpoint
    # energy (0.373, not 0.5). A linear sweep of wavelength is therefore not a
    # linear sweep of energy, which is exactly why the ranking is computed
    # rather than assumed.
    assert photon_energy_rank(0.5 * (405.0 + 680.0)) < 0.5


def test_a_halo_never_outshines_its_source():
    """The spill of light around an emitter stays under the emitter itself."""
    pack = chigame.ProceduralPack()
    core = pack.resolve("photon", "probe", emission_nm=520.0)
    halo = pack.resolve("photon", "halo", emission_nm=520.0)
    assert halo.color[3] < core.color[3]
    assert halo.scale > core.scale, "a halo has to be wider than what it surrounds"


def test_capture_reports_a_failing_draw_instead_of_an_empty_frame(gpu, qapp):
    """A game whose draw raises must surface that error, not a shape puzzle.

    The canvas catches whatever the draw callback raises and only logs it, then
    returns an empty frame -- so the real error used to appear much later as an
    IndexError on a 0-dimensional array, somewhere unrelated.
    """

    class Broken(_Solid):
        def draw(self, scene):
            """Fail deliberately.

            Parameters
            ----------
            scene : chisurf.gui.chigame.scene.Scene
                Ignored.
            """
            raise ValueError("deliberate failure inside draw")

    with pytest.raises(ValueError, match="deliberate failure inside draw"):
        chigame.capture(Broken(), size=(32, 32), with_text=False)
