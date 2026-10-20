"""How fast the canvas draws, and how it behaves when nothing asks it to.

Two mechanisms live here, both about *cadence* rather than what gets drawn:

``CanvasRenderer.set_max_fps`` re-throttles an already-open window's
frame-rate ceiling by calling straight into ``rendercanvas``'s own
``set_update_mode`` -- the real live-reconfigure API the library exposes for
exactly this, found by reading ``rendercanvas/base.py`` rather than assumed.
Nothing here opens a real GPU window: the renderer's ``_surface()`` is the
seam (it answers ``self`` for a host that *is* a canvas and the held canvas
for one that merely owns one), so a fake surface is enough to prove the right
call happens with the right arguments.

The idle-settle timer is the fix for a distinct, previously-unnoticed bug: an
"ondemand" canvas (both hosts use that update mode) draws nothing once nobody
is interacting, so the fps readout -- computed only from inside a real draw --
freezes at its last value forever rather than reporting the still viewport
honestly. ``_arm_idle_settle`` schedules one follow-up draw past the idle gap
using the codebase's existing host-independent timer
(:class:`chimol.core.toolkit.Timer`, the same clock movie playback and the
cartoon settle-then-bake pass already use), and ``_note_frame_drawn`` makes
sure that one follow-up draw does not rearm itself and free-run forever.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

from chimol.viewport.canvas import _IDLE_GAP, CanvasRenderer


# --------------------------------------------------------------------------- #
# set_max_fps
# --------------------------------------------------------------------------- #
class _FakeSurface:
    """Stands in for the ``rendercanvas`` object `_surface()` would return."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def set_update_mode(self, update_mode, *, min_fps=None, max_fps=None):
        self.calls.append((update_mode, min_fps, max_fps))


class _FakeHost:
    """The minimum `set_max_fps` needs from `self`: a `_surface()`."""

    def __init__(self, surface) -> None:
        self._surface_obj = surface

    def _surface(self):
        return self._surface_obj


#: Refresh rates a screen the viewer runs on can have.
REFRESH_RATES = (60, 75, 90, 120, 144, 165, 240)


def _presented_fps(ceiling: float, refresh: float) -> float:
    """What a vsynced window shows under *ceiling*: the first vsync after the interval."""
    import math

    slot = 1.0 / refresh
    return 1.0 / (math.ceil((1.0 / ceiling) / slot - 1e-9) * slot)


def test_the_frame_ceiling_never_halves_the_rate_below_sixty():
    """The window's ceiling is fitted to the screen, so no screen drops under 60 fps.

    The display paces the frames: the canvas presents with vsync. A ceiling
    *at* a vsync fraction beats against the grid and halves the rate -- it has
    happened twice (rendercanvas' default 30 gave a hard 15; 60 gave a hard 30
    on a 120 Hz screen). A ceiling far above every refresh rate (the old 240)
    avoided that but drew a frame per pointer event from a fast mouse. So the
    default is emtk's, which ``open_canvas`` turns into the slowest whole
    fraction of the screen's refresh rate that still reaches 60, plus a margin.
    chimol must hand that default through untouched, or the fitting never runs.
    """
    from emtk.native import DEFAULT_MAX_FPS as EMTK_DEFAULT
    from emtk.native import _frame_ceiling
    from chimol.hosts.native import canvas as native

    assert native.DEFAULT_MAX_FPS == EMTK_DEFAULT
    assert native._max_fps() == EMTK_DEFAULT, "chimol's default must let emtk fit the screen"
    for refresh in REFRESH_RATES:
        shown = _presented_fps(_frame_ceiling(refresh), refresh)
        assert shown >= 60.0 - 1e-6, f"{refresh} Hz shows {shown:.1f} fps"
        assert shown <= 100.0 + 1e-6, f"{refresh} Hz draws {shown:.1f} fps, a frame per event"


def test_the_shipped_configuration_agrees_with_the_default():
    """Three places say the ceiling; a window reads the config, so it must match."""
    import json
    import pathlib

    import chimol
    from chimol.core.settings import registry
    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.hosts.native.canvas import DEFAULT_MAX_FPS

    shipped = json.loads(
        (
            pathlib.Path(chimol.__file__).resolve().parent
            / "core"
            / "settings"
            / "chimol_display.json"
        ).read_text()
    )
    assert shipped["renderer"]["max_fps"] == DEFAULT_MAX_FPS
    assert _DISPLAY_CONFIG["renderer"]["max_fps"] == DEFAULT_MAX_FPS
    spec = registry.resolve("max_fps")
    assert spec.default == DEFAULT_MAX_FPS


def test_an_existing_configuration_is_lifted_off_the_old_ceilings():
    """A default written into a user's file reaches nobody without a migration.

    Existing copies of `chimol_display.json` carry `max_fps: 60` (before schema
    20) or `240` (before 23), both shipped defaults and not choices anybody
    made -- so each is migrated onto today's default, and a value the user
    *did* choose is left alone.
    """
    from chimol.core.settings.config import DISPLAY_CONFIG_MIGRATIONS, apply_display_config_migrations
    from chimol.hosts.native.canvas import DEFAULT_MAX_FPS

    for old in (60, 240):
        cfg = {"renderer": {"max_fps": old}}
        apply_display_config_migrations(cfg, 19)
        assert cfg["renderer"]["max_fps"] == DEFAULT_MAX_FPS, old
    chosen = {"renderer": {"max_fps": 144}}
    apply_display_config_migrations(chosen, 19)
    assert chosen["renderer"]["max_fps"] == 144
    assert DISPLAY_CONFIG_MIGRATIONS[23]["renderer"]["max_fps"] == (240, DEFAULT_MAX_FPS)


def test_the_present_method_can_be_pinned_by_hand(monkeypatch):
    """Both desktop windows read one setting, so a workaround applies to both."""
    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.hosts.native import canvas as native

    section = dict(_DISPLAY_CONFIG.get("renderer") or {})
    for choice in ("screen", "bitmap"):
        monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {**section, "present_method": choice})
        assert native._present_method() == choice
    monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {**section, "present_method": "nonsense"})
    assert native._present_method() == "auto", "a typo must not break the window"


def test_set_max_fps_calls_rendercanvas_set_update_mode():
    """The real live-reconfigure API, not a home-grown throttle beside it."""
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 30)

    assert surface.calls == [("ondemand", None, 30.0)]


def test_set_max_fps_leaves_the_update_mode_alone():
    """Only the ceiling changes; the mode stays the "ondemand" the window was
    built with, so this cannot turn a viewport into `continuous`.
    """
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 144)

    mode, min_fps, _max_fps = surface.calls[0]
    assert mode == "ondemand"
    assert min_fps is None


def test_set_max_fps_clamps_below_one():
    """``rendercanvas`` raises for anything under 1; a bad value must not
    crash a draw.
    """
    surface = _FakeSurface()
    host = _FakeHost(surface)

    CanvasRenderer.set_max_fps(host, 0)

    assert surface.calls == [("ondemand", None, 1.0)]


def test_set_max_fps_does_nothing_without_a_settable_surface():
    """A surface with no `set_update_mode` (or none at all) must not raise."""
    host = _FakeHost(object())
    CanvasRenderer.set_max_fps(host, 30)  # no exception


def test_set_max_fps_swallows_a_surface_that_raises():
    class _Angry:
        def set_update_mode(self, *a, **k):
            raise RuntimeError("no scheduler")

    CanvasRenderer.set_max_fps(_FakeHost(_Angry()), 30)  # no exception


# --------------------------------------------------------------------------- #
# The idle-settle timer
# --------------------------------------------------------------------------- #
class _FakeTimer:
    """Stands in for `chimol.core.toolkit.Timer`, recording what was asked."""

    def __init__(self) -> None:
        self.single_shot = None
        self.started_ms = None
        self._callback: Callable[[], None] | None = None
        self.timeout = SimpleNamespace(connect=self._connect)

    def _connect(self, fn) -> None:
        self._callback = fn

    def setSingleShot(self, value) -> None:  # noqa: N802 - mirrors Qt naming
        self.single_shot = value

    def start(self, msec) -> None:
        self.started_ms = msec

    def fire(self) -> None:
        """Simulate the timer elapsing."""
        assert self._callback is not None
        self._callback()


def _fake_host(*, nerd: bool = False, debug: bool = False) -> SimpleNamespace:
    """A double carrying real bound versions of the methods
    `_arm_idle_settle` itself calls: `timeout.connect` needs a callable, and
    `update` is what the settle draw asks for.

    ``nerd``/``debug`` set what :meth:`CanvasRenderer._readout_is_live` reads,
    which is what decides the timer's cadence.
    """
    gui = SimpleNamespace(nerd=nerd, debug_overlays=debug)
    host = SimpleNamespace(
        # `make_timer(self._controller)` picks the timer class from the viewer
        # (a HeadlessViewer never gets a QTimer); no viewer here, so the
        # module's `Timer` -- the one the tests patch -- is used.
        _controller=None,
        _idle_settle_timer=None,
        _idle_settling=False,
        updated=0,
        _internal_gui=gui,
    )
    host.update = lambda: setattr(host, "updated", host.updated + 1)
    host._on_idle_settle_timeout = lambda: CanvasRenderer._on_idle_settle_timeout(host)
    host._readout_is_live = lambda: CanvasRenderer._readout_is_live(host)
    return host


def test_arm_idle_settle_starts_a_singleshot_timer_past_the_idle_gap(monkeypatch):
    """With no readout on screen the timer is the one-shot settle."""
    monkeypatch.setattr("chimol.core.toolkit.Timer", _FakeTimer, raising=True)
    host = _fake_host()

    CanvasRenderer._arm_idle_settle(host)

    timer = host._idle_settle_timer
    assert isinstance(timer, _FakeTimer)
    assert timer.single_shot is True
    assert timer.started_ms >= int(_IDLE_GAP * 1000)


def test_a_live_readout_ticks_at_the_idle_tick_interval(monkeypatch):
    """The counter has to *run*, so it redraws on its own cadence.

    Past the idle gap it would only ever redraw after the rate had already
    been cleared to zero, which is a settle, not a counter.
    """
    monkeypatch.setattr("chimol.core.toolkit.Timer", _FakeTimer, raising=True)
    from chimol.render.frame_stats import nerd_idle_tick_interval

    host = _fake_host(nerd=True)
    CanvasRenderer._arm_idle_settle(host)

    assert host._idle_settle_timer.started_ms == max(int(nerd_idle_tick_interval() * 1000), 16)


def test_the_idle_tick_is_slower_than_the_publish_tick():
    """It costs a whole frame, not a re-read, so it must not run at the
    publish rate -- an instrument that redraws the scene to report the rate
    is an instrument that changes the rate.
    """
    from chimol.render.frame_stats import nerd_idle_tick_interval, nerd_report_interval

    assert nerd_idle_tick_interval() > nerd_report_interval()


def test_the_idle_tick_can_be_switched_off_entirely(monkeypatch):
    """0 is a real value: no redraws at all, the rate settles to zero and
    stays there. That is the setting to use while measuring.
    """
    monkeypatch.setattr("chimol.core.toolkit.Timer", _FakeTimer, raising=True)
    monkeypatch.setattr(
        "chimol.render.frame_stats.nerd_idle_tick_interval",
        lambda: 0.0,
        raising=True,
    )
    host = _fake_host(nerd=True)

    CanvasRenderer._arm_idle_settle(host)

    assert host._idle_settle_timer is None, "a disabled tick must arm nothing"


def test_the_settle_timer_asks_for_another_draw(monkeypatch):
    monkeypatch.setattr("chimol.core.toolkit.Timer", _FakeTimer, raising=True)
    host = _fake_host()

    CanvasRenderer._arm_idle_settle(host)
    host._idle_settle_timer.fire()

    assert host._idle_settling is True
    assert host.updated == 1


def test_a_real_draw_arms_the_idle_settle_timer():
    """Every draw that is not itself the settle draw rearms the debounce."""
    calls = []
    host = _fake_host()
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == [1]
    assert host._idle_settling is False


def test_the_settle_draw_does_not_rearm_when_no_readout_is_shown():
    """With nothing to keep live, the follow-up draw settles the rate to zero
    once and stops -- an idle viewport nobody is measuring goes fully quiet.
    """
    calls = []
    host = _fake_host()
    host._idle_settling = True
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == []
    assert host._idle_settling is False


def test_a_live_readout_keeps_rearming_so_the_counter_runs():
    """The reported bug: the counter only advanced when something *else*
    repainted the chrome (a hover crossing a control), because the settle draw
    deliberately did not rearm. With a readout on screen it must rearm --
    including after its own draw -- or the number freezes between hovers.
    """
    calls = []
    host = _fake_host(nerd=True)
    host._idle_settling = True  # this draw *is* the timer's own
    host._arm_idle_settle = lambda: calls.append(1)

    CanvasRenderer._note_frame_drawn(host)

    assert calls == [1], "a live readout must keep the timer going"
    assert host._idle_settling is False


def test_the_status_band_rate_also_counts_as_a_live_readout():
    """`debug_overlays` draws the plain rate without nerd mode's graphs; it is
    just as frozen if the tick stops.
    """
    host = _fake_host(debug=True)
    assert CanvasRenderer._readout_is_live(host) is True


def test_no_readout_means_no_repeating_tick():
    """Neither instrument on screen: nothing to keep live, nothing to pay."""
    host = _fake_host()
    assert CanvasRenderer._readout_is_live(host) is False
